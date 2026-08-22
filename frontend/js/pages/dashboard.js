// Dashboard agregado (US-080). Consome GET /api/dashboard, servido de cache.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { emptyState, loading, pageHeader, showError, statCard, statusBadge } from '../lib/ui.js';

function freshness(data, onReload) {
  return el('div', { class: 'freshness' }, [
    el('span', {
      class: 'field__hint',
      // Nunca apresentar cache como tempo real (decisão D-18).
      text: `atualizado ${relativeTime(data.generated_at)}${data.from_cache ? ' · de cache' : ''}`,
    }),
    el('button', { class: 'btn btn--sm', text: 'Recarregar', onClick: onReload }),
  ]);
}

function portConflicts(conflitos) {
  if (!conflitos.length) return null;

  return el('div', { class: 'alert alert--warning' }, [
    el('strong', { text: 'Conflito de porta' }),
    el(
      'div',
      {},
      conflitos.map((item) =>
        el('div', { class: 'field__hint' }, [
          el('span', { class: 'mono', text: String(item.port) }),
          ` usada por ${item.projects.join(', ')}`,
        ])
      )
    ),
  ]);
}

function pendingChanges(itens) {
  if (!itens.length) {
    return el('p', { class: 'field__hint', text: 'Nenhuma alteração pendente conhecida.' });
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
            el('td', { text: `${item.dirty_count} arquivo(s)` }),
          ])
        )
      ),
    ]),
  ]);
}

function activeServices(itens) {
  if (!itens.length) {
    return el('p', {
      class: 'field__hint',
      text: 'Nenhum serviço online. O verificador roda em background para projetos fixados e recentes.',
    });
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
                    text: item.url,
                  })
                : el('span', { class: 'mono', text: `:${item.port ?? '—'}` }),
            ]),
            el('td', {}, [statusBadge('RUNNING')]),
          ])
        )
      ),
    ]),
  ]);
}

function recent(itens) {
  if (!itens.length) return null;

  return el('section', { style: 'margin-top:var(--sp-5)' }, [
    el('h2', { class: 'section-title', text: 'Acessados recentemente' }),
    el(
      'div',
      { class: 'chip-row' },
      itens.map((item) =>
        el('a', {
          class: 'tech-chip',
          href: `#/projects/${encodeURIComponent(item.id)}`,
          text: `${item.name} · ${relativeTime(item.last_accessed_at)}`,
        })
      )
    ),
  ]);
}

export async function renderDashboard(container) {
  mount(container, loading());

  let data;
  try {
    data = await api.dashboard();
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

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
      statCard(data.totals.running, 'Rodando'),
      statCard(data.totals.stopped, 'Parados'),
      statCard(data.totals.with_docker, 'Com Docker'),
      statCard(data.totals.missing, 'Sem diretório'),
    ]),
    el('div', { class: 'two-columns' }, [
      el('section', {}, [
        el('h2', { class: 'section-title', text: 'Alterações pendentes' }),
        pendingChanges(data.pending_changes),
      ]),
      el('section', {}, [
        el('h2', { class: 'section-title', text: 'Serviços ativos' }),
        activeServices(data.active_services),
      ]),
    ]),
    recent(data.recent_projects)
  );
}
