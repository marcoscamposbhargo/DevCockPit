// Aba Services: estado dos serviços locais com reverificação sob demanda.

import { api } from '../lib/api.js';
import { el } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { loading, showError, toast } from '../lib/ui.js';

const STATE_COLOR = {
  ONLINE: 'var(--status-running)',
  OFFLINE: 'var(--fg-muted)',
  STARTING: 'var(--status-starting)',
  ERROR: 'var(--status-error)',
  STALE: 'var(--fg-muted)',
  UNKNOWN: 'var(--status-unknown)',
};

function table(items, { onOpen }) {
  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', { text: 'Serviço' }),
          el('th', { text: 'Endereço' }),
          el('th', { text: 'Estado' }),
          el('th', { text: 'Latência' }),
          el('th', { text: 'Verificado' }),
          el('th', { text: '' }),
        ]),
      ]),
      el(
        'tbody',
        {},
        items.map((item) =>
          el('tr', {}, [
            el('td', {}, [
              el('strong', { text: item.label }),
              el('div', { class: 'field__hint', text: item.health_kind }),
            ]),
            el('td', { class: 'mono', text: item.url ?? `${item.host}:${item.port ?? '—'}` }),
            el('td', {}, [
              el('span', {
                text: item.state,
                style: `color:${STATE_COLOR[item.state] ?? 'inherit'}`,
              }),
              item.detail ? el('div', { class: 'field__hint', text: item.detail }) : null,
            ]),
            el('td', { text: item.latency_ms === null ? '—' : `${item.latency_ms} ms` }),
            el('td', { text: item.checked_at ? relativeTime(item.checked_at) : 'nunca' }),
            el('td', {}, [
              item.url || item.port
                ? el('button', {
                    class: 'btn btn--sm',
                    text: 'Abrir',
                    onClick: () => onOpen(item.key),
                  })
                : null,
            ]),
          ])
        )
      ),
    ]),
  ]);
}

export async function renderServicesPanel(container) {
  const projectId = container.dataset.projectId;
  container.replaceChildren(loading());

  const draw = async (items) => {
    if (!items.length) {
      container.replaceChildren(
        el('p', {
          class: 'field__hint',
          text: 'Nenhum serviço cadastrado. A detecção sugere serviços a partir do Compose e do Vite.',
        })
      );
      return;
    }

    const onOpen = async (key) => {
      try {
        const resultado = await api.openBrowser(projectId, key);
        toast(`Abrindo ${resultado.detail}`, { kind: 'success' });
      } catch (error) {
        showError(error);
      }
    };

    const verificar = async () => {
      container.replaceChildren(loading('Verificando serviços…'));
      try {
        draw((await api.checkServices(projectId)).items);
      } catch (error) {
        showError(error);
      }
    };

    container.replaceChildren(
      el('div', { class: 'freshness' }, [
        el('span', {
          class: 'field__hint',
          text: 'Estado servido de cache; o verificador roda em background para projetos fixados e recentes.',
        }),
        el('button', { class: 'btn btn--sm', text: 'Verificar agora', onClick: verificar }),
      ]),
      table(items, { onOpen })
    );
  };

  try {
    await draw((await api.listServices(projectId)).items);
  } catch (error) {
    showError(error);
    container.replaceChildren(el('p', { class: 'loading', text: error.message }));
  }
}
