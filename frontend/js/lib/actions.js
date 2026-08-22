// Barra de ações do projeto (US-070 a US-072).
//
// Regra da UI: ação impossível aparece **desabilitada com o motivo**, nunca
// como um clique que falha depois. A disponibilidade das ferramentas vem de
// `GET /api/health`, consultado uma vez e reaproveitado.

import { api } from './api.js';
import { el } from './dom.js';
import { icon } from './icons.js';
import { showError, toast } from './ui.js';

const INDISPONIVEL = { git: false, docker: false, code: false };

let toolsPromise = null;

/** Disponibilidade das ferramentas, com cache **só do sucesso**.
 *
 * Guardar a falha era um bug de verdade: uma página aberta enquanto o servidor
 * estava fora do ar cacheava "nenhuma ferramenta existe" para sempre, e todos
 * os botões ficavam desabilitados até o usuário dar F5 — sem mensagem nenhuma,
 * só o cursor de bloqueado.
 */
export function tools() {
  if (toolsPromise === null) {
    toolsPromise = api
      .health()
      .then((health) => health.tools)
      .catch(() => {
        toolsPromise = null;
        return INDISPONIVEL;
      });
  }
  return toolsPromise;
}

/** Descarta o cache: a próxima consulta pergunta ao servidor de novo. */
export function invalidateTools() {
  toolsPromise = null;
}

async function run(label, fn) {
  try {
    await fn();
    toast(`${label}: ok.`, { kind: 'success' });
  } catch (error) {
    showError(error);
  }
}

const MOTIVO_DIR = 'O diretório deste projeto não existe mais.';

function toolActions(project, available) {
  const missing = project.status === 'MISSING';

  return [
    {
      label: 'VS Code',
      icon: 'code',
      enabled: available.code && !missing,
      reason: available.code ? MOTIVO_DIR : "'code' não está no PATH.",
      onClick: () => run('VS Code', () => api.openVsCode(project.id)),
    },
    {
      label: 'Pasta',
      icon: 'folder',
      enabled: !missing,
      reason: MOTIVO_DIR,
      onClick: () => run('Pasta', () => api.openFolder(project.id)),
    },
    {
      label: 'Terminal',
      icon: 'terminal',
      enabled: !missing,
      reason: MOTIVO_DIR,
      onClick: () => run('Terminal', () => api.openTerminal(project.id)),
    },
  ];
}

function toButton(botao, { size = '' } = {}) {
  return el(
    'button',
    {
      class: `btn${size}`,
      type: 'button',
      disabled: !botao.enabled,
      title: botao.enabled ? '' : botao.reason,
      onClick: botao.enabled ? botao.onClick : null,
    },
    [botao.icon ? icon(botao.icon, { size: size ? 13 : 15 }) : null, botao.label]
  );
}

/** Ferramentas direto no card da lista, sem entrar no projeto. */
export function quickTools(project, available) {
  return el(
    'div',
    { class: 'card__tools' },
    toolActions(project, available).map((botao) => toButton(botao, { size: ' btn--sm' }))
  );
}

export async function actionBar(project) {
  const available = await tools();
  const missing = project.status === 'MISSING';

  const botoes = toolActions(project, available);

  const abriveis = project.services.filter((service) => service.url || service.port);
  for (const service of abriveis.slice(0, 3)) {
    botoes.push({
      label: `Abrir ${service.label}`,
      icon: 'external',
      enabled: !missing,
      reason: MOTIVO_DIR,
      onClick: () => run(service.label, () => api.openBrowser(project.id, service.key)),
    });
  }

  return el('div', { class: 'card__footer' }, botoes.map((botao) => toButton(botao)));
}
