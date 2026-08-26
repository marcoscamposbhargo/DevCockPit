import { api } from './lib/api.js';
import { el, mount } from './lib/dom.js';
import { invalidateTools, tools } from './lib/actions.js';
import { icon } from './lib/icons.js';
import { toggleQuickAsk, wireQuickAsk } from './lib/quick-ask.js';
import { mountRail } from './lib/rail.js';
import { applyShell, railHidden, sidebarCollapsed, toggleRail, toggleSidebar } from './lib/shell.js';
import { applyTheme, cycleTheme, getTheme, THEME_LABELS, watchSystemTheme } from './lib/theme.js';
import { shortcutsHint, wireShortcuts } from './lib/shortcuts.js';
import { emptyState, showError, toast } from './lib/ui.js';
import { renderActivity } from './pages/activity.js';
import { renderDashboard } from './pages/dashboard.js';
import { renderDay } from './pages/day.js';
import { renderDiscovery } from './pages/discovery.js';
import { renderHyperbrain } from './pages/hyperbrain.js';
import { renderProject } from './pages/project.js';
import { renderPorts } from './pages/ports.js';
import { renderProjects } from './pages/projects.js';
import { renderSettings } from './pages/settings.js';
import { navigate, register, setNotFound, start } from './router.js';

const view = document.getElementById('view');

register('day', '/day', renderDay);
register('dashboard', '/dashboard', renderDashboard);
register('projects', '/projects', renderProjects);
register('discovery', '/discovery', renderDiscovery);
register('project', '/projects/:id', renderProject);
register('hyperbrain', '/hyperbrain', renderHyperbrain);
register('ports', '/ports', renderPorts);
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

/** Ícone e rótulo dos itens de navegação.
 *
 * O ícone é montado aqui, não no HTML: `icons.js` desenha SVG por função, e a
 * regra da casa é que `innerHTML` nunca recebe marcação — nem a nossa. Com a
 * barra recolhida o ícone é a única pista visível, então ele precisa existir
 * antes do primeiro clique, não depois da primeira rota.
 */
function decorateNav() {
  for (const link of document.querySelectorAll('.sidebar__nav .nav-item')) {
    const nome = link.dataset.icon;
    if (!nome || link.querySelector('.icon')) continue;
    link.prepend(icon(nome, { size: 16 }));
    // Com a barra recolhida o rótulo some da tela; o title é o que sobra para
    // quem passa o mouse, e o aria-label para quem usa leitor.
    const rotulo = link.textContent.trim();
    link.title = rotulo;
    link.setAttribute('aria-label', rotulo);
  }
}

/** Botão do VS Code na barra superior.
 *
 * Existe para o começo do dia: liga a máquina, abre o DevCockpit e abre o
 * editor sem ter que escolher um projeto antes. Abre vazio — o VS Code
 * restaura a última sessão sozinho. Quem quer um projeto específico continua
 * usando o botão do card, que manda o caminho.
 *
 * Fica na barra superior porque a lateral recolhida esconde as seções de
 * texto, e um atalho de todo dia não pode mudar de lugar conforme o estado da
 * barra.
 */
async function wireEditorButton() {
  const botao = document.getElementById('open-editor');
  botao.replaceChildren(icon('code', { size: 15 }));

  botao.addEventListener('click', async () => {
    botao.disabled = true;
    try {
      await api.openEditor();
      toast('VS Code: ok.', { kind: 'success' });
    } catch (error) {
      showError(error);
    } finally {
      botao.disabled = false;
    }
  });

  // Sem o `code` no PATH o botão não some — fica desabilitado **com o motivo**,
  // que é a regra da casa para ação impossível.
  const disponiveis = await tools();
  if (!disponiveis.code) {
    botao.disabled = true;
    botao.title = "'code' não está no PATH. No VS Code, use 'Shell Command: Install code command in PATH'.";
  }
}

/** Botão da pergunta rápida, ao lado do VS Code.
 *
 * O chat da aba IA fala *de um projeto*; este fala de nada — é a dúvida de
 * terminal que aparece no meio do trabalho. Por isso mora na barra superior,
 * alcançável de qualquer tela, e não dentro de um projeto.
 */
function wireQuickAskButton() {
  const botao = document.getElementById('quick-ask');
  botao.replaceChildren(icon('terminal', { size: 15 }));
  botao.addEventListener('click', toggleQuickAsk);
}

function wireShell() {
  const sidebarBtn = document.getElementById('sidebar-toggle');
  const railBtn = document.getElementById('rail-toggle');
  //: `null` até a primeira carga do trilho: "—" é honesto, "0" seria mentira.
  let ativosNoAr = null;

  applyShell();
  decorateNav();

  const desenha = () => {
    const recolhida = sidebarCollapsed();
    sidebarBtn.replaceChildren(icon('sidebar', { size: 15 }));
    sidebarBtn.title = `${recolhida ? 'Expandir' : 'Recolher'} a barra lateral (Ctrl+B)`;
    sidebarBtn.setAttribute('aria-expanded', recolhida ? 'false' : 'true');
    sidebarBtn.setAttribute(
      'aria-label',
      recolhida ? 'Expandir a barra lateral' : 'Recolher a barra lateral'
    );

    // O botão do trilho é rotulado, e não um ícone mudo. Fechado, um ícone
    // sozinho na topbar não conta a ninguém que é ele quem traz a barra de
    // volta: fechar era óbvio (o X está dentro da barra) e reabrir virava
    // caça ao tesouro. Com o rótulo e a contagem ele também vira o resumo de
    // "quantos estão no ar" — que é o que a barra responderia se estivesse
    // aberta.
    const aberta = !railHidden();
    railBtn.replaceChildren(
      icon('layers', { size: 14 }),
      el('span', { class: 'rail-switch__label', text: 'Ativos' }),
      el('span', { class: 'rail-switch__count', text: ativosNoAr === null ? '—' : String(ativosNoAr) })
    );
    railBtn.dataset.open = aberta ? 'true' : 'false';
    railBtn.setAttribute('aria-pressed', aberta ? 'true' : 'false');
    railBtn.setAttribute('aria-label', aberta ? 'Ocultar os projetos ativos' : 'Mostrar os projetos ativos');
    railBtn.title = `${aberta ? 'Ocultar' : 'Mostrar'} os projetos ativos (Ctrl+Alt+B)`;
  };

  sidebarBtn.addEventListener('click', toggleSidebar);
  railBtn.addEventListener('click', toggleRail);
  window.addEventListener('devcockpit:shell-changed', desenha);
  // O trilho anuncia quantos estão no ar a cada recarga. O botão mostra esse
  // número mesmo com a barra fechada — senão fechar a barra também apagaria a
  // informação, e aí ela só serviria aberta.
  window.addEventListener('devcockpit:rail-count', (event) => {
    ativosNoAr = event.detail;
    desenha();
  });
  desenha();

  document.addEventListener('keydown', (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'b') return;
    event.preventDefault();
    // Ctrl+B esconde a lateral em todo editor, e Ctrl+Alt+B o painel
    // secundário. Herdar os dois gestos custa menos que ensinar dois novos.
    if (event.altKey) toggleRail();
    else toggleSidebar();
  });
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

wireShell();
wireTheme();
wireSearch();
wireShortcuts();
wireEditorButton();
wireQuickAskButton();
wireQuickAsk();

// A dica mora no rodapé da lateral, ao lado do estado das ferramentas: é o
// canto onde já se olha para saber "como está o ambiente", e o custo visual de
// mais uma linha ali é zero.
document.querySelector('.sidebar__footer')?.prepend(shortcutsHint());
mountRail();
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
