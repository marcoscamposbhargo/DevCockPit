// O núcleo — o único elemento da tela que não representa um dado.
//
// Ele representa a inteligência do painel, e por isso o que ele mostra tem que
// ser verdade: `desligado` quando o Cockpit AI está desligado, `pensando` só
// enquanto há uma requisição de fato em curso. Um núcleo que pulsa "pensando"
// sem ninguém ter perguntado nada é decoração fingindo ser informação.
//
// Toda a animação é CSS. Nenhum JavaScript roda por quadro aqui: o que muda é
// um atributo `data-brain`, e as regras de `hyperbrain.css` fazem o resto.

import { semente } from './layout.js';
import { svgEl } from './render.js';

//: Poucas e discretas. O teto do documento é 40; 30 dá a sensação de atividade
//: sem virar tela de proteção — e elas orbitam, além de cintilar.
const PARTICULAS = 30;

export const ESTADOS = {
  desligado: 'IA desligada',
  idle: 'pronto',
  listening: 'ouvindo',
  thinking: 'pensando',
  accessing: 'lendo o projeto',
  executing: 'executando',
  success: 'feito',
  warning: 'atenção',
  error: 'falhou',
};

function particulas(raio) {
  const grupo = svgEl('g', { class: 'hb-core__dust', 'aria-hidden': 'true' });

  for (let i = 0; i < PARTICULAS; i += 1) {
    // Posição derivada do índice: mesma disposição a cada abertura, como o
    // resto do grafo. Aleatório aqui faria o núcleo parecer outro a cada visita.
    const h = semente(`particula:${i}`);
    const angulo = (i / PARTICULAS) * Math.PI * 2 + ((h % 100) / 100) * 0.22;
    const distancia = raio * (1.35 + ((h >>> 7) % 60) / 100);

    grupo.append(
      svgEl('circle', {
        class: 'hb-core__mote',
        cx: (Math.cos(angulo) * distancia).toFixed(1),
        cy: (Math.sin(angulo) * distancia).toFixed(1),
        r: (1 + ((h >>> 3) % 12) / 10).toFixed(1),
        // Fases diferentes para as partículas não pulsarem em bloco.
        style: `--fase:${((h >>> 5) % 100) / 25}s`,
      })
    );
  }

  return grupo;
}

/**
 * Cria o núcleo.
 *
 * @param {number} raio  raio do disco central, em unidades do grafo
 */
export function criarNucleo(raio = 46) {
  const grupo = svgEl(
    'g',
    {
      class: 'hb-node hb-core',
      dataset: { id: 'core', tipo: 'core', brain: 'idle' },
      tabindex: '0',
      role: 'button',
      'aria-label': 'HyperBrain, núcleo',
    },
    [
      svgEl('circle', { class: 'hb-core__halo', r: raio * 1.9 }),
      particulas(raio),
      svgEl('circle', { class: 'hb-core__ring hb-core__ring--externo', r: raio * 1.72 }),
      svgEl('circle', { class: 'hb-core__ring', r: raio * 1.32 }),
      svgEl('circle', { class: 'hb-core__disc', r: raio }),
      // Arco de atividade: um traço curto girando bem mais rápido que os anéis.
      // É o que dá a impressão de que existe algo *acontecendo* lá dentro, e
      // não só de que a luz está acesa.
      svgEl('circle', { class: 'hb-core__arco', r: raio * 1.14 }),
      svgEl('circle', { class: 'hb-core__pulse', r: raio }),
      // Três pulsos defasados: com um só, a onda solitária deixa um vazio longo
      // entre batidas, e nesse vazio o núcleo parece desligado.
      svgEl('circle', { class: 'hb-core__pulse hb-core__pulse--tardio', r: raio }),
      svgEl('circle', { class: 'hb-core__pulse hb-core__pulse--terceiro', r: raio }),
      svgEl('text', {
        class: 'hb-core__name',
        y: 4,
        'text-anchor': 'middle',
        text: 'HYPERBRAIN',
      }),
      svgEl('text', {
        class: 'hb-core__state',
        y: raio + 22,
        'text-anchor': 'middle',
        text: ESTADOS.idle,
      }),
    ]
  );

  const rotulo = grupo.querySelector('.hb-core__state');

  return {
    no: grupo,
    definirEstado(estado) {
      const conhecido = estado in ESTADOS ? estado : 'idle';
      grupo.dataset.brain = conhecido;
      if (rotulo) rotulo.textContent = ESTADOS[conhecido];
      grupo.setAttribute('aria-label', `HyperBrain, núcleo — ${ESTADOS[conhecido]}`);
    },
  };
}
