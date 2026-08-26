// Onde cada nó fica — simulação de força, em números puros.
//
// Este módulo não conhece DOM, SVG nem `fetch`. Recebe nós e arestas, devolve
// coordenadas. É o que permite testá-lo no runner do Node, sem navegador.
//
// Duas escolhas que valem explicar, porque contrariam o comportamento padrão
// de um grafo de força:
//
// **A posição inicial é determinística.** Nada de `Math.random()`. O mesmo
// projeto cai no mesmo lugar toda vez que a tela abre — um grafo que se
// reorganiza sozinho a cada visita não deixa ninguém construir memória
// espacial, e memória espacial é metade do motivo de existir um grafo.
//
// **A simulação para.** A energia decai e, abaixo do limiar, o laço encerra.
// Nó voando para sempre é bonito no primeiro minuto e cansativo no segundo —
// e custa CPU o dia inteiro numa ferramenta que fica aberta o dia inteiro.

//: Quanto os nós se empurram. Cresce com o quadrado da proximidade, então o
//: valor parece alto: a 100px de distância isto vira ~1 de força.
//:
//: A repulsão é **proporcional ao peso dos dois nós**. Sem isso, o projeto de
//: nome longo empurra tanto quanto o satélite de tecnologia, e os rótulos se
//: sobrepõem justamente no meio, onde estão os nós maiores.
const REPULSAO = 11000;

//: Comprimento de repouso por tipo de aresta. A do núcleo é maior porque
//: precisa caber o rótulo do projeto sem encostar no núcleo.
const COMPRIMENTO = { core: 285, tech: 165, padrao: 200 };

const RIGIDEZ = 0.04;
//: Puxão em direção ao centro. Sem isto, um projeto sem nenhuma tecnologia
//: compartilhada é empurrado para fora e some da viewport.
const GRAVIDADE = 0.006;
const ATRITO = 0.85;
const DECAIMENTO = 0.945;
//: Abaixo disto o movimento não é mais visível, só custo.
const ENERGIA_MINIMA = 0.008;

/** Hash determinístico de texto (FNV-1a de 32 bits). */
export function semente(texto) {
  let h = 0x811c9dc5;
  for (let i = 0; i < texto.length; i += 1) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

/** Posição inicial de um nó, derivada só do id: mesma entrada, mesmo lugar.
 *
 * Em três dimensões a distribuição sai do ângulo de inclinação derivado do
 * mesmo hash: espalha sobre a esfera sem os amontoados que uma escolha ingênua
 * de latitude produz nos polos.
 */
export function posicaoInicial(id, { centroX = 0, centroY = 0, dimensoes = 2 } = {}) {
  const h = semente(id);
  const angulo = ((h % 997) / 997) * Math.PI * 2;
  const raio = 150 + ((h >>> 10) % 130);

  if (dimensoes < 3) {
    return { x: centroX + Math.cos(angulo) * raio, y: centroY + Math.sin(angulo) * raio, z: 0 };
  }

  const u = ((h >>> 3) % 1000) / 1000;
  const inclinacao = Math.acos(1 - 2 * u);
  return {
    x: centroX + Math.sin(inclinacao) * Math.cos(angulo) * raio,
    y: centroY + Math.sin(inclinacao) * Math.sin(angulo) * raio,
    z: Math.cos(inclinacao) * raio,
  };
}

/**
 * Cria a simulação.
 *
 * @param {Array} nos      objetos com `id` e, opcionalmente, `fixo`
 * @param {Array} arestas  objetos com `de`, `para` e `kind`
 */
export function criarLayout(nos, arestas, { centroX = 0, centroY = 0, dimensoes = 2 } = {}) {
  const corpos = new Map();
  const emTresDimensoes = dimensoes >= 3;

  for (const no of nos) {
    const inicial = no.fixo
      ? { x: centroX, y: centroY, z: 0 }
      : posicaoInicial(no.id, { centroX, centroY, dimensoes });
    corpos.set(no.id, {
      id: no.id,
      ...inicial,
      vx: 0,
      vy: 0,
      vz: 0,
      fixo: Boolean(no.fixo),
      //: 1 é o nó de projeto comum. O adaptador pode declarar `peso` quando o
      //: espaço que o nó precisa não é o mesmo que ele ocupa desenhado;
      //: senão, o tamanho serve.
      peso: no.peso ?? (no.tamanho ?? 19) / 19,
    });
  }

  //: Aresta que aponta para nó inexistente é defeito do adaptador, não algo
  //: para a simulação adivinhar. Descartar em silêncio esconderia o defeito.
  const ligacoes = arestas.filter((a) => corpos.has(a.de) && corpos.has(a.para));

  let energia = 1;

  function passo() {
    if (energia < ENERGIA_MINIMA) return false;

    const lista = [...corpos.values()];

    for (const corpo of lista) {
      corpo.fx = 0;
      corpo.fy = 0;
      corpo.fz = 0;
    }

    // Repulsão entre todos os pares. O(n²) e assumido: com ~200 nós são 20 mil
    // contas por quadro, o que um quadtree resolveria em troca de 150 linhas
    // que ninguém precisaria manter nesta escala.
    for (let i = 0; i < lista.length; i += 1) {
      for (let j = i + 1; j < lista.length; j += 1) {
        const a = lista[i];
        const b = lista[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dz = emTresDimensoes ? b.z - a.z : 0;
        let dist2 = dx * dx + dy * dy + dz * dz;

        // Dois nós exatamente sobrepostos dividiriam por zero. O desempate sai
        // do hash do id, não de um sorteio: determinismo vale mais aqui.
        if (dist2 < 0.01) {
          const h = semente(a.id + b.id);
          dx = ((h % 100) - 50) / 50;
          dy = (((h >>> 8) % 100) - 50) / 50;
          dz = emTresDimensoes ? (((h >>> 16) % 100) - 50) / 50 : 0;
          dist2 = dx * dx + dy * dy + dz * dz || 1;
        }

        const dist = Math.sqrt(dist2);
        const forca = (REPULSAO * a.peso * b.peso) / dist2;
        const ux = dx / dist;
        const uy = dy / dist;
        const uz = dz / dist;

        a.fx -= ux * forca;
        a.fy -= uy * forca;
        a.fz -= uz * forca;
        b.fx += ux * forca;
        b.fy += uy * forca;
        b.fz += uz * forca;
      }
    }

    // Molas das arestas.
    for (const ligacao of ligacoes) {
      const a = corpos.get(ligacao.de);
      const b = corpos.get(ligacao.para);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = emTresDimensoes ? b.z - a.z : 0;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      const alvo = COMPRIMENTO[ligacao.kind] ?? COMPRIMENTO.padrao;
      const forca = (dist - alvo) * RIGIDEZ;
      const ux = dx / dist;
      const uy = dy / dist;
      const uz = dz / dist;

      a.fx += ux * forca;
      a.fy += uy * forca;
      a.fz += uz * forca;
      b.fx -= ux * forca;
      b.fy -= uy * forca;
      b.fz -= uz * forca;
    }

    let maiorVelocidade = 0;

    for (const corpo of lista) {
      if (corpo.fixo) {
        corpo.vx = 0;
        corpo.vy = 0;
        corpo.vz = 0;
        continue;
      }

      corpo.fx += (centroX - corpo.x) * GRAVIDADE;
      corpo.fy += (centroY - corpo.y) * GRAVIDADE;
      corpo.fz += (0 - corpo.z) * GRAVIDADE;

      corpo.vx = (corpo.vx + corpo.fx) * ATRITO;
      corpo.vy = (corpo.vy + corpo.fy) * ATRITO;
      corpo.x += corpo.vx * energia;
      corpo.y += corpo.vy * energia;

      if (emTresDimensoes) {
        corpo.vz = (corpo.vz + corpo.fz) * ATRITO;
        corpo.z += corpo.vz * energia;
      }

      maiorVelocidade = Math.max(
        maiorVelocidade,
        Math.abs(corpo.vx),
        Math.abs(corpo.vy),
        emTresDimensoes ? Math.abs(corpo.vz) : 0
      );
    }

    energia *= DECAIMENTO;

    // Estabilizou antes da energia acabar: encerra em vez de continuar
    // gastando quadro para mover décimos de pixel.
    if (maiorVelocidade < 0.05) energia = 0;

    return energia >= ENERGIA_MINIMA;
  }

  return {
    passo,
    get energia() {
      return energia;
    },
    /** Reaquece após uma interação — arrastar um nó reacomoda os vizinhos. */
    reaquecer(valor = 0.45) {
      energia = Math.max(energia, valor);
    },
    posicao(id) {
      const corpo = corpos.get(id);
      return corpo ? { x: corpo.x, y: corpo.y, z: corpo.z } : null;
    },
    posicoes() {
      return new Map([...corpos].map(([id, c]) => [id, { x: c.x, y: c.y, z: c.z }]));
    },
    /** Prende um nó onde a pessoa o soltou. */
    fixar(id, x, y, z = null) {
      const corpo = corpos.get(id);
      if (!corpo) return;
      corpo.x = x;
      corpo.y = y;
      if (z !== null) corpo.z = z;
      corpo.vx = 0;
      corpo.vy = 0;
      corpo.vz = 0;
      corpo.fixo = true;
    },
    soltar(id) {
      const corpo = corpos.get(id);
      if (corpo) corpo.fixo = false;
    },
    /** Roda até estabilizar, sem desenhar. Usado quando o movimento é vetado. */
    estabilizar(maximo = 400) {
      let voltas = 0;
      while (voltas < maximo && passo()) voltas += 1;
      return voltas;
    },
  };
}
