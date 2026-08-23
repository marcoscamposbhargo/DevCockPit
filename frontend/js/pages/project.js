import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { actionBar } from '../lib/actions.js';
import { powerToggle } from '../lib/power.js';
import { loading, pageHeader, showError, statusBadge, techChip, toast } from '../lib/ui.js';
import { navigate } from '../router.js';
import { renderDockerPanel } from './docker-panel.js';
import { renderGitPanel } from './git-panel.js';
import { renderManifestPanel } from './manifest-panel.js';
import { renderServerPanel } from './server-panel.js';
import { renderServicesPanel } from './services-panel.js';

const TABS = [
  { key: 'overview', label: 'Overview' },
  // Server vem antes de Docker porque é a aba do dia a dia: subir o backend e
  // ler o que ele cuspiu acontece dezenas de vezes; mexer em container, não.
  { key: 'server', label: 'Server' },
  { key: 'git', label: 'Git' },
  { key: 'docker', label: 'Docker' },
  { key: 'services', label: 'Services' },
  { key: 'manifest', label: 'Manifest' },
];

function overview(project, onDetect) {
  return el('section', {}, [
    el('dl', { class: 'definition-list' }, [
      el('dt', { text: 'Status' }),
      el('dd', {}, [statusBadge(project.status)]),

      el('dt', { text: 'Caminho' }),
      el('dd', { class: 'mono', text: project.path }),

      el('dt', { text: 'Stack' }),
      el(
        'dd',
        {},
        project.technologies.length
          ? [
              el(
                'div',
                { class: 'chip-row' },
                project.technologies.map((tech) => techChip(tech.name, tech.source))
              ),
            ]
          : ['Nenhuma tecnologia detectada.']
      ),

      el('dt', { text: 'Serviços' }),
      el(
        'dd',
        {},
        project.services.length
          ? [
              el(
                'ul',
                {},
                project.services.map((service) =>
                  el('li', {}, [
                    `${service.label}: `,
                    el('span', {
                      class: 'mono',
                      text: service.url ?? `localhost:${service.port ?? '—'}`,
                    }),
                    el('span', { class: 'field__hint', text: ` (${service.health_kind})` }),
                  ])
                )
              ),
              el('p', {
                class: 'field__hint',
                text: 'O estado de cada serviço fica na aba Services.',
              }),
            ]
          : ['Nenhum serviço detectado.']
      ),

      el('dt', { text: 'Detecção' }),
      el('dd', {}, [
        el('button', {
          class: 'btn btn--sm',
          onClick: onDetect,
          text: 'Reexecutar detecção',
        }),
        project.detection_locked
          ? el('span', {
              class: 'field__hint',
              style: 'margin-left:var(--sp-2)',
              text: 'stack travada: a detecção não sobrescreve suas edições',
            })
          : null,
      ]),

      el('dt', { text: 'Último acesso' }),
      el('dd', { text: relativeTime(project.last_accessed_at) }),
    ]),
  ]);
}

function missingBanner(project) {
  if (project.status !== 'MISSING') return null;

  return el('div', { class: 'card card--missing' }, [
    el('h3', { text: 'O diretório deste projeto não existe mais' }),
    el('p', { class: 'field__hint' }, [
      'O caminho ',
      el('span', { class: 'mono', text: project.path }),
      ' não foi encontrado. As ações ficam desabilitadas até que ele volte, ' +
        'ou você pode remover o registro.',
    ]),
  ]);
}

export async function renderProject(container, params, query) {
  mount(container, loading());

  let project;
  try {
    project = await api.getProject(params.id);
  } catch (error) {
    showError(error);
    mount(
      container,
      el('p', { class: 'loading', text: error.message }),
      el('a', { href: '#/projects', text: '← Voltar para Projects' })
    );
    return;
  }

  const activeTab = TABS.some((tab) => tab.key === query.tab) ? query.tab : 'overview';

  // Quantos serviços responderam na última verificação. Vem do cache dos
  // serviços do próprio projeto — abrir a página do projeto já é o momento em
  // que essa leitura é barata e esperada.
  let online = 0;
  try {
    const estado = await api.listServices(project.id);
    online = estado.items.filter((item) => item.state === 'ONLINE').length;
  } catch {
    /* sem o estado, a chave começa em "desligado" e o clique ainda funciona. */
  }

  const togglePin = async () => {
    try {
      await api.updateProject(project.id, { is_pinned: !project.is_pinned });
      toast(project.is_pinned ? 'Projeto desafixado.' : 'Projeto fixado na sidebar.', {
        kind: 'success',
      });
      window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
      renderProject(container, params, query);
    } catch (error) {
      showError(error);
    }
  };

  const runDetection = async () => {
    try {
      const diff = await api.detectProject(project.id);
      if (diff.skipped) {
        toast('Detecção ignorada: a stack deste projeto está travada.');
      } else if (diff.added.length || diff.removed.length || diff.services_added.length) {
        toast(
          `Detecção: +${diff.added.length} tecnologia(s), −${diff.removed.length}, ` +
            `+${diff.services_added.length} serviço(s).`,
          { kind: 'success' }
        );
      } else {
        toast('Detecção executada. Nada mudou.');
      }

      // Divergência de porta vem em toast próprio, e não misturada na contagem
      // acima: "nada mudou" era literalmente verdade — a detecção não
      // sobrescreve o cadastro — e ao mesmo tempo escondia que o painel está
      // verificando um número que o arquivo do projeto abandonou.
      for (const drift of diff.port_drift ?? []) {
        toast(`${drift.label}: o projeto usa a porta ${drift.detected}.`, {
          kind: 'warning',
          meta:
            `O cadastro diz ${drift.declared}, então é essa que o painel verifica. ` +
            'Troque em Ports para os dois baterem.',
        });
      }

      for (const warning of diff.warnings ?? []) toast(warning, { kind: 'error' });
      renderProject(container, params, query);
    } catch (error) {
      showError(error);
    }
  };

  const tabBar = el(
    'nav',
    { class: 'tabs', 'aria-label': 'Seções do projeto' },
    TABS.map((tab) =>
      el('a', {
        class: 'tab',
        href: `#/projects/${encodeURIComponent(project.id)}?tab=${tab.key}`,
        text: tab.label,
        'aria-current': tab.key === activeTab ? 'page' : null,
      })
    )
  );

  const panel = el('div', { class: 'tab-panel', dataset: { projectId: project.id } });

  mount(
    container,
    pageHeader({
      title: project.name,
      subtitle: project.path,
      actions: [
        powerToggle(project, {
          on: online > 0,
          onChanged: () => renderProject(container, params, query),
        }),
        el('button', {
          class: 'btn',
          onClick: togglePin,
          text: project.is_pinned ? 'Desafixar' : 'Fixar',
        }),
        el('button', { class: 'btn', onClick: () => navigate('/projects'), text: '← Projects' }),
      ],
    }),
    missingBanner(project),
    tabBar,
    panel
  );

  if (activeTab === 'server') {
    await renderServerPanel(panel);
  } else if (activeTab === 'git') {
    await renderGitPanel(panel);
  } else if (activeTab === 'docker') {
    await renderDockerPanel(panel);
  } else if (activeTab === 'services') {
    await renderServicesPanel(panel);
  } else if (activeTab === 'manifest') {
    await renderManifestPanel(panel);
  } else {
    panel.append(overview(project, runDetection));
    panel.append(
      el('section', { style: 'margin-top:var(--sp-5)' }, [
        el('h2', { class: 'section-title', text: 'Ações' }),
        await actionBar(project),
      ])
    );
  }
}
