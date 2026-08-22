import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { duration, relativeTime } from '../lib/format.js';
import { emptyState, loading, pageHeader } from '../lib/ui.js';

const STATUS_COLOR = {
  SUCCESS: 'var(--status-running)',
  FAILED: 'var(--status-error)',
  TIMEOUT: 'var(--status-warning)',
  DENIED: 'var(--status-error)',
};

export async function renderActivity(container) {
  mount(container, loading());

  let data;
  try {
    data = await api.listActivity({ limit: 100 });
  } catch (error) {
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  if (!data.items.length) {
    mount(
      container,
      pageHeader({ title: 'Activity' }),
      emptyState({
        title: 'Nenhuma ação registrada',
        text: 'Toda ação executada pelo DevCockpit aparece aqui, com duração e resultado.',
      })
    );
    return;
  }

  const table = el('table', { class: 'table' }, [
    el('thead', {}, [
      el('tr', {}, [
        el('th', { text: 'Quando' }),
        el('th', { text: 'Ação' }),
        el('th', { text: 'Projeto' }),
        el('th', { text: 'Status' }),
        el('th', { text: 'Duração' }),
        el('th', { text: 'Mensagem' }),
      ]),
    ]),
    el(
      'tbody',
      {},
      data.items.map((entry) =>
        el('tr', {}, [
          el('td', { text: relativeTime(entry.created_at) }),
          el('td', { class: 'mono', text: entry.action }),
          el('td', {}, [
            entry.project_id
              ? el('a', {
                  href: `#/projects/${encodeURIComponent(entry.project_id)}`,
                  text: entry.project_id,
                })
              : '—',
          ]),
          el('td', {
            text: entry.status,
            style: `color:${STATUS_COLOR[entry.status] ?? 'inherit'}`,
          }),
          el('td', { text: duration(entry.duration_ms) }),
          el('td', { text: entry.message ?? '—' }),
        ])
      )
    ),
  ]);

  mount(
    container,
    pageHeader({ title: 'Activity', subtitle: `${data.total} registro(s)` }),
    el('div', { class: 'table-wrap' }, [table])
  );
}
