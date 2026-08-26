// Nós e arestas viram SVG.
//
// SVG e não canvas pelo mesmo motivo registrado em `charts.js`: as cores saem
// das variáveis do CSS, então trocar de tema não exige redesenhar nada. E há um
// ganho que canvas não dá de graça: cada nó é um elemento real, então foco de
// teclado, `aria-label` e leitor de tela funcionam sem nenhuma camada extra.
//
// Nenhum texto vindo da API encosta em `innerHTML` — nome de projeto e de
// tecnologia entram por `textContent`, como manda o ADR-005.

const NS = 'http://www.w3.org/2000/svg';

export function svgEl(tag, atributos = {}, filhos = []) {
  const node = document.createElementNS(NS, tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (chave === 'class') node.setAttribute('class', String(valor));
    else if (chave === 'dataset') {
      for (const [k, v] of Object.entries(valor)) {
        if (v !== null && v !== undefined) node.dataset[k] = String(v);
      }
    } else if (chave === 'text') node.textContent = String(valor);
    else node.setAttribute(chave, valor === true ? '' : String(valor));
  }
  for (const filho of [].concat(filhos)) {
    if (filho) node.append(filho);
  }
  return node;
}

/** O palco: raiz, viewport que recebe zoom e pan, e as duas camadas. */
export function criarPalco() {
  const arestas = svgEl('g', { class: 'hb-edges' });
  const nos = svgEl('g', { class: 'hb-nodes' });
  const viewport = svgEl('g', { class: 'hb-viewport' }, [arestas, nos]);

  const svg = svgEl(
    'svg',
    {
      class: 'hb-stage',
      role: 'application',
      'aria-label': 'Mapa de projetos do HyperBrain',
    },
    [viewport]
  );

  return { svg, viewport, arestas, nos };
}

const ROTULO_TIPO = { projeto: 'projeto', tecnologia: 'tecnologia', core: 'núcleo' };

//: Rótulo comprido é o que faz um grafo virar sopa de letras: "PLATAFORMA DE
//: INGRESSOS" ocupa quatro vezes a largura do próprio nó e atravessa os
//: vizinhos. O nome inteiro continua no `aria-label` e no painel lateral —
//: quem precisa dele não perde nada, e quem só está olhando o mapa ganha.
const LIMITE_DO_ROTULO = 18;

export function encurtar(texto, limite = LIMITE_DO_ROTULO) {
  const limpo = String(texto ?? '').trim();
  return limpo.length <= limite ? limpo : `${limpo.slice(0, limite - 1)}…`;
}

/** Uma ou duas letras que representam o projeto dentro do círculo.
 *
 * Círculo vazio não tem identidade: com dezenove deles na tela, o nó só existe
 * enquanto o rótulo estiver visível. A inicial sobrevive ao zoom de longe, ao
 * rótulo escondido por falta de espaço e ao olhar de relance.
 */
export function iniciais(nome) {
  const palavras = String(nome ?? '')
    .trim()
    .split(/[\s\-_.]+/)
    .filter(Boolean);

  if (!palavras.length) return '?';
  if (palavras.length === 1) return palavras[0].slice(0, 2).toUpperCase();
  return (palavras[0][0] + palavras[1][0]).toUpperCase();
}

function forma(no) {
  if (no.tipo === 'tecnologia') {
    // Triângulo: a forma diferencia o tipo sem depender de cor, que é o
    // requisito de quem não distingue as duas.
    const r = no.tamanho;
    const pontos = [
      [0, -r],
      [r * 0.87, r * 0.5],
      [-r * 0.87, r * 0.5],
    ]
      .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
      .join(' ');
    return svgEl('polygon', { class: 'hb-node__shape', points: pontos });
  }

  return svgEl('circle', { class: 'hb-node__shape', r: no.tamanho });
}

/** Um nó: forma, rótulo e o mínimo de semântica para o teclado alcançá-lo.
 *
 * `indice` só serve para escalonar a entrada: o mapa se abre do centro para
 * fora, em vez de aparecer inteiro de uma vez.
 */
export function desenharNo(no, indice = 0) {
  const descricao =
    no.tipo === 'tecnologia'
      ? `${no.rotulo}, tecnologia usada por ${no.contagem} projetos`
      : `${no.rotulo}, ${ROTULO_TIPO[no.tipo] ?? no.tipo}`;

  const grupo = svgEl(
    'g',
    {
      class: 'hb-node',
      dataset: { id: no.id, tipo: no.tipo, estado: no.estado ?? '', fixado: no.fixado ?? false },
      // A matiz é um número, não uma cor: o CSS a aplica como rotação sobre o
      // token. Cor literal continua morando só em `tokens.css`.
      style: `--indice:${indice}${no.matiz === undefined ? '' : `;--matiz:${no.matiz}deg`}`,
      tabindex: '0',
      role: 'button',
      'aria-label': descricao,
    },
    [
      // Alvo de clique maior que o desenho: um círculo de 19px é preciso
      // demais para o mouse, e muito mais para o toque.
      svgEl('circle', { class: 'hb-node__hit', r: Math.max(no.tamanho + 12, 26) }),
      forma(no),
      no.tipo === 'projeto'
        ? svgEl('text', {
            class: 'hb-node__inicial',
            y: no.tamanho * 0.34,
            'text-anchor': 'middle',
            'font-size': (no.tamanho * 0.86).toFixed(1),
            text: iniciais(no.rotulo),
          })
        : null,
      svgEl('text', {
        class: 'hb-node__label',
        y: no.tamanho + 16,
        'text-anchor': 'middle',
        text: encurtar(no.rotulo),
      }),
    ]
  );

  return grupo;
}

export function desenharAresta(aresta) {
  return svgEl('line', {
    class: 'hb-edge',
    dataset: { id: aresta.id, kind: aresta.kind },
  });
}

/** Mede e reposiciona os rótulos para nenhum atravessar outro.
 *
 * Roda **só quando o grafo para de se mexer**: medir texto obriga o navegador a
 * calcular layout, e fazer isso a cada quadro custaria mais que a simulação
 * inteira. Enquanto os nós se acomodam, o rótulo acompanha embaixo, como antes.
 */
/** Distância até o núcleo, normalizada, aplicada como "luz" em cada nó.
 *
 * É o que dá profundidade sem 3D: o que está perto do núcleo recebe mais luz e
 * vem para a frente; o que está longe recua. A conta é geométrica — não é um
 * degradê pintado por cima —, então arrastar um nó muda a luz dele de verdade.
 */
export function iluminar(posicoes, { elementosDeNo }) {
  const centro = posicoes.get('core') ?? { x: 0, y: 0 };
  let maior = 1;

  for (const [id, ponto] of posicoes) {
    if (id === 'core') continue;
    maior = Math.max(maior, Math.hypot(ponto.x - centro.x, ponto.y - centro.y));
  }

  for (const [id, ponto] of posicoes) {
    const elemento = elementosDeNo.get(id);
    if (!elemento || id === 'core') continue;
    const distancia = Math.hypot(ponto.x - centro.x, ponto.y - centro.y) / maior;
    // 1 encostado no núcleo, 0 na borda do grafo.
    elemento.style.setProperty('--luz', (1 - distancia).toFixed(3));
  }
}

export function ajustarRotulos(posicoes, { elementosDeNo, nos }, posicionar) {
  const medidos = [];

  for (const no of nos) {
    const elemento = elementosDeNo.get(no.id);
    const ponto = posicoes.get(no.id);
    if (!elemento || !ponto) continue;

    const texto = elemento.querySelector('.hb-node__label');

    // Nó sem rótulo — o núcleo — entra mesmo assim, como obstáculo: ele ocupa
    // o maior buraco da tela e nenhum nome deveria pousar ali.
    if (!texto) {
      medidos.push({
        id: no.id,
        x: ponto.x,
        y: ponto.y,
        // 1,45 e não 1,9: o halo externo é quase transparente, e reservar o
        // círculo inteiro dele escondia rótulo que era perfeitamente legível.
        // O que precisa ficar limpo é o disco, os anéis e o texto de estado.
        raio: no.tamanho * 1.45,
        largura: 0,
        altura: 0,
        prioridade: Number.MAX_SAFE_INTEGER,
      });
      continue;
    }

    // `getComputedTextLength` é a largura real da fonte renderizada; estimar
    // por número de caracteres erra feio em nome com maiúsculas.
    const largura = texto.getComputedTextLength?.() ?? no.rotulo.length * 7;
    const altura = no.tipo === 'tecnologia' ? 11 : 12;

    medidos.push({
      id: no.id,
      x: ponto.x,
      y: ponto.y,
      raio: no.tamanho,
      largura,
      altura,
      //: Quem some primeiro é o satélite, não o projeto — e entre projetos,
      //: some antes o que está parado há mais tempo.
      prioridade: no.tipo === 'projeto' ? no.tamanho : 1,
      elemento: texto,
    });
  }

  const posicoesDeRotulo = posicionar(medidos);

  for (const item of medidos) {
    const escolha = posicoesDeRotulo.get(item.id);
    if (!escolha || !item.elemento) continue;
    item.elemento.setAttribute('x', escolha.dx.toFixed(1));
    item.elemento.setAttribute('y', escolha.dy.toFixed(1));
    item.elemento.setAttribute('text-anchor', escolha.anchor);
    item.elemento.dataset.oculto = String(escolha.oculto);
  }
}

/** Aplica as posições calculadas. Roda a cada quadro, então é só atributo. */
export function aplicarPosicoes(posicoes, { elementosDeNo, elementosDeAresta, arestas }) {
  for (const [id, elemento] of elementosDeNo) {
    const p = posicoes.get(id);
    if (p) elemento.setAttribute('transform', `translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`);
  }

  for (const aresta of arestas) {
    const linha = elementosDeAresta.get(aresta.id);
    const a = posicoes.get(aresta.de);
    const b = posicoes.get(aresta.para);
    if (!linha || !a || !b) continue;
    linha.setAttribute('x1', a.x.toFixed(2));
    linha.setAttribute('y1', a.y.toFixed(2));
    linha.setAttribute('x2', b.x.toFixed(2));
    linha.setAttribute('y2', b.y.toFixed(2));
  }
}

/** Traduz o estado visual em atributos — o CSS faz o resto.
 *
 * Atenuar por classe e opacidade, e não recalcular layout: entrar em foco não
 * pode mexer em onde as coisas estão, ou a pessoa perde a referência do que
 * estava olhando.
 */
export function aplicarDestaque({ elementosDeNo, elementosDeAresta, arestas }, { foco, proximos, destacados, selecionado }) {
  for (const [id, elemento] of elementosDeNo) {
    const apagado =
      (foco && !proximos.has(id)) || (!foco && destacados && !destacados.has(id) && id !== 'core');
    elemento.dataset.apagado = String(Boolean(apagado));
    elemento.dataset.selecionado = String(id === selecionado);
    elemento.dataset.foco = String(id === foco);
  }

  for (const aresta of arestas) {
    const linha = elementosDeAresta.get(aresta.id);
    if (!linha) continue;
    const dentro = foco ? proximos.has(aresta.de) && proximos.has(aresta.para) : true;
    linha.dataset.apagado = String(!dentro);
  }
}
