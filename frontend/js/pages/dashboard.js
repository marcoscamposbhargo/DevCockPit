// Dashboard agregado (US-080). Consome GET /api/dashboard, servido de cache.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { emptyState, loading, pageHeader, showError, statCard, statusBadge } from '../lib/ui.js';

function freshness(data, onReload) {
  return el('div', { class: 'freshness' }, [
    el('span', {
      class: 'field__hint',
      // Nunca apresentar cache como tempo real (decisão D-18).
      text: `atualizado ${relativeTime(data.generated_at)}${data.from_cache ? ' · de cache' : ''}`,
    }),
    el(
      'button',
      { class: 'btn btn--sm', type: 'button', onClick: onReload },
      [icon('refresh', { size: 13 }), 'Recarregar']
    ),
  ]);
}

/**
 * Painel nomeado.
 *
 * A contagem vai no cabeçalho porque é a informação que decide se vale a pena
 * ler o corpo — e porque um painel vazio precisa dizer isso antes de ocupar
 * meia tela sem conteúdo.
 */
function panel({ title, count = null, action = null, body }) {
  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: title }),
      count !== null ? el('span', { class: 'panel__count', text: String(count) }) : null,
      action,
    ]),
    el('div', { class: 'panel__body' }, [body]),
  ]);
}

function panelEmpty(text) {
  return el('p', { class: 'panel__empty', text });
}

function portConflicts(conflitos) {
  if (!conflitos.length) return null;

  return el('div', { class: 'alert', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          conflitos.length === 1 ? 'Conflito de porta' : `${conflitos.length} conflitos de porta`,
      }),
      ...conflitos.map((item) =>
        el('div', { class: 'field__hint' }, [
          el('span', { class: 'mono', text: String(item.port) }),
          ` usada por ${item.projects.join(', ')}`,
        ])
      ),
      // Avisar sem oferecer o conserto obrigava a caçar o projeto na lista e
      // achar a aba certa. O conserto fica a um clique do aviso.
      el('div', { style: 'margin-top:var(--sp-2)' }, [
        el('a', { href: '#/ports', text: 'Resolver em Ports →' }),
      ]),
    ]),
  ]);
}

function pendingChanges(itens) {
  if (!itens.length) {
    return panelEmpty('Nenhuma alteração pendente conhecida.');
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        itens.map((item) =>
          el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(item.project_id)}?tab=git`,
                text: item.name,
              }),
            ]),
            el('td', { class: 'mono', text: item.branch ?? '—' }),
            el('td', { class: 'table__num', text: `${item.dirty_count} arquivo(s)` }),
          ])
        )
      ),
    ]),
  ]);
}

function activeServices(itens) {
  if (!itens.length) {
    return panelEmpty(
      'Nenhum serviço online. O verificador roda em background para projetos fixados e recentes.'
    );
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        itens.map((item) =>
          el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(item.project_id)}`,
                text: item.project_name,
              }),
            ]),
            el('td', { text: item.label }),
            el('td', {}, [
              item.url
                ? el('a', {
                    class: 'mono',
                    href: item.url,
                    target: '_blank',
                    rel: 'noreferrer',
                    text: item.url.replace(/^https?:\/\//, ''),
                  })
                : el('span', { class: 'mono', text: `:${item.port ?? '—'}` }),
            ]),
            el('td', { class: 'table__end' }, [statusBadge('RUNNING')]),
          ])
        )
      ),
    ]),
  ]);
}

/** Mapa de portas — o que a tela não mostrava e é a pergunta de todo dia:
 *  "quem está ocupando a 8000?". Conflito aparece marcado na própria linha. */
function portMap(portas, noAr) {
  if (!portas.length) {
    return panelEmpty('Nenhuma porta declarada pelos projetos cadastrados.');
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        portas.map((item) =>
          el('tr', { dataset: { conflict: String(item.conflict) } }, [
            el('td', { class: 'mono', text: String(item.port) }),
            el('td', { text: item.projects.join(', ') }),
            el('td', { class: 'table__end' }, [
              item.conflict
                ? el('span', { class: 'signal', dataset: { kind: 'dirty' } }, [
                    el('span', { class: 'signal__dot' }),
                    'conflito',
                  ])
                : // "Declarada" e "atendendo" são coisas diferentes, e o painel
                  // listava as duas do mesmo jeito: uma coluna de números onde
                  // metade é intenção e metade é fato. O visitante tinha que ir
                  // à tela de Ports para saber qual era qual.
                  noAr.has(item.port)
                  ? el('span', { class: 'signal', dataset: { kind: 'on' }, title: noAr.get(item.port) }, [
                      el('span', { class: 'signal__dot' }),
                      'no ar',
                    ])
                  : null,
            ]),
          ])
        )
      ),
    ]),
  ]);
}

function recent(itens) {
  if (!itens.length) return panelEmpty('Nenhum projeto acessado ainda.');

  return el(
    'ul',
    { class: 'recent-list' },
    itens.map((item) =>
      el('li', {}, [
        el('a', {
          class: 'recent-list__name',
          href: `#/projects/${encodeURIComponent(item.id)}`,
          text: item.name,
        }),
        el('span', { class: 'field__hint', text: relativeTime(item.last_accessed_at) }),
      ])
    )
  );
}

export async function renderDashboard(container) {
  mount(container, loading());

  // O mapa de portas é opcional: ele enriquece a tela, mas uma falha nele não
  // pode derrubar o dashboard inteiro.
  const [resultado, portas] = await Promise.allSettled([api.dashboard(), api.ports()]);

  if (resultado.status === 'rejected') {
    showError(resultado.reason);
    mount(container, el('p', { class: 'loading', text: resultado.reason.message }));
    return;
  }

  const data = resultado.value;
  const mapaDePortas = portas.status === 'fulfilled' ? portas.value.items : [];

  // Quais dessas portas estão de fato atendendo agora. Vem da mesma resposta,
  // do lado observado — nenhuma chamada a mais.
  const portasNoAr = new Map(
    (portas.status === 'fulfilled' ? (portas.value.observed ?? []) : []).map((porta) => [
      porta.port,
      porta.project_name
        ? `${porta.process_name ?? 'processo'} de ${porta.project_name}`
        : (porta.process_name ?? 'processo desconhecido'),
    ])
  );

  if (data.totals.projects === 0) {
    mount(
      container,
      pageHeader({ title: 'Ambiente de desenvolvimento' }),
      emptyState({
        title: 'Ambiente vazio',
        text: 'Aponte uma pasta raiz e deixe o DevCockpit encontrar seus projetos.',
        actions: [
          el('a', { class: 'btn btn--primary', href: '#/discovery', text: 'Varrer diretório' }),
        ],
      })
    );
    return;
  }

  mount(
    container,
    pageHeader({ title: 'Ambiente de desenvolvimento' }),
    freshness(data, () => renderDashboard(container)),
    portConflicts(data.port_conflicts),
    el('div', { class: 'grid-stats' }, [
      statCard(data.totals.projects, 'Projetos'),
      statCard(data.totals.running, 'Rodando', { tone: 'running' }),
      statCard(data.totals.stopped, 'Parados'),
      statCard(data.totals.with_docker, 'Com Docker'),
      statCard(data.totals.missing, 'Sem diretório'),
    ]),
    // Duas colunas, duas linhas. Antes era uma linha só, com a coluna da
    // esquerda quase sempre vazia e meia tela sobrando embaixo.
    el('div', { class: 'panel-grid' }, [
      panel({
        title: 'Serviços ativos',
        count: data.active_services.length,
        body: activeServices(data.active_services),
      }),
      panel({
        title: 'Portas em uso',
        count: mapaDePortas.length,
        body: portMap(mapaDePortas, portasNoAr),
      }),
      panel({
        title: 'Alterações pendentes',
        count: data.pending_changes.length,
        body: pendingChanges(data.pending_changes),
      }),
      panel({
        title: 'Acessados recentemente',
        action: el('a', { class: 'panel__action', href: '#/projects', text: 'Ver todos' }),
        body: recent(data.recent_projects),
      }),
    ])
  );
}
