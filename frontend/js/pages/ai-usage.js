// Consumo de IA do período (REQ-12).
//
// Responde "quanto gastei", não "o provider está conectado" — essa segunda
// pergunta já tem tela própria em Settings (T-11). Aqui é só o que a rota
// `GET /api/ai/usage` mediu no período.
//
// A regra que decide cada linha é P-02: indicador sem dado é "não medido", em
// cinza, com o que falta para medir — nunca zero. `medido: false` na resposta
// inteira nem chega a montar a tabela: a tela mostra o motivo, ponto. Com
// dados, custo e latência continuam anuláveis campo a campo (nenhum modelo
// com preço declarado no período, por exemplo), e por isso cada indicador é
// testado contra `null` isoladamente, do mesmo jeito que a tabela de
// providers em settings.js trata a latência da sondagem.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { pageHeader } from '../lib/ui.js';

const PERIODOS = [7, 14, 30, 90];
const DIAS_PADRAO = 7;

/** Texto de "não medido" com o motivo, no padrão de settings.js e do Health
 * Score: cinza, e nunca um zero com cara de medição.
 */
function naoMedido(motivo) {
  return el('span', { class: 'field__hint', text: motivo ? `não medido — ${motivo}` : 'não medido' });
}

/** Um indicador simples: rótulo, valor (ou "não medido"), explicação opcional. */
function indicador(rotulo, valor, { motivo = null, titulo = null } = {}) {
  const medido = valor !== null && valor !== undefined;
  return el('div', { class: 'stat-card', dataset: { empty: String(!medido) }, title: titulo }, [
    el('div', { class: medido ? 'stat-card__value' : 'stat-card__value field__hint', text: medido ? String(valor) : '—' }),
    el('div', { class: 'stat-card__label', text: rotulo }),
    !medido ? naoMedido(motivo) : null,
  ]);
}

/** Chamadas locais × cloud, lado a lado. As duas colunas seguem a mesma regra:
 * cada lado é "não medido" por si — o total pode existir sem que a divisão
 * exista (registro não classifica um dos providers, por exemplo).
 */
function divisaoLocalCloud(ind) {
  const temDivisao =
    ind.chamadas_local !== null && ind.chamadas_local !== undefined
    && ind.chamadas_cloud !== null && ind.chamadas_cloud !== undefined;

  if (!temDivisao) {
    return el('section', { class: 'panel', style: 'margin-top:var(--sp-6)' }, [
      el('h2', { class: 'section-title', text: 'Local × nuvem' }),
      naoMedido('sem tentativa classificada como local ou nuvem no período'),
    ]);
  }

  return el('section', { class: 'panel', style: 'margin-top:var(--sp-6)' }, [
    el('h2', { class: 'section-title', text: 'Local × nuvem' }),
    el('div', { class: 'stat-grid' }, [
      indicador('Chamadas locais', ind.chamadas_local, {
        titulo: 'Tentativas atendidas por provider declarado type: local em configs/ai.yml.',
      }),
      indicador('Tokens locais', ind.tokens_local),
      indicador('Chamadas em nuvem', ind.chamadas_cloud),
      indicador('Tokens em nuvem', ind.tokens_cloud),
    ]),
  ]);
}

/** Custo do período. A data da tabela de preço vai sempre junto do valor —
 * custo sem data ao lado é uma afirmação sem proveniência, e o projeto trata
 * isso como falha de honestidade (P-02), não detalhe de rodapé.
 */
function blocoCusto(ind) {
  const temCusto = ind.custo_estimado !== null && ind.custo_estimado !== undefined;
  const parcial = (ind.chamadas_sem_custo ?? 0) > 0;

  const valor = temCusto
    ? el('div', { class: 'stat-card__value', text: `US$ ${ind.custo_estimado.toFixed(4)}` })
    : el('div', { class: 'stat-card__value field__hint', text: '—' });

  const dataDoPreco = temCusto
    ? el('p', {
        class: 'field__hint',
        text: ind.price_date
          ? `Preço de ${ind.price_date}.`
          : 'Preço sem data registrada — não é possível dizer há quanto tempo a tabela usada está desatualizada.',
      })
    : naoMedido('nenhuma tentativa do período tinha preço declarado (configs/ai.yml)');

  return el('section', { class: 'panel', style: 'margin-top:var(--sp-6)' }, [
    el('h2', { class: 'section-title', text: 'Custo estimado' }),
    el('div', { class: 'stat-card', dataset: { empty: String(!temCusto) } }, [
      valor,
      el('div', { class: 'stat-card__label', text: 'no período' }),
      dataDoPreco,
    ]),
    // Aviso visível ao lado do total, não em rodapé: quando parte das
    // tentativas não tinha preço, o total é parcial, e escondido ele se lê
    // como completo — exatamente o que P-02 proíbe.
    parcial
      ? el('p', {
          class: 'field__hint',
          style: 'color:var(--status-warning)',
          text:
            `Parcial: ${ind.chamadas_sem_custo} chamada(s) sem custo conhecido não entraram ` +
            'nesta soma.',
        })
      : null,
  ]);
}

function seletorPeriodo(atual, aoTrocar) {
  return el(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': 'Período do consumo' },
    PERIODOS.map((dias) =>
      el('button', {
        class: 'segmented__opt',
        type: 'button',
        'aria-pressed': String(dias === atual),
        text: `${dias}d`,
        onClick: () => aoTrocar(dias),
      })
    )
  );
}

/**
 * O corpo da tela a partir da resposta de `GET /api/ai/usage`.
 *
 * `dados` é o `AiUsageOut` inteiro. Período sem execução (`medido: false`)
 * mostra o motivo que a rota deu — nunca uma tabela de zeros — porque "não
 * usei a IA" e "a IA não tem como rodar" são causas diferentes e a rota já
 * distingue as duas em texto.
 */
export function usageBody(dados) {
  if (!dados.medido) {
    return el('section', { class: 'panel' }, [
      el('p', { class: 'field__hint', text: dados.motivo || 'Nenhuma execução registrada no período.' }),
    ]);
  }

  const ind = dados.indicadores;

  return el('div', {}, [
    el('section', { class: 'panel' }, [
      el('h2', { class: 'section-title', text: 'Chamadas e tokens' }),
      el('div', { class: 'stat-grid' }, [
        indicador('Perguntas', ind.perguntas, {
          titulo: 'Perguntas distintas no período (correlation_id diferentes).',
        }),
        indicador('Chamadas', ind.chamadas, {
          titulo: 'Tentativas de execução — uma pergunta com fallback conta mais de uma.',
        }),
        indicador('Tokens de entrada', ind.tokens_in),
        indicador('Tokens de saída', ind.tokens_out),
      ]),
    ]),

    divisaoLocalCloud(ind),
    blocoCusto(ind),

    el('section', { class: 'panel', style: 'margin-top:var(--sp-6)' }, [
      el('h2', { class: 'section-title', text: 'Latência, falhas e fallbacks' }),
      el('div', { class: 'stat-grid' }, [
        indicador('Latência média', ind.latencia_media_ms !== null && ind.latencia_media_ms !== undefined
          ? `${Math.round(ind.latencia_media_ms)} ms`
          : null, {
          motivo: 'nenhuma tentativa executada mediu tempo de resposta',
          titulo: 'Média só das tentativas executadas — candidato pulado (skipped) não entra na conta.',
        }),
        indicador('Falhas', ind.falhas, {
          titulo: 'Tentativas com timeout ou erro. Pulada (skipped) não conta como falha.',
        }),
        indicador('Fallbacks', ind.fallbacks, {
          titulo:
            'Perguntas que precisaram de mais de uma tentativa — não o número de tentativas ' +
            'extras. Uma pergunta que passou por três provedores conta uma vez.',
        }),
      ]),
    ]),
  ]);
}

export async function renderAiUsage(container) {
  let dias = DIAS_PADRAO;

  async function carregar() {
    let dados;
    try {
      dados = await api.aiUsage(dias);
    } catch (error) {
      // Sem showError/toast aqui: a rota fora do ar não é um evento passageiro
      // como salvar um formulário — é o estado da tela, e fica explicado no
      // corpo dela mesma (mesmo padrão de renderSettings ao falhar `/health`).
      mount(
        container,
        pageHeader({ title: 'Consumo de IA', subtitle: 'Chamadas, tokens, custo e falhas do período' }),
        el('section', { class: 'panel' }, [
          el('p', { class: 'field__hint', text: error.message }),
        ])
      );
      return;
    }

    mount(
      container,
      pageHeader({
        title: 'Consumo de IA',
        subtitle: 'Chamadas, tokens, custo e falhas do período',
        actions: [seletorPeriodo(dias, trocar)],
      }),
      usageBody(dados)
    );
  }

  function trocar(novo) {
    dias = novo;
    carregar();
  }

  mount(container, pageHeader({ title: 'Consumo de IA' }), el('p', { class: 'loading', text: 'Carregando…' }));
  await carregar();
}
