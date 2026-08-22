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

/** Largura abaixo da qual o trilho vira gaveta sobreposta (espelha layout.css). */
const LARGURA_GAVETA = 1100;

export function railHidden() {
  const gravado = ler(CHAVE_RAIL, null);
  if (gravado !== null) return gravado === 'hidden';

  // Sem preferência gravada, o padrão depende do espaço: numa janela estreita
  // o trilho é uma gaveta que cobre o conteúdo, e abrir por conta própria em
  // cima do que a pessoa veio ler é o comportamento errado. Numa janela larga
  // ele é uma coluna e aparece de saída, que é a razão de existir.
  try {
    return window.innerWidth < LARGURA_GAVETA;
  } catch {
    return false;
  }
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
