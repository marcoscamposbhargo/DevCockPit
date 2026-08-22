// Trilho de projetos, à direita da barra lateral.
//
// Existe para responder "o que está de pé agora?" sem sair da tela em que se
// está. Antes essa resposta exigia abrir Projects (ou o Dashboard) e ler uma
// tabela — três cliques para saber se o Postgres do projeto ainda estava no ar.
//
// Nada aqui verifica nada: o trilho lê o mesmo cache agregado que o dashboard
// serve (`GET /api/dashboard`). Um painel sempre visível **não pode** disparar
// verificação de rede por projeto (NFR-010/NFR-011).

import { api } from './api.js';
import { el, mount } from './dom.js';
import { icon } from './icons.js';
import { hasDocker, powerToggle } from './power.js';
import { toggleRail } from './shell.js';
import { showError, toast } from './ui.js';

const RECARGA_MS = 30_000;

let ultimoDesenho = null;
let timer = 0;

function projetoHref(id) {
  return `#/projects/${encodeURIComponent(id)}`;
}

/** Ações que valem um clique só daqui: abrir o editor e abrir o serviço. */
function railActions(project, servico) {
  const missing = project.status === 'MISSING';

  const abrir = async (label, fn) => {
    try {
      await fn();
    } catch (error) {
      showError(error);
      return;
    }
    toast(`${label}: ok.`, { kind: 'success' });
  };

  return el('div', { class: 'rail-card__actions' }, [
    el(
      'button',
      {
        class: 'btn btn--sm btn--icon',
        type: 'button',
        title: missing ? 'O diretório deste projeto não existe mais.' : 'Abrir no VS Code',
        'aria-label': `Abrir ${project.name} no VS Code`,
        disabled: missing,
        onClick: missing ? null : () => abrir('VS Code', () => api.openVsCode(project.id)),
      },
      [icon('code', { size: 13 })]
    ),
    servico
      ? el(
          'button',
          {
            class: 'btn btn--sm btn--icon',
            type: 'button',
            title: `Abrir ${servico.label} no navegador`,
            'aria-label': `Abrir ${servico.label} de ${project.name}`,
            onClick: () => abrir(servico.label, () => api.openBrowser(project.id, servico.key)),
          },
          [icon('external', { size: 13 })]
        )
      : null,
  ]);
}

function railCard(project, { online, total, servico, git, onChanged }) {
  const ligado = online > 0;
  const estado = project.status === 'MISSING' ? 'missing' : ligado ? 'on' : 'off';

  return el('article', { class: 'rail-card', dataset: { state: estado } }, [
    el('div', { class: 'rail-card__head' }, [
      el('span', { class: 'rail-card__dot', 'aria-hidden': 'true' }),
      el('a', {
        class: 'rail-card__name',
        href: projetoHref(project.id),
        text: project.name,
        title: project.path,
      }),
    ]),

    el('div', { class: 'rail-card__meta' }, [
      total > 0
        ? el('span', {
            class: 'rail-card__count',
            text: `${online}/${total} online`,
            title: `${online} de ${total} serviço(s) responderam na última verificação.`,
          })
        : el('span', { class: 'rail-card__count', text: 'sem serviço declarado' }),
      git && git.dirty_count > 0
        ? el('span', {
            class: 'rail-card__git',
            text: `${git.branch ?? 'HEAD'} · ${git.dirty_count}`,
            title: `${git.dirty_count} arquivo(s) com alteração pendente.`,
          })
        : null,
    ]),

    el('div', { class: 'rail-card__foot' }, [
      powerToggle(project, { on: ligado, compact: true, onChanged }),
      railActions(project, servico),
    ]),
  ]);
}

function railSection(titulo, cards, { dica = null } = {}) {
  if (!cards.length && !dica) return null;
  return el('section', { class: 'rail__section' }, [
    el('h2', { class: 'rail__heading' }, [titulo, el('span', { text: String(cards.length) })]),
    cards.length ? el('div', { class: 'rail__cards' }, cards) : el('p', { class: 'rail__empty', text: dica }),
  ]);
}

/** Cruza a lista de projetos com o cache do dashboard. */
function combinar(projetos, dashboard) {
  const online = new Map();
  const servico = new Map();
  const git = new Map();

  for (const item of dashboard?.active_services ?? []) {
    online.set(item.project_id, (online.get(item.project_id) ?? 0) + 1);
    if (!servico.has(item.project_id) && (item.url || item.port)) {
      // O primeiro serviço com endereço é o que o botão "abrir" usa: numa
      // stack web é quase sempre o front, que é o que se quer ver.
      servico.set(item.project_id, item);
    }
  }
  for (const item of dashboard?.pending_changes ?? []) git.set(item.project_id, item);

  return projetos.map((project) => ({
    project,
    online: online.get(project.id) ?? 0,
    total: project.services_total ?? 0,
    servico: servico.get(project.id) ?? null,
    git: git.get(project.id) ?? null,
  }));
}

export async function refreshRail() {
  const raiz = document.getElementById('project-rail');
  if (!raiz) return;

  const corpo = raiz.querySelector('.rail__body');
  const contador = raiz.querySelector('.rail__badge');

  let linhas;
  try {
    const [lista, dashboard] = await Promise.all([
      api.listProjects({ limit: 200 }),
      api.dashboard().catch(() => null),
    ]);
    linhas = combinar(lista.items, dashboard);
  } catch {
    mount(corpo, el('p', { class: 'rail__empty', text: 'Servidor fora do ar.' }));
    contador.textContent = '—';
    window.dispatchEvent(new CustomEvent('devcockpit:rail-count', { detail: null }));
    return;
  }

  const onChanged = () => {
    // O estado real só aparece depois que o verificador roda de novo; até lá o
    // botão mostra o estado otimista e o trilho se corrige na próxima carga.
    window.setTimeout(refreshRail, 2000);
  };

  const ativos = linhas.filter((linha) => linha.online > 0);
  const ativosIds = new Set(ativos.map((linha) => linha.project.id));

  // Fixado que não está no ar continua no trilho: é justamente onde se quer
  // dar o clique de ligar.
  const dormindo = linhas.filter(
    (linha) => !ativosIds.has(linha.project.id) && linha.project.is_pinned
  );

  contador.textContent = String(ativos.length);
  // O botão da topbar mostra este número mesmo com o trilho fechado.
  window.dispatchEvent(new CustomEvent('devcockpit:rail-count', { detail: ativos.length }));

  mount(
    corpo,
    railSection('No ar', ativos.map((l) => railCard(l.project, { ...l, onChanged })), {
      dica: 'Nenhum serviço respondeu na última verificação.',
    }),
    railSection('Fixados', dormindo.map((l) => railCard(l.project, { ...l, onChanged })))
  );

  if (!ativos.length && !dormindo.length) {
    mount(
      corpo,
      el('p', {
        class: 'rail__empty',
        text: 'Fixe um projeto para acompanhá-lo aqui sem abrir a lista.',
      })
    );
  }

  ultimoDesenho = Date.now();
}

export function mountRail() {
  const raiz = document.getElementById('project-rail');
  if (!raiz) return;

  mount(
    raiz,
    el('header', { class: 'rail__header' }, [
      el('h2', { class: 'rail__title', text: 'Ativos' }),
      el('span', { class: 'rail__badge', text: '—' }),
      el(
        'button',
        {
          class: 'rail__icon-btn',
          type: 'button',
          title: 'Recarregar o trilho',
          'aria-label': 'Recarregar o trilho de projetos',
          onClick: () => refreshRail(),
        },
        [icon('refresh', { size: 13 })]
      ),
      el(
        'button',
        {
          class: 'rail__icon-btn',
          type: 'button',
          title: 'Ocultar o trilho',
          'aria-label': 'Ocultar o trilho de projetos',
          onClick: toggleRail,
        },
        [icon('close', { size: 13 })]
      ),
    ]),
    el('div', { class: 'rail__body' })
  );

  refreshRail();

  window.addEventListener('devcockpit:projects-changed', refreshRail);

  if (timer) window.clearInterval(timer);
  timer = window.setInterval(() => {
    // A aba escondida não precisa de dado fresco, e o cache do servidor tem
    // TTL próprio: recarregar em background só gasta bateria.
    if (document.visibilityState === 'visible') refreshRail();
  }, RECARGA_MS);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    if (!ultimoDesenho || Date.now() - ultimoDesenho > RECARGA_MS) refreshRail();
  });
}
