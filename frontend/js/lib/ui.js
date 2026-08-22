// Componentes compartilhados entre páginas.

import { el } from './dom.js';
import { statusLabel } from './format.js';

export function statusBadge(status) {
  return el('span', { class: 'status-badge', dataset: { status } }, [
    el('span', { class: 'status-badge__dot' }),
    statusLabel(status),
  ]);
}

export function techChip(name, source = 'DETECTED') {
  return el('span', { class: 'tech-chip', dataset: { source }, text: name });
}

export function statCard(value, label) {
  return el('div', { class: 'stat-card' }, [
    el('div', { class: 'stat-card__value', text: String(value) }),
    el('div', { class: 'stat-card__label', text: label }),
  ]);
}

export function emptyState({ icon = '◌', title, text, actions = [] }) {
  return el('div', { class: 'empty-state' }, [
    el('div', { class: 'empty-state__icon', text: icon }),
    el('h2', { text: title }),
    text ? el('p', { class: 'empty-state__text', text }) : null,
    actions.length ? el('div', { class: 'card__footer' }, actions) : null,
  ]);
}

export function loading(text = 'Carregando…') {
  return el('div', { class: 'loading', text });
}

export function pageHeader({ title, subtitle, actions = [] }) {
  return el('header', { class: 'page-header' }, [
    el('div', { class: 'page-header__text' }, [
      el('h1', { text: title }),
      subtitle ? el('p', { class: 'card__path', text: subtitle }) : null,
    ]),
    actions.length ? el('div', { class: 'page-header__actions' }, actions) : null,
  ]);
}

let toastTimer = 0;

export function toast(message, { kind = 'info', meta } = {}) {
  const container = document.getElementById('toasts');
  const node = el('div', { class: `toast toast--${kind}` }, [
    el('div', { text: message }),
    meta ? el('div', { class: 'toast__meta', text: meta }) : null,
  ]);
  container.append(node);

  toastTimer = window.setTimeout(() => node.remove(), kind === 'error' ? 8000 : 4000);
  return () => {
    window.clearTimeout(toastTimer);
    node.remove();
  };
}

export function showError(error) {
  toast(error.message ?? 'Erro inesperado.', {
    kind: 'error',
    meta: error.correlationId ? `correlation_id: ${error.correlationId}` : undefined,
  });
}
