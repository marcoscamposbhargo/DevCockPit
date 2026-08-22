import { api } from './lib/api.js';
import { el, mount } from './lib/dom.js';
import { invalidateTools } from './lib/actions.js';
import { applyTheme, cycleTheme, getTheme, THEME_LABELS, watchSystemTheme } from './lib/theme.js';
import { emptyState } from './lib/ui.js';
import { renderActivity } from './pages/activity.js';
import { renderDashboard } from './pages/dashboard.js';
import { renderDiscovery } from './pages/discovery.js';
import { renderProject } from './pages/project.js';
import { renderProjects } from './pages/projects.js';
import { renderSettings } from './pages/settings.js';
import { navigate, register, setNotFound, start } from './router.js';

const view = document.getElementById('view');

register('dashboard', '/dashboard', renderDashboard);
register('projects', '/projects', renderProjects);
register('discovery', '/discovery', renderDiscovery);
register('project', '/projects/:id', renderProject);
register('activity', '/activity', renderActivity);
register('settings', '/settings', renderSettings);

setNotFound((container) => {
  mount(
    container,
    emptyState({
      iconName: 'alert',
      title: 'Página não encontrada',
      text: 'O endereço não corresponde a nenhuma tela.',
      actions: [
        el('button', {
          class: 'btn btn--primary',
          text: 'Ir para o Dashboard',
          onClick: () => navigate('/dashboard'),
        }),
      ],
    })
  );
});

function highlightNav(routeName) {
  const active = ['project', 'discovery'].includes(routeName) ? 'projects' : routeName;
  for (const link of document.querySelectorAll('.sidebar__nav .nav-item')) {
    if (link.dataset.route === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

async function refreshPinned() {
  const container = document.getElementById('pinned-list');
  try {
    const data = await api.listProjects({ pinned: true, limit: 20 });
    if (!data.items.length) {
      mount(container, el('span', { class: 'field__hint', text: 'Nenhum projeto fixado' }));
      return;
    }
    mount(
      container,
      ...data.items.map((project) =>
        el('a', {
          class: 'nav-item',
          href: `#/projects/${encodeURIComponent(project.id)}`,
          text: project.name,
        })
      )
    );
  } catch {
    mount(container, el('span', { class: 'field__hint', text: '—' }));
  }
}

async function refreshTools() {
  const indicator = document.getElementById('tools-indicator');
  try {
    // Descarta o cache de disponibilidade junto: senão uma leitura feita com o
    // servidor fora do ar (ou antes de instalar o `code`) manteria os botões
    // desabilitados até a página ser recarregada.
    invalidateTools();
    const health = await api.health();
    const marks = Object.entries(health.tools).map(([name, available]) =>
      el('span', {
        text: `${name}: ${available ? 'ok' : '—'}`,
        style: available ? '' : 'color:var(--status-warning)',
      })
    );
    mount(indicator, ...marks);
  } catch {
    mount(indicator, el('span', { text: 'servidor offline', style: 'color:var(--status-error)' }));
  }
}

function wireTheme() {
  const button = document.getElementById('theme-toggle');

  const desenha = () => {
    const preferencia = getTheme();
    button.textContent = `Tema: ${THEME_LABELS[preferencia]}`;
    button.title = 'Alternar entre sistema, escuro e claro';
  };

  applyTheme();
  watchSystemTheme();
  button.addEventListener('click', () => {
    cycleTheme();
    desenha();
  });
  window.addEventListener('devcockpit:theme-changed', desenha);
  desenha();
}

function wireSearch() {
  const search = document.getElementById('global-search');
  const naListaDeProjetos = () =>
    window.location.hash.split('?')[0].replace(/\/$/, '') === '#/projects';

  // Uma busca só na aplicação inteira. Estando em Projects ela filtra enquanto
  // se digita; de qualquer outra tela, Enter leva para lá com o termo aplicado.
  search.addEventListener('input', () => {
    if (naListaDeProjetos()) {
      window.dispatchEvent(new CustomEvent('devcockpit:search', { detail: search.value }));
    }
  });

  search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !naListaDeProjetos()) {
      const term = search.value.trim();
      navigate(term ? `/projects?q=${encodeURIComponent(term)}` : '/projects');
    }
    if (event.key === 'Escape') {
      search.value = '';
      if (naListaDeProjetos()) {
        window.dispatchEvent(new CustomEvent('devcockpit:search', { detail: '' }));
      }
      search.blur();
    }
  });

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      search.focus();
      search.select();
    }
    if (event.key === 'r' && !event.ctrlKey && !event.metaKey && document.activeElement === document.body) {
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    }
  });
}

wireTheme();
wireSearch();
window.addEventListener('devcockpit:projects-changed', refreshPinned);

await refreshTools();

// O PATH muda por fora (instalar o VS Code, subir o Docker Desktop) e a página
// costuma ficar aberta o dia inteiro. Uma consulta por minuto é barata e evita
// botão desabilitado por informação velha.
window.setInterval(refreshTools, 60_000);

await start(view, (match) => {
  highlightNav(match.name);
  refreshPinned();
});
