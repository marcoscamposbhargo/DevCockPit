// Onde cada rótulo cabe — o problema que a simulação de força não resolve.
//
// A força cuida dos nós; o rótulo é um retângulo largo pendurado num deles, e
// dois nós confortavelmente separados podem ter nomes que se atravessam.
// "QRCODE_GENERATION" ocupa oito vezes a largura do próprio círculo.
//
// A saída é escolher, para cada rótulo, o primeiro lugar livre em volta do nó:
// abaixo, acima, à direita, à esquerda. Quem não acha lugar nenhum **some** —
// e volta no hover e no foco. Um nome ilegível por cima de outro não informa
// mais do que nenhum nome: informa menos, porque atrapalha o vizinho também.
//
// Módulo puro: recebe números, devolve números. Quem mede o texto de verdade é
// a tela, com `getComputedTextLength()`.

//: Folga entre caixas. Dois pixels bastam para o olho separar; mais que isso
//: começa a esconder rótulo que caberia.
const MARGEM = 2;

/** Lugares tentados, em ordem. Abaixo primeiro porque é o padrão de leitura. */
function candidatos(raio, largura, altura) {
  const meia = altura / 2;
  return [
    { dx: 0, dy: raio + altura + 2, anchor: 'middle', largura, altura },
    { dx: 0, dy: -(raio + 6), anchor: 'middle', largura, altura },
    { dx: raio + 8, dy: meia - 1, anchor: 'start', largura, altura },
    { dx: -(raio + 8), dy: meia - 1, anchor: 'end', largura, altura },
  ];
}

function caixaDoRotulo(no, candidato) {
  const centroY = no.y + candidato.dy - candidato.altura / 2;
  let esquerda = no.x + candidato.dx;
  if (candidato.anchor === 'middle') esquerda -= candidato.largura / 2;
  else if (candidato.anchor === 'end') esquerda -= candidato.largura;

  return {
    x1: esquerda - MARGEM,
    y1: centroY - MARGEM,
    x2: esquerda + candidato.largura + MARGEM,
    y2: centroY + candidato.altura + MARGEM,
  };
}

function colide(a, b) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

/**
 * Escolhe a posição de cada rótulo.
 *
 * Item com `largura: 0` entra só como obstáculo, e não recebe posição. É o
 * caso do núcleo: ele não tem rótulo para acomodar, mas ocupa um buraco enorme
 * no meio da tela — halo, anéis, nome e estado — e um rótulo de tecnologia
 * pousando ali fica ilegível.
 *
 * @param {Array} nos  `{id, x, y, raio, largura, altura, prioridade}`
 * @returns {Map<string, {dx: number, dy: number, anchor: string, oculto: boolean}>}
 */
export function posicionarRotulos(nos) {
  // Os círculos dos nós são obstáculos desde o começo: rótulo por cima de nó é
  // tão ruim quanto rótulo por cima de rótulo.
  const ocupado = nos.map((no) => ({
    x1: no.x - no.raio,
    y1: no.y - no.raio,
    x2: no.x + no.raio,
    y2: no.y + no.raio,
  }));

  // Maior prioridade primeiro, e o id desempata: com a ordem dependendo só da
  // entrada, o mesmo grafo produz o mesmo arranjo em toda abertura.
  const ordem = [...nos].sort(
    (a, b) => (b.prioridade ?? 0) - (a.prioridade ?? 0) || (a.id < b.id ? -1 : 1)
  );

  const resultado = new Map();

  for (const no of ordem) {
    if (!no.largura) continue;

    const opcoes = candidatos(no.raio, no.largura, no.altura);
    const escolhido = opcoes.find(
      (opcao) => !ocupado.some((caixa) => colide(caixaDoRotulo(no, opcao), caixa))
    );

    if (escolhido) {
      ocupado.push(caixaDoRotulo(no, escolhido));
      resultado.set(no.id, { ...escolhido, oculto: false });
    } else {
      // Sem lugar: fica escondido na posição padrão, e reaparece no hover.
      resultado.set(no.id, { ...opcoes[0], oculto: true });
    }
  }

  return resultado;
}
