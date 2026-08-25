// Bloco de análise do dashboard: o que aconteceu antes de agora.
//
// Carrega sozinho, depois da tela. O dashboard tem orçamento de 500 ms e é o
// que a pessoa foi ver; a análise é leitura de histórico e pode chegar meio
// segundo depois sem que ninguém sinta. Falha aqui não derruba o painel — o
// bloco diz que não conseguiu e o resto da tela continua de pé.

import { api } from './api.js';
import { bar, hourStrip, stackedColumns } from './charts.js';
import { el, mount } from './dom.js';

const CHAVE_PERIODO = 'devcockpit:analise:dias';
const PERIODOS = [7, 14, 30];

function periodoSalvo() {
  try {
    const bruto = Number(window.localStorage.getItem(CHAVE_PERIODO));
    return PERIODOS.includes(bruto) ? bruto : 14;
  } catch {
    // Modo privado ou storage bloqueado: o padrão serve.
    return 14;
  }
}

function salvarPeriodo(dias) {
  try {
    window.localStorage.setItem(CHAVE_PERIODO, String(dias));
  } catch {
    /* preferência é conveniência, não estado do sistema */
  }
}

function diaCurto(iso) {
  const [, mes, dia] = iso.split('-');
  return `${dia}/${mes}`;
}

function painel({ title, hint = null, action = null, body }) {
  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: title }),
      hint ? el('span', { class: 'panel__count', text: hint }) : null,
      action,
    ]),
    el('div', { class: 'panel__body' }, [body]),
  ]);
}

function vazio(texto) {
  return el('p', { class: 'panel__empty', text: texto });
}

function legenda() {
  return el('div', { class: 'analise-legenda' }, [
    el('span', {}, [el('i'), 'sucesso']),
    el('span', {}, [el('i', { dataset: { kind: 'failed' } }), 'falha']),
    el('span', {}, [el('i', { dataset: { kind: 'timeout' } }), 'tempo esgotado']),
    el('span', {}, [el('i', { dataset: { kind: 'denied' } }), 'recusada']),
  ]);
}

function atividadePorDia(dados) {
  if (!dados.activity_total) {
    return vazio('Nenhuma ação registrada no período.');
  }

  const colunas = dados.activity_daily.map((dia) => ({
    label: diaCurto(dia.day),
    total: dia.total,
    partes: [
      { kind: 'success', valor: dia.success, rotulo: 'sucesso' },
      { kind: 'failed', valor: dia.failed, rotulo: 'falha' },
      { kind: 'timeout', valor: dia.timeout, rotulo: 'tempo esgotado' },
      { kind: 'denied', valor: dia.denied, rotulo: 'recusada' },
    ],
  }));

  return el('div', {}, [stackedColumns(colunas), legenda()]);
}

function tecnologias(itens) {
  if (!itens.length) return vazio('Nenhuma tecnologia detectada.');

  const maximo = Math.max(...itens.map((i) => i.projects));
  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        itens.map((item) =>
          el('tr', {}, [
            el('td', { text: item.name }),
            el('td', { class: 'field__hint', text: item.category }),
            el('td', {}, [
              bar(item.projects / maximo, { titulo: `${item.projects} projeto(s)` }),
              el('span', { class: 'field__hint', text: String(item.projects) }),
            ]),
          ])
        )
      ),
    ]),
  ]);
}

function seletor(atual, aoTrocar) {
  return el(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': 'Período da análise' },
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
 * Bloco de análise. Devolve `{ element }`; o carregamento é interno.
 */
export function analyticsPanel() {
  const element = el('div', { class: 'panel-grid' });
  let dias = periodoSalvo();

  async function carregar() {
    mount(element, painel({ title: 'Análise', body: vazio('Carregando histórico…') }));

    let dados;
    try {
      dados = await api.analytics(dias);
    } catch (erro) {
      // 404 aqui não é "não encontrei o histórico": é um servidor que subiu
      // antes desta rota existir e continua no ar com o código antigo em
      // memória. A mensagem genérica mandava procurar o problema no lugar
      // errado — o arquivo novo está no disco, e recarregar a página não
      // resolve nada.
      const desatualizado = erro.status === 404;
      mount(
        element,
        painel({
          title: 'Análise',
          body: vazio(
            desatualizado
              ? 'O servidor no ar é anterior a esta tela: ele não conhece ' +
                  '/api/analytics. Reinicie o DevCockpit (scripts\\serve.ps1 -Restart) ' +
                  'e recarregue a página.'
              : `Não foi possível carregar o histórico: ${erro.message}`
          ),
        })
      );
      return;
    }

    const trocar = (novo) => {
      dias = novo;
      salvarPeriodo(novo);
      carregar();
    };

    mount(
      element,
      painel({
        title: 'Atividade',
        hint: `${dados.activity_total} ação(ões) · ${dados.failure_rate}% de falha`,
        action: seletor(dias, trocar),
        body: atividadePorDia(dados),
      }),
      painel({
        title: 'Horário de trabalho',
        hint: 'ações por hora do dia',
        body: dados.activity_total
          ? el('div', {}, [
              hourStrip(dados.activity_by_hour),
              el('div', { class: 'cols__eixo' }, [
                el('span', { text: '00h' }),
                el('span', { text: '12h' }),
                el('span', { text: '23h' }),
              ]),
            ])
          : vazio('Nenhuma ação registrada no período.'),
      }),
      painel({
        title: 'Stack dos projetos',
        body: tecnologias(dados.technologies),
      }),
      dados.truncated
        ? painel({
            title: 'Aviso',
            body: vazio(
              'O período tem mais registros do que a análise lê de uma vez. ' +
                'Os gráficos mostram só o começo da janela — reduza o período.'
            ),
          })
        : null
    );
  }

  carregar();
  return { element, recarregar: carregar };
}
