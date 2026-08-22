// Estado do casco da aplicação: barra lateral recolhida e trilho de ativos.
//
// Fica em `localStorage`, não no banco: é preferência de quem olha a tela
// naquele monitor, igual ao tema. Uma mesma pessoa quer a lateral aberta no
// monitor grande e recolhida no notebook.

const CHAVE_SIDEBAR = 'devcockpit:sidebar';
const CHAVE_RAIL = 'devcockpit:rail';

const shell = () => document.querySelector('.app-shell');

function ler(chave, padrao) {
  try {
    return window.localStorage.getItem(chave) ?? padrao;
  } catch {
    return padrao;
  }
}

function gravar(chave, valor) {
  try {
    window.localStorage.setItem(chave, valor);
  } catch {
    /* modo privado: a sessão funciona, só não lembra na próxima. */
  }
}

export function sidebarCollapsed() {
  return ler(CHAVE_SIDEBAR, 'expanded') === 'collapsed';
}

export function railHidden() {
  return ler(CHAVE_RAIL, 'shown') === 'hidden';
}

/** Escreve o estado no casco. O CSS lê `data-*`; nenhum componente sabe disso. */
export function applyShell() {
  const raiz = shell();
  if (!raiz) return;
  raiz.dataset.sidebar = sidebarCollapsed() ? 'collapsed' : 'expanded';
  raiz.dataset.rail = railHidden() ? 'hidden' : 'shown';
}

export function toggleSidebar() {
  gravar(CHAVE_SIDEBAR, sidebarCollapsed() ? 'expanded' : 'collapsed');
  applyShell();
  window.dispatchEvent(new CustomEvent('devcockpit:shell-changed'));
}

export function toggleRail() {
  gravar(CHAVE_RAIL, railHidden() ? 'shown' : 'hidden');
  applyShell();
  window.dispatchEvent(new CustomEvent('devcockpit:shell-changed'));
}
