// Componentes compartilhados entre páginas.

import { el } from './dom.js';
import { statusLabel } from './format.js';
import { icon } from './icons.js';

export function statusBadge(status) {
  return el('span', { class: 'status-badge', dataset: { status } }, [
    el('span', { class: 'status-badge__dot' }),
    statusLabel(status),
  ]);
}

export function techChip(name, source = 'DETECTED') {
  return el('span', { class: 'tech-chip', dataset: { source }, text: name });
}

/** Número do dashboard. Zero fica apagado: só chama atenção o que exige ação. */
export function statCard(value, label, { tone = null } = {}) {
  const vazio = Number(value) === 0;
  return el('div', { class: 'stat-card', dataset: { tone, empty: String(vazio) } }, [
    el('div', { class: 'stat-card__value', text: String(value) }),
    el('div', { class: 'stat-card__label', text: label }),
  ]);
}

export function emptyState({ iconName = 'inbox', title, text, actions = [] }) {
  return el('div', { class: 'empty-state' }, [
    el('div', { class: 'empty-state__icon' }, [icon(iconName, { size: 22 })]),
    el('h2', { text: title }),
    text ? el('p', { class: 'empty-state__text', text }) : null,
    actions.length ? el('div', { class: 'card__footer' }, actions) : null,
  ]);
}

export function loading(text = 'Carregando…') {
  return el('div', { class: 'loading', text });
}

/** Esqueleto na forma do conteúdo que vem, para a página não pular ao chegar. */
export function skeletonGrid(count = 6) {
  return el(
    'div',
    { class: 'grid-cards', 'aria-hidden': 'true' },
    Array.from({ length: count }, () => el('div', { class: 'skeleton-card' }))
  );
}

export function pageHeader({ title, subtitle, actions = [] }) {
  return el('header', { class: 'page-header' }, [
    el('div', { class: 'page-header__text' }, [
      el('h1', { text: title }),
      subtitle ? el('p', { class: 'page-header__subtitle', text: subtitle }) : null,
    ]),
    actions.length ? el('div', { class: 'page-header__actions' }, actions) : null,
  ]);
}

const TOAST_ICON = { success: 'check', error: 'alert', warning: 'alert', info: 'pulse' };

//: Quanto tempo cada tom fica na tela. Erro e aviso duram mais porque pedem
//: uma decisão; confirmação de sucesso já cumpriu o papel ao aparecer.
const TOAST_DURACAO = { error: 8000, warning: 8000 };
const TOAST_DURACAO_PADRAO = 4000;

export function toast(message, { kind = 'info', meta } = {}) {
  const container = document.getElementById('toasts');
  const node = el('div', { class: `toast toast--${kind}`, role: 'status', 'aria-live': 'polite' }, [
    el('span', { class: 'toast__icon' }, [icon(TOAST_ICON[kind] ?? 'pulse', { size: 14 })]),
    el('div', { class: 'toast__body' }, [
      el('div', { text: message }),
      meta ? el('div', { class: 'toast__meta', text: meta }) : null,
    ]),
  ]);
  container.append(node);

  // O temporizador é por aviso, não um só para todos. Com uma variável de
  // módulo, dois avisos seguidos faziam o segundo sobrescrever o identificador
  // do primeiro: o primeiro ficava na tela para sempre, e a função de fechar
  // devolvida por ele passava a cancelar o tempo do vizinho.
  const temporizador = window.setTimeout(
    () => node.remove(),
    TOAST_DURACAO[kind] ?? TOAST_DURACAO_PADRAO
  );
  return () => {
    window.clearTimeout(temporizador);
    node.remove();
  };
}

export function showError(error) {
  toast(error.message ?? 'Erro inesperado.', {
    kind: 'error',
    meta: error.correlationId ? `correlation_id: ${error.correlationId}` : undefined,
  });
}
