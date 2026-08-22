// Tema claro/escuro.
//
// A preferência é do navegador desta máquina, não do banco: é ajuste de quem
// olha a tela, não configuração do projeto. Guardar no servidor obrigaria uma
// rota de escrita para mudar cor de fundo.

const STORAGE_KEY = 'devcockpit:theme';
const VALUES = ['system', 'dark', 'light'];

export const THEME_LABELS = {
  system: 'Sistema',
  dark: 'Escuro',
  light: 'Claro',
};

export function getTheme() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return VALUES.includes(stored) ? stored : 'system';
  } catch {
    // Janela anônima com armazenamento bloqueado não pode derrubar a UI.
    return 'system';
  }
}

export function resolvedTheme(preference = getTheme()) {
  if (preference !== 'system') return preference;
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function applyTheme(preference = getTheme()) {
  document.documentElement.dataset.theme = resolvedTheme(preference);
  document.documentElement.dataset.themePreference = preference;
  return preference;
}

export function setTheme(preference) {
  const valor = VALUES.includes(preference) ? preference : 'system';
  try {
    window.localStorage.setItem(STORAGE_KEY, valor);
  } catch {
    // Sem persistência, o tema vale só para esta sessão. Melhor que quebrar.
  }
  applyTheme(valor);
  window.dispatchEvent(new CustomEvent('devcockpit:theme-changed', { detail: valor }));
  return valor;
}

export function cycleTheme() {
  const atual = getTheme();
  return setTheme(VALUES[(VALUES.indexOf(atual) + 1) % VALUES.length]);
}

export function watchSystemTheme() {
  window
    .matchMedia?.('(prefers-color-scheme: light)')
    .addEventListener('change', () => {
      if (getTheme() === 'system') applyTheme('system');
    });
}

export { VALUES as THEME_VALUES };
