// Aba Docker da página do projeto (US-053).
//
// O console de job aparece em painel, logo abaixo das ações — nunca em modal.
// Modal esconderia justamente o progresso que se quer acompanhar.

import { api } from '../lib/api.js';
import { el } from '../lib/dom.js';
import { jobConsole } from '../lib/job-console.js';
import { loading, showError, toast } from '../lib/ui.js';

const ACTIONS = [
  { key: 'up', label: 'Subir', primary: true },
  { key: 'stop', label: 'Parar' },
  { key: 'restart', label: 'Reiniciar' },
  { key: 'down', label: 'Derrubar' },
];

const STATE_COLOR = {
  running: 'var(--status-running)',
  exited: 'var(--fg-muted)',
  created: 'var(--status-starting)',
  restarting: 'var(--status-warning)',
  paused: 'var(--status-warning)',
  dead: 'var(--status-error)',
};

function unavailable(status) {
  return el('div', { class: 'card' }, [
    el('div', { class: 'card__header' }, [
      el('h3', { text: 'Docker indisponível' }),
      el('span', { style: 'margin-left:auto' }, [
        el('span', { class: 'status-badge', dataset: { status: 'UNKNOWN' } }, [
          el('span', { class: 'status-badge__dot' }),
          'Unknown',
        ]),
      ]),
    ]),
    el('p', { class: 'field__hint', text: status.detail ?? 'O Docker não respondeu.' }),
  ]);
}

function noCompose(status) {
  return el('div', { class: 'card' }, [
    el('h3', { text: 'Sem arquivo Compose' }),
    el('p', {
      class: 'field__hint',
      text: status.detail ?? 'Este projeto não tem docker-compose.yml.',
    }),
  ]);
}

function containerTable(status, { onLogs }) {
  if (!status.containers.length) {
    return el('p', {
      class: 'field__hint',
      text: 'Nenhum container. Use "Subir" para iniciar os serviços.',
    });
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', { text: 'Serviço' }),
          el('th', { text: 'Estado' }),
          el('th', { text: 'Imagem' }),
          el('th', { text: 'Portas' }),
          el('th', { text: 'Status' }),
          el('th', { text: '' }),
        ]),
      ]),
      el(
        'tbody',
        {},
        status.containers.map((container) =>
          el('tr', {}, [
            el('td', {}, [
              el('strong', { text: container.service }),
              el('div', { class: 'field__hint mono', text: container.name }),
            ]),
            el('td', {}, [
              el('span', {
                text: container.state,
                style: `color:${STATE_COLOR[container.state] ?? 'inherit'}`,
              }),
              container.health
                ? el('div', { class: 'field__hint', text: container.health })
                : null,
            ]),
            el('td', { class: 'mono', text: container.image }),
            el(
              'td',
              { class: 'mono' },
              container.ports.length
                ? container.ports.map((port) =>
                    el('div', {}, [
                      el('a', {
                        href: `http://localhost:${port.host_port}`,
                        target: '_blank',
                        rel: 'noreferrer',
                        text: `${port.host_port}→${port.container_port}`,
                      }),
                    ])
                  )
                : ['—']
            ),
            el('td', { class: 'field__hint', text: container.status }),
            el('td', {}, [
              el('button', {
                class: 'btn btn--sm',
                text: 'Logs',
                onClick: () => onLogs(container.service),
              }),
            ]),
          ])
        )
      ),
    ]),
  ]);
}

export async function renderDockerPanel(container) {
  const projectId = container.dataset.projectId;
  container.replaceChildren(loading('Consultando o Docker…'));

  let status;
  try {
    status = await api.dockerStatus(projectId);
  } catch (error) {
    container.replaceChildren(
      el('div', { class: 'card' }, [
        el('h3', { text: 'Não foi possível consultar o Docker' }),
        el('p', { class: 'field__hint', text: error.message }),
      ])
    );
    return;
  }

  if (!status.available) {
    container.replaceChildren(
      unavailable(status),
      el('button', {
        class: 'btn',
        style: 'margin-top:var(--sp-3)',
        text: 'Verificar novamente',
        onClick: () => renderDockerPanel(container),
      })
    );
    return;
  }

  if (!status.compose_file) {
    container.replaceChildren(noCompose(status));
    return;
  }

  const consoleSlot = el('div', {});
  const logsSlot = el('div', {});

  const runAction = async (action) => {
    logsSlot.replaceChildren();
    try {
      const accepted = await api.dockerAction(projectId, action);
      const view = jobConsole({
        jobId: accepted.job_id,
        title: `docker compose ${action}`,
        onFinish: (state) => {
          if (state === 'SUCCESS') {
            toast(`"${action}" concluído.`, { kind: 'success' });
            // Recarrega só a tabela: o console permanece visível para leitura.
            refreshTable();
          }
        },
      });
      consoleSlot.replaceChildren(view.element);
    } catch (error) {
      showError(error);
    }
  };

  const showLogs = async (service) => {
    logsSlot.replaceChildren(loading('Buscando logs…'));
    try {
      const data = await api.dockerLogs(projectId, service, 200);
      logsSlot.replaceChildren(
        el('section', { class: 'job-console' }, [
          el('header', { class: 'job-console__header' }, [
            el('strong', { text: `Logs · ${service}` }),
            el('span', { class: 'job-console__time', text: `últimas ${data.tail} linhas` }),
            el('span', { style: 'margin-left:auto' }, [
              el('button', {
                class: 'btn btn--sm',
                text: 'Fechar',
                onClick: () => logsSlot.replaceChildren(),
              }),
            ]),
          ]),
          el('pre', { class: 'job-console__output', text: data.lines.join('\n') }),
        ])
      );
    } catch (error) {
      showError(error);
      logsSlot.replaceChildren();
    }
  };

  const tableSlot = el('div', {});
  const refreshTable = async () => {
    try {
      const fresh = await api.dockerStatus(projectId);
      tableSlot.replaceChildren(containerTable(fresh, { onLogs: showLogs }));
    } catch (error) {
      showError(error);
    }
  };

  tableSlot.replaceChildren(containerTable(status, { onLogs: showLogs }));

  container.replaceChildren(
    el('div', { class: 'page-header' }, [
      el('div', { class: 'page-header__text' }, [
        el('h2', { text: `${status.running_count} de ${status.containers.length} rodando` }),
        el('p', { class: 'field__hint mono', text: status.compose_file }),
      ]),
      el(
        'div',
        { class: 'page-header__actions' },
        ACTIONS.map((action) =>
          el('button', {
            class: `btn${action.primary ? ' btn--primary' : ''}`,
            text: action.label,
            onClick: () => runAction(action.key),
          })
        )
      ),
    ]),
    consoleSlot,
    tableSlot,
    logsSlot
  );
}
