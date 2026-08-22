// Painel Git da página do projeto (US-032).

import { api } from '../lib/api.js';
import { el } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { loading } from '../lib/ui.js';

const CHANGE_LABEL = {
  modified: 'modificado',
  added: 'novo',
  deleted: 'removido',
  renamed: 'renomeado',
  untracked: 'não rastreado',
  conflicted: 'conflito',
};

const COUNT_LABEL = {
  modified: 'modificados',
  added: 'novos',
  deleted: 'removidos',
  renamed: 'renomeados',
  untracked: 'não rastreados',
  staged: 'no índice',
  conflicted: 'em conflito',
};

function notARepo(status) {
  if (status.inside_other_repo) {
    return el('div', { class: 'card' }, [
      el('h3', { text: 'Esta pasta não é um repositório próprio' }),
      el('p', { class: 'field__hint' }, [
        'Ela está dentro do repositório ',
        el('span', { class: 'mono', text: status.repo_root }),
        '. O DevCockpit não mostra o estado do repositório pai aqui, porque ' +
          'seria o mesmo estado para todos os projetos abaixo dele.',
      ]),
    ]);
  }

  return el('div', { class: 'card' }, [
    el('h3', { text: 'Sem repositório Git' }),
    el('p', {
      class: 'field__hint',
      text: 'Esta pasta não tem repositório Git. Nada a mostrar aqui.',
    }),
  ]);
}

function summary(status) {
  const counts = Object.entries(status.counts ?? {}).filter(([, value]) => value > 0);

  return el('dl', { class: 'definition-list' }, [
    el('dt', { text: 'Branch' }),
    el('dd', {}, [
      status.detached
        ? el('span', { class: 'status-badge', dataset: { status: 'UNKNOWN' } }, [
            el('span', { class: 'status-badge__dot' }),
            'detached HEAD',
          ])
        : el('span', { class: 'mono', text: status.current_branch ?? '—' }),
    ]),

    el('dt', { text: 'Upstream' }),
    el('dd', {
      text:
        status.ahead === null && status.behind === null
          ? 'sem upstream configurado'
          : `${status.ahead ?? 0} à frente · ${status.behind ?? 0} atrás`,
    }),

    el('dt', { text: 'Alterações' }),
    el('dd', {
      text: counts.length
        ? counts.map(([key, value]) => `${value} ${COUNT_LABEL[key] ?? key}`).join(' · ')
        : 'nenhuma — árvore limpa',
    }),

    el('dt', { text: 'HEAD' }),
    el('dd', { class: 'mono', text: status.head_sha ?? '—' }),
  ]);
}

function fileTable(status) {
  if (!status.files.length) return null;

  return el('section', { style: 'margin-top:var(--sp-5)' }, [
    el('h3', { class: 'section-title', text: 'Arquivos alterados' }),
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'table' }, [
        el('thead', {}, [
          el('tr', {}, [
            el('th', { text: 'Arquivo' }),
            el('th', { text: 'Mudança' }),
            el('th', { text: 'Índice' }),
          ]),
        ]),
        el(
          'tbody',
          {},
          status.files.map((file) =>
            el('tr', {}, [
              el('td', { class: 'mono', text: file.path }),
              el('td', { text: CHANGE_LABEL[file.change] ?? file.change }),
              el('td', { text: file.staged ? 'sim' : '—' }),
            ])
          )
        ),
      ]),
    ]),
    status.files_truncated
      ? el('p', {
          class: 'field__hint',
          text: 'Lista truncada: há mais arquivos alterados do que os exibidos.',
        })
      : null,
  ]);
}

function commitTable(commits) {
  if (!commits.length) return null;

  return el('section', { style: 'margin-top:var(--sp-5)' }, [
    el('h3', { class: 'section-title', text: 'Commits recentes' }),
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'table' }, [
        el(
          'tbody',
          {},
          commits.map((commit) =>
            el('tr', {}, [
              el('td', { class: 'mono', text: commit.sha }),
              el('td', { text: commit.subject }),
              el('td', { text: commit.author }),
              el('td', { text: relativeTime(commit.date) }),
            ])
          )
        ),
      ]),
    ]),
  ]);
}

function remoteList(remotes) {
  if (!remotes.length) return null;

  return el('section', { style: 'margin-top:var(--sp-5)' }, [
    el('h3', { class: 'section-title', text: 'Remotes' }),
    el(
      'ul',
      {},
      remotes.map((remote) =>
        el('li', {}, [
          el('span', { class: 'mono', text: `${remote.name} ` }),
          el('span', { class: 'mono', text: remote.url }),
          remote.provider ? el('span', { class: 'tech-chip', text: remote.provider }) : null,
        ])
      )
    ),
  ]);
}

export async function renderGitPanel(container) {
  const projectId = container.dataset.projectId;
  container.replaceChildren(loading('Consultando o Git…'));

  let status;
  try {
    status = await api.gitStatus(projectId);
  } catch (error) {
    container.replaceChildren(
      el('div', { class: 'card' }, [
        el('h3', { text: 'Não foi possível ler o Git' }),
        el('p', { class: 'field__hint', text: error.message }),
      ])
    );
    return;
  }

  if (!status.is_repo) {
    container.replaceChildren(notARepo(status));
    return;
  }

  const [commits, remotes] = await Promise.all([
    api.gitCommits(projectId, 10).catch(() => ({ items: [] })),
    api.gitRemotes(projectId).catch(() => ({ items: [] })),
  ]);

  container.replaceChildren(
    el('div', { class: 'freshness', style: 'margin-bottom:var(--sp-3)' }, [
      el('span', {
        class: 'field__hint',
        text: `Estado lido ${relativeTime(status.checked_at)} · somente leitura`,
      }),
    ]),
    summary(status),
    fileTable(status),
    commitTable(commits.items),
    remoteList(remotes.items)
  );
}
