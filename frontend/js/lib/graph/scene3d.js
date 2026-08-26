// O mapa em três dimensões, com three.js.
//
// Duas decisões que sustentam esta versão, e que valem mais que o brilho:
//
// **A dependência é servida pelo próprio painel.** `three.module.js` está em
// `js/vendor/`, resolvido por um mapa de importação no `index.html`. Sem npm,
// sem bundler e sem CDN — o executável precisa abrir offline, e uma dependência
// de rede quebraria isso. Ver ADR-009.
//
// **O texto continua no DOM.** Nome de projeto, foco de teclado e leitor de
// tela não entram na tela do WebGL: os rótulos são elementos HTML posicionados
// a cada quadro pela projeção da câmera. É o que impede o 3D de custar a
// acessibilidade que a versão em SVG tinha de graça.
//
// A cor sai dos mesmos tokens do resto do painel, lidos do CSS na hora de
// montar os materiais e relidos quando o tema muda.

import * as THREE from 'three';

// Apelidado para não colidir com a função local que projeta os rótulos —
// a colisão de nomes fazia a função chamar a si mesma até estourar a pilha.
import { posicionarRotulos as acomodarNaTela } from './labels.js';
import { encurtar } from './render.js';

//: Distância inicial da câmera. Ajustada no primeiro enquadramento.
const DISTANCIA_INICIAL = 900;
const ESCALA_MINIMA = 220;
const ESCALA_MAXIMA = 2600;
//: Abaixo disto o ponteiro andou por tremor de mão, não por intenção.
const ARRASTE_MINIMO = 4;

/** Lê uma cor dos tokens do CSS e devolve como cor do three.js. */
function corDoToken(elemento, nome, alternativa = '#888888') {
  const valor = getComputedStyle(elemento).getPropertyValue(nome).trim();
  try {
    return new THREE.Color(valor || alternativa);
  } catch {
    return new THREE.Color(alternativa);
  }
}

function paleta(raiz) {
  return {
    fundo: corDoToken(raiz, '--bg-base', '#0e1116'),
    superficie: corDoToken(raiz, '--bg-surface', '#161b22'),
    borda: corDoToken(raiz, '--border-strong', '#454c56'),
    acento: corDoToken(raiz, '--accent', '#2f81f7'),
    rodando: corDoToken(raiz, '--status-running', '#3fb950'),
    erro: corDoToken(raiz, '--status-error', '#f85149'),
    aviso: corDoToken(raiz, '--status-warning', '#d29922'),
    tecnologia: corDoToken(raiz, '--status-unknown', '#a371f7'),
    texto: corDoToken(raiz, '--fg-primary', '#e6edf3'),
    secundario: corDoToken(raiz, '--fg-secondary', '#9198a1'),
  };
}

function corDoNo(no, cores) {
  if (no.tipo === 'core') return cores.acento;
  if (no.tipo === 'tecnologia') {
    // A mesma matiz do mapa 2D, girada a partir do token: cada tecnologia com
    // sua cor, estável entre sessões.
    const base = cores.tecnologia.clone();
    const hsl = { h: 0, s: 0, l: 0 };
    base.getHSL(hsl);
    return base.setHSL((hsl.h + (no.matiz ?? 0) / 360) % 1, Math.max(hsl.s, 0.55), hsl.l);
  }
  if (no.estado === 'no-ar') return cores.rodando;
  if (no.estado === 'erro') return cores.erro;
  if (no.estado === 'ausente') return cores.aviso;
  // `--fg-secondary` e não uma tinta fixa: ele é meio-tom nos dois temas — mais
  // claro que o fundo escuro, mais escuro que o fundo claro. Derivar do texto
  // principal deixava a esfera quase preta no tema claro.
  return cores.secundario.clone();
}

function geometriaDoNo(no) {
  if (no.tipo === 'core') return new THREE.IcosahedronGeometry(no.tamanho, 3);
  if (no.tipo === 'tecnologia') return new THREE.OctahedronGeometry(no.tamanho * 1.15, 0);
  return new THREE.SphereGeometry(no.tamanho, 28, 20);
}

/**
 * Monta a cena.
 *
 * @param {HTMLElement} container  onde o `<canvas>` e os rótulos vivem
 * @param {{nos: Array, arestas: Array}} grafo
 * @param {object} layout  a simulação (em três dimensões)
 */
export function criarCena3D({ container, grafo, layout, aoSelecionar, aoPairar }) {
  const raiz = document.documentElement;
  let cores = paleta(raiz);

  const cena = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(52, 1, 1, 12000);
  camera.position.set(0, 0, DISTANCIA_INICIAL);

  const renderizador = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  // Teto no pixel ratio: numa tela 3x, renderizar tudo três vezes maior não
  // melhora nada que se perceba e derruba os quadros pela metade.
  renderizador.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // Sem mapeamento de tom, o brilho do núcleo estoura em branco e o resto da
  // cena afunda no preto: é a conta que transforma luz física em cor de tela.
  renderizador.toneMapping = THREE.ACESFilmicToneMapping;
  renderizador.toneMappingExposure = 1.15;
  renderizador.domElement.className = 'hb-canvas';
  container.append(renderizador.domElement);

  const camadaDeRotulos = document.createElement('div');
  camadaDeRotulos.className = 'hb-rotulos';
  camadaDeRotulos.setAttribute('aria-hidden', 'true');
  container.append(camadaDeRotulos);

  // --- luz ----------------------------------------------------------------
  //
  // A luz principal mora no núcleo: é ele que ilumina o ecossistema, e o que
  // está longe recebe menos. A profundidade sai da geometria, não de um
  // degradê pintado por cima.
  // A intensidade parece absurda porque, desde a r155, o three usa unidades
  // físicas: a luz cai com o quadrado da distância, e a cena tem centenas de
  // unidades de raio. 180.000 candelas a 300 de distância viram ~2 de
  // iluminação — que é o que se quer ver.
  const luzDoNucleo = new THREE.PointLight(cores.acento.getHex(), 180000, 3000, 2);
  cena.add(luzDoNucleo);

  // Ambiente e uma luz direcional fraca dão o mínimo para o que está longe do
  // núcleo não virar silhueta preta.
  //
  // A quantidade depende do tema, e não por gosto: no tema claro o fundo é
  // claro, e uma esfera de meio-tom só se destaca dele se estiver **bem**
  // iluminada. Com a luz do tema escuro, o mapa claro virava um punhado de
  // bolas pretas.
  const luzAmbiente = new THREE.AmbientLight(cores.texto.getHex(), 0.55);
  const luzDeApoio = new THREE.DirectionalLight(cores.texto.getHex(), 1.1);
  luzDeApoio.position.set(1, 1.5, 1);
  cena.add(luzAmbiente, luzDeApoio);

  function ajustarLuzAoTema() {
    const claro = raiz.dataset.theme === 'light';
    const corDaLuz = claro ? cores.superficie : cores.texto;
    luzAmbiente.color.copy(corDaLuz);
    luzAmbiente.intensity = claro ? 2.6 : 0.55;
    luzDeApoio.color.copy(corDaLuz);
    luzDeApoio.intensity = claro ? 2.2 : 1.1;
    renderizador.toneMappingExposure = claro ? 1.35 : 1.15;
  }

  ajustarLuzAoTema();

  // --- nós ----------------------------------------------------------------

  const malhas = new Map();
  const rotulos = new Map();
  const desenhaveis = [];

  for (const no of grafo.nos) {
    // O núcleo **é** a fonte de luz da cena: material sem sombreamento, que não
    // depende de nada iluminá-lo. Um material comum deixava um buraco preto no
    // meio do mapa, porque a luz que sai dele não volta para a própria
    // superfície.
    const material =
      no.tipo === 'core'
        ? new THREE.MeshBasicMaterial({ color: corDoNo(no, cores), toneMapped: false })
        : new THREE.MeshStandardMaterial({
            color: corDoNo(no, cores),
            roughness: 0.42,
            metalness: 0.2,
            emissive: corDoNo(no, cores),
            emissiveIntensity: 0.14,
          });

    const malha = new THREE.Mesh(geometriaDoNo(no), material);
    // O raio aparente do rótulo sai daqui; sem calcular, ele fica indefinido.
    malha.geometry.computeBoundingSphere();
    malha.userData.id = no.id;
    malha.userData.tipo = no.tipo;
    cena.add(malha);
    malhas.set(no.id, malha);
    desenhaveis.push(malha);

    const rotulo = document.createElement('span');
    rotulo.className = 'hb-rotulo';
    rotulo.dataset.tipo = no.tipo;

    if (no.tipo === 'core') {
      // O núcleo carrega duas linhas: o nome e o que ele está fazendo. Em WebGL
      // não existe texto de graça, e escrever isso numa textura custaria
      // nitidez — no DOM ele fica afiado em qualquer zoom e chega ao leitor de
      // tela junto com o resto da página.
      const nome = document.createElement('strong');
      nome.textContent = 'HYPERBRAIN';
      const estadoDoNucleo = document.createElement('span');
      estadoDoNucleo.className = 'hb-rotulo__estado';
      rotulo.append(nome, estadoDoNucleo);
      rotulo.dataset.brain = 'idle';
    } else {
      rotulo.textContent = encurtar(no.rotulo);
    }

    camadaDeRotulos.append(rotulo);
    rotulos.set(no.id, rotulo);
  }

  // Halo do núcleo: uma esfera maior, transparente, que dá volume à luz.
  const nucleo = malhas.get('core');
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(1, 32, 24),
    new THREE.MeshBasicMaterial({
      color: cores.acento,
      transparent: true,
      opacity: 0.09,
      side: THREE.BackSide,
    })
  );
  if (nucleo) {
    halo.scale.setScalar(nucleo.geometry.parameters.radius * 2.6);
    cena.add(halo);
  }

  // --- arestas ------------------------------------------------------------
  //
  // Um único objeto de linhas para o grafo inteiro: dezenas de objetos
  // separados custariam uma chamada de desenho cada.

  const vertices = new Float32Array(grafo.arestas.length * 6);
  const coresDeAresta = new Float32Array(grafo.arestas.length * 6);
  const geometriaDeArestas = new THREE.BufferGeometry();
  geometriaDeArestas.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geometriaDeArestas.setAttribute('color', new THREE.BufferAttribute(coresDeAresta, 3));

  const linhas = new THREE.LineSegments(
    geometriaDeArestas,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55 })
  );
  cena.add(linhas);

  function pintarArestas({ foco = null, proximos = null, ativa = null } = {}) {
    grafo.arestas.forEach((aresta, i) => {
      const dentro = !foco || (proximos?.has(aresta.de) && proximos?.has(aresta.para));
      const acesa = ativa === aresta.id;
      const cor = acesa
        ? cores.acento
        : aresta.kind === 'core'
          ? cores.acento.clone().multiplyScalar(dentro ? 0.55 : 0.12)
          : cores.borda.clone().multiplyScalar(dentro ? 0.8 : 0.15);

      for (const deslocamento of [0, 3]) {
        coresDeAresta[i * 6 + deslocamento] = cor.r;
        coresDeAresta[i * 6 + deslocamento + 1] = cor.g;
        coresDeAresta[i * 6 + deslocamento + 2] = cor.b;
      }
    });
    geometriaDeArestas.attributes.color.needsUpdate = true;
  }

  pintarArestas();

  // --- câmera orbital -----------------------------------------------------
  //
  // Escrita à mão, e não com o `OrbitControls` dos addons: o addon traria um
  // segundo arquivo para vendorizar e resolve muito mais do que esta tela usa.

  const orbita = { theta: 0.35, phi: 1.15, distancia: DISTANCIA_INICIAL, alvo: new THREE.Vector3() };
  let girando = true;

  function posicionarCamera() {
    const senoPhi = Math.sin(orbita.phi);
    camera.position.set(
      orbita.alvo.x + orbita.distancia * senoPhi * Math.sin(orbita.theta),
      orbita.alvo.y + orbita.distancia * Math.cos(orbita.phi),
      orbita.alvo.z + orbita.distancia * senoPhi * Math.cos(orbita.theta)
    );
    camera.lookAt(orbita.alvo);
  }

  posicionarCamera();

  const descartar = [];
  function ouvir(alvo, tipo, fn, opcoes) {
    alvo.addEventListener(tipo, fn, opcoes);
    descartar.push(() => alvo.removeEventListener(tipo, fn, opcoes));
  }

  const tela = renderizador.domElement;
  let gesto = null;

  ouvir(tela, 'pointerdown', (evento) => {
    if (evento.button !== 0) return;
    const alvo = apontar(evento);
    gesto = {
      x: evento.clientX,
      y: evento.clientY,
      theta: orbita.theta,
      phi: orbita.phi,
      no: alvo?.userData.id ?? null,
      moveu: false,
    };
    tela.setPointerCapture?.(evento.pointerId);
    girando = false;
  });

  ouvir(tela, 'pointermove', (evento) => {
    if (!gesto) {
      const alvo = apontar(evento);
      tela.dataset.sobre = alvo ? 'no' : '';
      aoPairar?.(alvo?.userData.id ?? null);
      return;
    }

    const dx = evento.clientX - gesto.x;
    const dy = evento.clientY - gesto.y;
    if (!gesto.moveu && Math.hypot(dx, dy) < ARRASTE_MINIMO) return;
    gesto.moveu = true;

    orbita.theta = gesto.theta - dx * 0.005;
    // Trava perto dos polos: passar direto vira cambalhota e desorienta.
    orbita.phi = Math.min(Math.PI - 0.12, Math.max(0.12, gesto.phi - dy * 0.005));
    posicionarCamera();
  });

  function encerrar(evento) {
    if (!gesto) return;
    const { no, moveu } = gesto;
    gesto = null;
    tela.releasePointerCapture?.(evento.pointerId);
    if (!moveu) aoSelecionar?.(no);
  }

  ouvir(tela, 'pointerup', encerrar);
  ouvir(tela, 'pointercancel', encerrar);

  ouvir(
    tela,
    'wheel',
    (evento) => {
      evento.preventDefault();
      girando = false;
      const fator = evento.deltaY < 0 ? 1 / 1.12 : 1.12;
      orbita.distancia = Math.min(ESCALA_MAXIMA, Math.max(ESCALA_MINIMA, orbita.distancia * fator));
      posicionarCamera();
    },
    { passive: false }
  );

  // --- seleção por raio ---------------------------------------------------

  const raio = new THREE.Raycaster();
  const ponteiro = new THREE.Vector2();

  function apontar(evento) {
    const caixa = tela.getBoundingClientRect();
    ponteiro.x = ((evento.clientX - caixa.left) / caixa.width) * 2 - 1;
    ponteiro.y = -((evento.clientY - caixa.top) / caixa.height) * 2 + 1;
    raio.setFromCamera(ponteiro, camera);
    return raio.intersectObjects(desenhaveis, false)[0]?.object ?? null;
  }

  // --- laço ---------------------------------------------------------------

  const projecao = new THREE.Vector3();
  const raioDeOclusao = new THREE.Raycaster();
  const direcao = new THREE.Vector3();
  let quadrosAteChecarOclusao = 0;
  const ocultosPorOclusao = new Set();

  /** Quem está atrás de outra coisa perde o rótulo.
   *
   * Sem isto, o nome de um projeto escondido atrás do núcleo aparece **em cima**
   * do núcleo, como se fosse dele. É o preço do 3D que ninguém lembra de pagar:
   * em duas dimensões nada fica atrás de nada.
   *
   * A checagem é a cada oito quadros porque é a parte cara do laço, e porque a
   * câmera se move devagar demais para alguém notar a diferença.
   */
  function conferirOclusao() {
    if (quadrosAteChecarOclusao-- > 0) return;
    quadrosAteChecarOclusao = 8;

    ocultosPorOclusao.clear();
    for (const [id, malha] of malhas) {
      direcao.copy(malha.position).sub(camera.position).normalize();
      raioDeOclusao.set(camera.position, direcao);
      const primeiro = raioDeOclusao.intersectObjects(desenhaveis, false)[0]?.object;
      if (primeiro && primeiro !== malha) ocultosPorOclusao.add(id);
    }
  }

  function posicionarRotulos() {
    conferirOclusao();
    const caixa = tela.getBoundingClientRect();
    if (!caixa.width) return;

    // Metade da altura da tela dividida pela tangente do meio-ângulo: o fator
    // que converte tamanho no mundo para tamanho em pixels a uma distância.
    const alturaProjetada = caixa.height / 2 / Math.tan(((camera.fov / 2) * Math.PI) / 180);
    const visiveis = [];

    for (const [id, rotulo] of rotulos) {
      const malha = malhas.get(id);
      if (!malha) continue;

      projecao.copy(malha.position).project(camera);
      // Atrás da câmera: o rótulo sairia espelhado do outro lado da tela.
      if (projecao.z > 1) {
        rotulo.style.opacity = '0';
        continue;
      }

      // O núcleo é a âncora da tela inteira, e some atrás de qualquer esfera
      // que passe na frente dele. O nome dele não pode sumir junto.
      if (ocultosPorOclusao.has(id) && id !== 'core') {
        rotulo.style.opacity = '0';
        continue;
      }

      const x = (projecao.x * 0.5 + 0.5) * caixa.width;
      const y = (-projecao.y * 0.5 + 0.5) * caixa.height;
      const distancia = camera.position.distanceTo(malha.position);
      // Longe fica mais apagado: é a mesma pista de profundidade que o olho
      // usa com neblina, e o que impede o fundo de competir com a frente.
      const nitidez = Math.max(0.15, Math.min(1, 1400 / distancia - 0.25));

      // Raio aparente do nó em pixels: a mesma projeção em perspectiva, só que
      // aplicada ao tamanho em vez de à posição.
      const raioNaTela = (malha.geometry.boundingSphere?.radius ?? 20) * (alturaProjetada / distancia);

      const ehNucleo = rotulo.dataset.tipo === 'core';

      if (ehNucleo) {
        // Posicionado à mão, **acima** do núcleo: abaixo dele fica o caminho
        // por onde os projetos da frente passam, e o acomodador o trataria como
        // um rótulo qualquer, disputando lugar com eles.
        rotulo.style.transform =
          `translate(-50%, -100%) translate(${x.toFixed(1)}px, ${(y - raioNaTela - 10).toFixed(1)}px)`;
        rotulo.style.opacity = '1';
        rotulo.style.zIndex = '1200';
      }

      visiveis.push({
        id,
        x,
        y,
        // O obstáculo do núcleo inclui o espaço do próprio nome, acima dele:
        // sem isso, o rótulo de um projeto pousava em cima de "HYPERBRAIN".
        raio: ehNucleo ? raioNaTela + 26 : raioNaTela,
        // Largura zero: entra como obstáculo, para ninguém pousar em cima dele,
        // e não recebe posição do acomodador.
        largura: ehNucleo ? 0 : rotulo.offsetWidth,
        altura: ehNucleo ? 0 : rotulo.offsetHeight,
        prioridade: ehNucleo ? 1e9 : raioNaTela,
        rotulo,
        nitidez,
        distancia,
      });
    }

    // Os rótulos passam pelo mesmo acomodador do mapa 2D — o algoritmo é o
    // mesmo, e o que muda é só de onde vêm as coordenadas.
    const arranjo = acomodarNaTela(visiveis);

    for (const item of visiveis) {
      const escolha = arranjo.get(item.id);
      if (!escolha) continue;
      const dx = escolha ? escolha.dx : 0;
      const dy = escolha ? escolha.dy : item.raio + 14;
      const ancora =
        escolha?.anchor === 'start' ? '0' : escolha?.anchor === 'end' ? '-100%' : '-50%';

      item.rotulo.style.transform =
        `translate(${ancora}, 0) translate(${(item.x + dx).toFixed(1)}px, ${(item.y + dy).toFixed(1)}px)`;
      item.rotulo.style.opacity =
        item.rotulo.dataset.apagado === 'true'
          ? '0.12'
          : escolha?.oculto
            ? '0'
            : item.nitidez.toFixed(2);
      item.rotulo.style.zIndex = String(Math.round(1000 - item.distancia / 10));
    }
  }

  function atualizarGeometria() {
    const posicoes = layout.posicoes();

    for (const [id, malha] of malhas) {
      const p = posicoes.get(id);
      if (p) malha.position.set(p.x, p.y, p.z ?? 0);
    }

    if (nucleo) {
      luzDoNucleo.position.copy(nucleo.position);
      halo.position.copy(nucleo.position);
    }

    grafo.arestas.forEach((aresta, i) => {
      const a = posicoes.get(aresta.de);
      const b = posicoes.get(aresta.para);
      if (!a || !b) return;
      vertices.set([a.x, a.y, a.z ?? 0, b.x, b.y, b.z ?? 0], i * 6);
    });
    geometriaDeArestas.attributes.position.needsUpdate = true;
    geometriaDeArestas.computeBoundingSphere();
  }

  function redimensionar() {
    const caixa = container.getBoundingClientRect();
    if (!caixa.width || !caixa.height) return;
    renderizador.setSize(caixa.width, caixa.height, false);
    camera.aspect = caixa.width / caixa.height;
    camera.updateProjectionMatrix();
  }

  const observador = new ResizeObserver(redimensionar);
  observador.observe(container);
  redimensionar();

  return {
    /** Um quadro. A página decide quando chamar. */
    desenhar({ girarSozinho = true } = {}) {
      if (girarSozinho && girando) orbita.theta += 0.0009;
      if (girando) posicionarCamera();
      atualizarGeometria();
      posicionarRotulos();
      renderizador.render(cena, camera);
    },

    /** Enquadra o grafo inteiro: distância a partir do raio do conjunto. */
    enquadrar() {
      const posicoes = [...layout.posicoes().values()];
      if (!posicoes.length) return;

      let maior = 1;
      for (const p of posicoes) maior = Math.max(maior, Math.hypot(p.x, p.y, p.z ?? 0));

      const abertura = (camera.fov * Math.PI) / 180;
      orbita.alvo.set(0, 0, 0);
      // 2,1 e não 1,35: em perspectiva, o nó mais próximo da câmera ocupa
      // muito mais tela que o raio do conjunto sugere, e o enquadramento
      // apertado deixava metade do grafo para fora.
      orbita.distancia = Math.min(
        ESCALA_MAXIMA,
        Math.max(ESCALA_MINIMA, (maior * 2.1) / Math.tan(abertura / 2))
      );
      posicionarCamera();
    },

    aproximar(fator = 1 / 1.2) {
      girando = false;
      orbita.distancia = Math.min(ESCALA_MAXIMA, Math.max(ESCALA_MINIMA, orbita.distancia * fator));
      posicionarCamera();
    },

    /** Liga e desliga a deriva lenta da câmera. */
    definirGiro(ligado) {
      girando = ligado;
    },

    girando: () => girando,

    /** Foco, destaque e seleção — os mesmos estados da versão em SVG. */
    aplicarDestaque({ foco, proximos, destacados, selecionado }) {
      for (const [id, malha] of malhas) {
        const apagado =
          (foco && !proximos.has(id)) ||
          (!foco && destacados && !destacados.has(id) && id !== 'core');

        malha.material.opacity = apagado ? 0.12 : 1;
        malha.material.transparent = apagado;
        malha.material.emissiveIntensity =
          id === selecionado ? 0.9 : malha.userData.tipo === 'core' ? 0.85 : apagado ? 0.02 : 0.12;
        malha.scale.setScalar(id === selecionado ? 1.25 : 1);

        const rotulo = rotulos.get(id);
        if (rotulo) {
          rotulo.dataset.apagado = String(Boolean(apagado));
          rotulo.dataset.selecionado = String(id === selecionado);
        }
      }
      pintarArestas({ foco, proximos });
    },

    /** Acende a aresta de uma consulta — só com fato por trás. */
    acender(arestaId) {
      pintarArestas({ ativa: arestaId });
    },

    /** O que o núcleo está fazendo — cor da luz e texto embaixo dele. */
    definirEstadoNucleo(nome, texto) {
      const rotulo = rotulos.get('core');
      if (rotulo) {
        rotulo.dataset.brain = nome;
        const linha = rotulo.querySelector('.hb-rotulo__estado');
        if (linha) linha.textContent = texto;
      }

      const malha = malhas.get('core');
      if (!malha) return;

      const cor =
        nome === 'desligado'
          ? cores.borda
          : nome === 'error'
            ? cores.erro
            : nome === 'warning'
              ? cores.aviso
              : nome === 'success'
                ? cores.rodando
                : cores.acento;

      malha.material.color.copy(cor);
      luzDoNucleo.color.copy(cor);
      luzDoNucleo.intensity = nome === 'desligado' ? 0.9 : 3.4;
      halo.material.color.copy(cor);
      halo.material.opacity = nome === 'desligado' ? 0.03 : 0.09;
    },

    /** O tema mudou: os materiais são refeitos a partir dos tokens novos. */
    reler() {
      cores = paleta(raiz);
      for (const no of grafo.nos) {
        const malha = malhas.get(no.id);
        if (!malha) continue;
        const cor = corDoNo(no, cores);
        malha.material.color.copy(cor);
        // O núcleo usa material sem sombreamento, que não tem `emissive`.
        malha.material.emissive?.copy(cor);
      }
      luzDoNucleo.color.copy(cores.acento);
      halo.material.color.copy(cores.acento);
      ajustarLuzAoTema();
      pintarArestas();
    },

    destruir() {
      observador.disconnect();
      while (descartar.length) descartar.pop()();
      for (const malha of malhas.values()) {
        malha.geometry.dispose();
        malha.material.dispose();
      }
      halo.geometry.dispose();
      halo.material.dispose();
      geometriaDeArestas.dispose();
      linhas.material.dispose();
      // O contexto WebGL é finito: o navegador derruba os mais antigos quando
      // passa do teto. Sair da rota sem liberar deixaria a tela em branco na
      // décima visita.
      renderizador.dispose();
      renderizador.domElement.remove();
      camadaDeRotulos.remove();
    },
  };
}
