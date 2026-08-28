// Health Score do projeto — Fase 4.
//
// A tela tem uma regra e ela vale mais que o número grande no topo: **não
// medido não é zero**. Indicador sem dado aparece cinza, fora da média, e diz
// o que falta para poder ser medido. Barra vermelha para algo que ninguém
// apurou é o jeito mais rápido de fazer alguém perder a confiança no painel.
//
// Cada indicador mostra a evidência ao lado da nota. Número sem explicação não
// dá para agir: "62" não diz nada, "62 porque falta README e a pasta de testes
// está vazia" diz o que fazer em seguida.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { showError } from '../lib/ui.js';

/** Faixa de cor por nota. Três faixas, não um gradiente: o olho não lê
 *  diferença entre 61 e 64, e fingir que lê é precisão inventada. */
function faixa(nota) {
  if (nota === null || nota === undefined) return 'unknown';
  if (nota >= 70) return 'on';
  if (nota >= 40) return 'partial';
  return 'off';
}

function barra(indicador) {
  const medido = indicador.nota !== null && indicador.nota !== undefined;

  return el('article', { class: 'score-item', dataset: { kind: faixa(indicador.nota) } }, [
    el('div', { class: 'score-item__head' }, [
      el('span', { class: 'score-item__label', text: indicador.rotulo }),
      el('span', {
        class: 'score-item__value',
        text: medido ? String(indicador.nota) : 'não medido',
      }),
    ]),
    el('div', { class: 'score-item__track' }, [
      // Sem barra quando não há nota: uma barra vazia se lê como zero, e é
      // justamente a confusão que esta tela existe para não cometer.
      medido
        ? el('div', { class: 'score-item__fill', style: `width:${indicador.nota}%` })
        : null,
    ]),
    el('p', { class: 'score-item__why', text: indicador.evidencia }),
    indicador.sugestao
      ? el('p', { class: 'score-item__hint', text: indicador.sugestao })
      : null,
  ]);
}

/** Uma recomendação, com o fato que a motiva logo abaixo.
 *
 * O fato não é enfeite: é o que separa "arrume a documentação" de "você
 * declarou isso ao fechar a sessão de 26/08". A primeira se ignora; a segunda,
 * não.
 */
function recomendacao(item, project) {
  const destino = item.onde
    ? `#/projects/${encodeURIComponent(project.id)}?tab=${item.onde}`
    : null;

  return el('article', { class: 'next-item' }, [
    destino
      ? el('a', { class: 'next-item__title', href: destino, text: item.titulo })
      : el('span', { class: 'next-item__title', text: item.titulo }),
    el('p', { class: 'next-item__why', text: item.porque }),
  ]);
}


export async function renderIntelligencePanel(container, project) {
  let dados;
  try {
    dados = await api.intelligence(project.id);
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  const temNota = dados.score !== null && dados.score !== undefined;

  mount(
    container,
    el('section', { class: 'panel' }, [
      el('header', { class: 'panel__header' }, [
        el('h2', { class: 'panel__title', text: 'Health Score' }),
        el('span', {
          class: 'panel__count',
          text: `${dados.cobertura} indicador(es) medido(s)`,
          title:
            'A média cobre só o que foi possível medir. Indicador sem dado fica de fora ' +
            'em vez de entrar como zero.',
        }),
      ]),
      el('div', { class: 'panel__body' }, [
        // A próxima ação vem antes do score: quem abre esta aba quer saber o
        // que fazer, e o número é o argumento, não a resposta.
        dados.recomendacoes.length
          ? el('div', { class: 'next-block' }, [
              el('h3', { class: 'next-block__title', text: 'Próxima ação' }),
              ...dados.recomendacoes.map((item) => recomendacao(item, project)),
            ])
          : null,
        el('div', { class: 'score-head', dataset: { kind: faixa(dados.score) } }, [
          el('span', {
            class: 'score-head__number',
            text: temNota ? String(dados.score) : '—',
          }),
          el('p', {
            class: 'field__hint',
            text: temNota
              ? `Média dos ${dados.cobertura.split(' ')[0]} indicador(es) com dado. ` +
                'Os demais aparecem abaixo, com o que falta para medi-los.'
              : 'Nenhum indicador pôde ser medido ainda. O que falta está listado abaixo.',
          }),
        ]),
        el('div', { class: 'score-grid' }, dados.indicadores.map(barra)),
        el('p', {
          class: 'field__hint',
          text:
            'Todos os indicadores saem do que o painel já observou: disco, histórico de ' +
            'ações, sessões, tarefas e memória. Nenhum número é estimado.',
        }),
      ]),
    ])
  );
}
