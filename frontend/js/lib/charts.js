// Gráficos em SVG, desenhados à mão.
//
// Sem biblioteca por dois motivos. O painel não tem nenhuma dependência de
// frontend hoje, e trazer uma para desenhar duas formas seria pagar caro por
// pouco. E o que se precisa aqui é modesto: uma linha e um arco.
//
// SVG e não canvas porque o resultado precisa acompanhar o tema. Num `<svg>`
// as cores vêm de `currentColor` e das variáveis do CSS, então trocar de claro
// para escuro não exige redesenhar nada — num canvas exigiria.

import { el } from './dom.js';

const NS = 'http://www.w3.org/2000/svg';

function svgEl(nome, atributos = {}) {
  const node = document.createElementNS(NS, nome);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (valor !== null && valor !== undefined) node.setAttribute(chave, String(valor));
  }
  return node;
}

/**
 * Linha do tempo curta de um valor percentual.
 *
 * Um número sozinho responde "agora"; a linha responde "e antes?". Num painel
 * de operação essa é a pergunta que importa: 80% de memória constante há uma
 * hora é rotina, 80% subindo há cinco minutos é aviso.
 *
 * @param {number[]} valores  série de 0 a 100, do mais antigo ao mais recente
 */
export function sparkline(valores, { largura = 220, altura = 44, rotulo = '' } = {}) {
  const svg = svgEl('svg', {
    class: 'spark',
    viewBox: `0 0 ${largura} ${altura}`,
    preserveAspectRatio: 'none',
    role: 'img',
    'aria-label': rotulo,
  });

  // Menos de dois pontos não é uma linha. Em vez de desenhar um traço que
  // sugere estabilidade que ninguém mediu, o gráfico admite que ainda não sabe.
  if (valores.length < 2) {
    svg.append(
      svgEl('line', {
        x1: 0,
        y1: altura - 1,
        x2: largura,
        y2: altura - 1,
        class: 'spark__base',
      })
    );
    return svg;
  }

  const passo = largura / (valores.length - 1);
  const y = (v) => altura - 2 - (Math.max(0, Math.min(100, v)) / 100) * (altura - 4);
  const pontos = valores.map((v, i) => `${(i * passo).toFixed(1)},${y(v).toFixed(1)}`);

  // A área embaixo da linha dá peso ao gráfico sem exigir grade nem eixo — num
  // retângulo de 44 pixels de altura, eixo seria mais rabisco que informação.
  svg.append(
    svgEl('polygon', {
      class: 'spark__area',
      points: `0,${altura} ${pontos.join(' ')} ${largura},${altura}`,
    }),
    svgEl('polyline', { class: 'spark__line', points: pontos.join(' ') })
  );

  return svg;
}

/**
 * Arco de 0 a 100, com o número no meio.
 *
 * Meia-lua e não círculo inteiro: o vazio embaixo é onde o rótulo cabe sem
 * competir com o número, e um anel fechado obrigaria a espremer os dois.
 */
export function gauge(valor, { rotulo = '', detalhe = '', tom = null } = {}) {
  const pct = Math.max(0, Math.min(100, Number(valor) || 0));
  const raio = 34;
  const comprimento = Math.PI * raio;

  const svg = svgEl('svg', {
    class: 'gauge',
    viewBox: '0 0 84 52',
    role: 'img',
    'aria-label': `${rotulo}: ${pct}%`,
  });

  const caminho = `M 8 44 A ${raio} ${raio} 0 0 1 76 44`;

  svg.append(
    svgEl('path', { class: 'gauge__trilho', d: caminho }),
    svgEl('path', {
      class: 'gauge__arco',
      d: caminho,
      'stroke-dasharray': `${comprimento}`,
      // O arco cresce da esquerda para a direita descobrindo o traço, em vez
      // de girar: leitura mais direta para uma escala que começa em zero.
      'stroke-dashoffset': `${comprimento * (1 - pct / 100)}`,
    })
  );

  return el('div', { class: 'gauge-wrap', dataset: { tom } }, [
    svg,
    el('div', { class: 'gauge__valor', text: `${Math.round(pct)}%` }),
    el('div', { class: 'gauge__rotulo', text: rotulo }),
    detalhe ? el('div', { class: 'gauge__detalhe', text: detalhe }) : null,
  ]);
}

/**
 * Barra horizontal simples, para comparar itens de uma lista.
 *
 * @param {number} fracao  de 0 a 1
 */
export function bar(fracao, { tom = null, titulo = '' } = {}) {
  const largura = Math.max(0, Math.min(1, Number(fracao) || 0)) * 100;
  return el('span', { class: 'bar', dataset: { tom }, title: titulo }, [
    el('span', { class: 'bar__fill', style: `width:${largura.toFixed(1)}%` }),
  ]);
}

/** Faixa de alerta a partir do valor: verde, âmbar, vermelho. */
export function tomPara(valor, { atencao = 75, critico = 90 } = {}) {
  if (valor >= critico) return 'critico';
  if (valor >= atencao) return 'atencao';
  return 'ok';
}

/**
 * Colunas empilhadas — uma por dia, cada uma dividida por desfecho.
 *
 * Empilhado e não lado a lado porque a pergunta é dupla: "trabalhei quanto
 * neste dia?" (a altura total) e "quanto disso deu errado?" (a fatia). Duas
 * barras vizinhas respondem a primeira mal, porque obrigam a somar de olho.
 *
 * HTML e não SVG: são retângulos alinhados a uma grade, e cada coluna precisa
 * de `title` e de foco para o teclado. Em SVG isso seria reimplementar o que
 * uma div já faz.
 *
 * @param {Array<{label: string, total: number, partes: Array<{kind: string, valor: number, rotulo: string}>}>} colunas
 */
export function stackedColumns(colunas, { altura = 120 } = {}) {
  const maximo = Math.max(1, ...colunas.map((c) => c.total));

  return el('div', { class: 'cols', style: `--cols-altura:${altura}px` }, [
    el(
      'div',
      { class: 'cols__plot' },
      colunas.map((coluna) => {
        const detalhe = coluna.partes
          .filter((parte) => parte.valor > 0)
          .map((parte) => `${parte.valor} ${parte.rotulo}`)
          .join(' · ');

        return el(
          'div',
          {
            class: 'cols__col',
            tabindex: '0',
            title: `${coluna.label}: ${detalhe || 'nada'}`,
          },
          [
            el(
              'div',
              { class: 'cols__pilha', style: `height:${((coluna.total / maximo) * 100).toFixed(1)}%` },
              coluna.partes
                .filter((parte) => parte.valor > 0)
                .map((parte) =>
                  el('div', {
                    class: 'cols__seg',
                    dataset: { kind: parte.kind },
                    style: `flex-grow:${parte.valor}`,
                  })
                )
            ),
          ]
        );
      })
    ),
    el('div', { class: 'cols__eixo' }, [
      el('span', { text: colunas[0]?.label ?? '' }),
      el('span', { class: 'cols__max', text: `pico ${maximo}` }),
      el('span', { text: colunas.at(-1)?.label ?? '' }),
    ]),
  ]);
}

/**
 * Faixa de 24 células, uma por hora do dia.
 *
 * Responde "quando eu trabalho" sem eixo nem número: a intensidade basta, e o
 * padrão semanal aparece de relance.
 */
export function hourStrip(horas) {
  const maximo = Math.max(1, ...horas);
  return el(
    'div',
    { class: 'horas' },
    horas.map((valor, hora) =>
      el('span', {
        class: 'horas__celula',
        title: `${String(hora).padStart(2, '0')}h — ${valor} ação(ões)`,
        style: `--intensidade:${(valor / maximo).toFixed(2)}`,
      })
    )
  );
}
