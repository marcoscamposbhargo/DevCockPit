import { quickTools, tools } from '../lib/actions.js';
import { api, ApiError } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { hasDocker, powerToggle } from '../lib/power.js';
import {
  emptyState,
  pageHeader,
  showError,
  skeletonGrid,
  statusBadge,
  techChip,
  toast,
} from '../lib/ui.js';
import { navigate } from '../router.js';

/** Sinais por projeto, cruzados do dashboard — que já vem de cache.
 *
 * O dashboard é a única fonte que sabe o estado observado sem tocar disco,
 * Git ou Docker. Listar projetos não pode disparar verificação de rede
 * (NFR-010), então o que não estiver no cache simplesmente não aparece —
 * melhor um card sem o sinal do que uma tela que trava para montá-lo.
 */
function buildSignals(dashboard) {
  const online = new Map();
  const git = new Map();

  for (const service of dashboard?.active_services ?? []) {
    online.set(service.project_id, (online.get(service.project_id) ?? 0) + 1);
  }
  for (const change of dashboard?.pending_changes ?? []) {
    git.set(change.project_id, change);
  }

  return { online, git };
}

const SIGNAL_ICON = { docker: 'container', dirty: 'branch', clean: 'branch' };

function signal(kind, text, title) {
  const marca = SIGNAL_ICON[kind]
    ? icon(SIGNAL_ICON[kind], { size: 12 })
    : el('span', { class: 'signal__dot' });

  return el('span', { class: 'signal', dataset: { kind }, title: title ?? '' }, [marca, text]);
}

/** A linha que faltava no card: o que está de pé, sem abrir o projeto. */
function signalRow(project, signals) {
  const chips = [];

  const total = project.services_total ?? 0;
  const online = signals.online.get(project.id) ?? 0;

  if (total > 0) {
    const kind = online === 0 ? 'off' : online >= total ? 'on' : 'partial';
    chips.push(
      signal(
        kind,
        `${online}/${total} online`,
        online === 0
          ? 'Nenhum serviço respondeu na última verificação.'
          : `${online} de ${total} serviço(s) responderam na última verificação.`
      )
    );
  }

  if (hasDocker(project)) {
    chips.push(signal('docker', 'Docker', 'Este projeto tem Compose ou Dockerfile.'));
  }

  const change = signals.git.get(project.id);
  if (change) {
    const sujo = change.dirty_count > 0;
    chips.push(
      signal(
        sujo ? 'dirty' : 'clean',
        sujo ? `${change.branch ?? 'HEAD'} · ${change.dirty_count}` : (change.branch ?? 'HEAD'),
        sujo
          ? `${change.dirty_count} arquivo(s) com alteração pendente.`
          : 'Sem alteração pendente.'
      )
    );
  }

  if (!chips.length) {
    chips.push(
      signal('off', 'sem serviço declarado', 'Nenhum serviço cadastrado neste projeto.')
    );
  }

  return el('div', { class: 'signal-row' }, chips);
}

/** Caminho legível: a pasta e o pai, com o path inteiro no tooltip.
 *
 * O path completo ocupava três linhas do card e empurrava para baixo tudo que
 * importa. Quem precisa do caminho inteiro passa o mouse ou abre o projeto.
 */
function compactPath(path) {
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  const tail = parts.slice(-2).join('/');
  return el('div', {
    class: 'card__path card__path--compact',
    text: parts.length > 2 ? `…/${tail}` : tail,
    title: path,
  });
}

function pinButton(project, onToggle) {
  return el('button', {
    class: `pin${project.is_pinned ? ' pin--on' : ''}`,
    type: 'button',
    title: project.is_pinned ? 'Desafixar' : 'Fixar no topo',
    'aria-pressed': project.is_pinned ? 'true' : 'false',
    'aria-label': project.is_pinned ? `Desafixar ${project.name}` : `Fixar ${project.name}`,
    onClick: () => onToggle(project),
  }, [icon('pin', { size: 14 })]);
}

/** Estado observado do projeto, resumido em uma palavra.
 *
 * É o que a faixa lateral colorida do card pinta. Existe para que uma grade de
 * vinte projetos se leia pela borda, antes de qualquer texto: o olho encontra
 * o que está de pé sem percorrer chip por chip.
 */
function liveState(project, signals) {
  if (project.status === 'MISSING') return 'missing';
  const total = project.services_total ?? 0;
  const online = signals.online.get(project.id) ?? 0;
  if (total === 0) return 'none';
  if (online === 0) return 'off';
  return online >= total ? 'on' : 'partial';
}

/** Monograma do projeto: âncora visual à esquerda do nome.
 *
 * Numa grade densa, todos os cards começam com um bloco de texto do mesmo
 * tamanho e o olho não tem onde pousar. Duas letras com cor derivada do nome
 * dão a cada card uma silhueta própria, e reencontrar um projeto conhecido
 * passa a ser reconhecimento em vez de leitura.
 */
function monogram(project) {
  const letras = String(project.name)
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  // Hash estável do nome: o mesmo projeto tem sempre o mesmo tom, em qualquer
  // recarga e em qualquer máquina.
  let hash = 0;
  for (const char of project.name) hash = (hash * 31 + char.charCodeAt(0)) % 360;

  return el('span', {
    class: 'card__monogram',
    'aria-hidden': 'true',
    style: `--monogram-hue: ${hash}`,
    text: letras || '?',
  });
}

function projectCard(project, { onDelete, onTogglePin, onPowerChanged, onDetect, available, signals }) {
  const isMissing = project.status === 'MISSING';

  return el(
    'article',
    {
      class: `card card--project${isMissing ? ' card--missing' : ''}`,
      dataset: { live: liveState(project, signals) },
    },
    [
    el('div', { class: 'card__header' }, [
      monogram(project),
      el('div', { class: 'card__ident' }, [
        el('a', {
          class: 'card__title',
          href: `#/projects/${encodeURIComponent(project.id)}`,
          text: project.name,
        }),
        compactPath(project.path),
      ]),
      el('div', { class: 'card__status' }, [statusBadge(project.status), pinButton(project, onTogglePin)]),
    ]),

    signalRow(project, signals),

    // Sem stack a linha continua existindo: some o conteúdo, não o degrau do
    // ritmo vertical, senão o card encolhe e desalinha do vizinho.
    el('div', { class: 'chip-row' }, [
      ...project.technologies.slice(0, 6).map((tech) => techChip(tech)),
      project.technologies.length > 6
        ? el('span', {
            class: 'tech-chip',
            title: project.technologies.slice(6).join(', '),
            text: `+${project.technologies.length - 6}`,
          })
        : null,
      // Sem stack, a linha vira um convite em vez de um lamento. Antes dizia
      // "Stack ainda não detectada" e parava aí: quem lesse tinha que abrir o
      // projeto e caçar a ação de detectar. Um projeto pode chegar sem stack
      // por vários caminhos — cadastro antes de o detector existir, arquivo de
      // configuração mal formado na hora do cadastro, pasta que só ganhou o
      // `package.json` depois. Em todos, a correção é a mesma e cabe num clique.
      project.technologies.length
        ? null
        : el('button', {
            class: 'btn btn--sm',
            type: 'button',
            title: 'Relê os arquivos do projeto e preenche a stack.',
            onClick: (event) => onDetect(project, event.currentTarget),
          }, [icon('refresh', { size: 12 }), 'Detectar stack']),
    ]),

    // Abrir o editor é o motivo mais comum de procurar um projeto aqui; exigir
    // dois cliques a mais para chegar na aba Overview era atrito puro. A chave
    // liga/desliga vem antes das ferramentas: ela é a decisão, elas são o que
    // se faz depois de tomá-la.
    el('div', { class: 'card__actions' }, [
      powerToggle(project, {
        on: (signals.online.get(project.id) ?? 0) > 0,
        onChanged: onPowerChanged,
      }),
      quickTools(project, available),
      el('div', { class: 'card__actions-end' }, [
        el('span', {
          class: 'field__hint',
          text: relativeTime(project.last_accessed_at),
          title: 'Último acesso',
        }),
        el(
          'button',
          {
            class: 'btn btn--sm btn--icon btn--danger',
            type: 'button',
            title: `Remover ${project.name} do registro`,
            'aria-label': `Remover ${project.name} do registro`,
            onClick: () => onDelete(project),
          },
          [icon('trash', { size: 13 })]
        ),
      ]),
    ]),
    ]
  );
}

// --- busca e filtros ---

const FILTERS = [
  { key: 'all', label: 'Todos', match: () => true },
  { key: 'pinned', label: 'Fixados', match: (p) => p.is_pinned },
  { key: 'online', label: 'Com serviço online', match: (p, s) => (s.online.get(p.id) ?? 0) > 0 },
  { key: 'docker', label: 'Com Docker', match: (p) => hasDocker(p) },
  {
    key: 'dirty',
    label: 'Com alteração',
    match: (p, s) => (s.git.get(p.id)?.dirty_count ?? 0) > 0,
  },
  { key: 'missing', label: 'Sem diretório', match: (p) => p.status === 'MISSING' },
];

function matchesText(project, termo) {
  if (!termo) return true;
  const alvo = `${project.name} ${project.path} ${project.technologies.join(' ')}`.toLowerCase();
  return alvo.includes(termo);
}

/** Fixados primeiro, depois o mais recente. É a ordem que a busca preserva. */
function sortProjects(items) {
  return [...items].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
    const ta = a.last_accessed_at ? Date.parse(a.last_accessed_at) : 0;
    const tb = b.last_accessed_at ? Date.parse(b.last_accessed_at) : 0;
    return tb - ta;
  });
}

function filterBar({ state, counts, stacks, onChange }) {
  const chips = FILTERS.map((filtro) =>
    el('button', {
      class: `filter-chip${state.filter === filtro.key ? ' filter-chip--on' : ''}`,
      type: 'button',
      'aria-pressed': state.filter === filtro.key ? 'true' : 'false',
      disabled: counts[filtro.key] === 0 && filtro.key !== 'all' && state.filter !== filtro.key,
      onClick: () => onChange({ filter: filtro.key }),
    }, [filtro.label, el('span', { class: 'filter-chip__count', text: String(counts[filtro.key]) })])
  );

  const seletorStack = el(
    'select',
    {
      class: 'input filter-bar__stack',
      'aria-label': 'Filtrar por stack',
      onChange: (event) => onChange({ stack: event.target.value }),
    },
    [
      el('option', { value: '', text: 'Qualquer stack' }),
      ...stacks.map((tech) =>
        el('option', { value: tech, text: tech, selected: state.stack === tech })
      ),
    ]
  );

  return el('div', { class: 'filter-bar' }, [
    el('div', { class: 'filter-bar__chips' }, chips),
    seletorStack,
    state.text
      ? el(
          'button',
          {
            class: 'filter-bar__clear',
            type: 'button',
            onClick: () => onChange({ text: '' }),
          },
          [icon('close', { size: 12 }), `busca: "${state.text}"`]
        )
      : null,
  ]);
}

function clearGlobalSearch() {
  const campo = document.getElementById('global-search');
  if (campo) campo.value = '';
}

export async function renderProjects(container, _params, query) {
  mount(container, skeletonGrid(6));

  let formVisible = false;
  const state = { text: (query.q ?? '').toLowerCase(), filter: 'all', stack: '' };

  let data = null;
  let available = null;
  let signals = { online: new Map(), git: new Map() };

  const carregar = async () => {
    // O dashboard é opcional: ele enriquece o card, mas a lista precisa
    // aparecer mesmo se a agregação falhar.
    const [lista, ferramentas, dashboard] = await Promise.all([
      api.listProjects({ limit: 200 }),
      tools(),
      api.dashboard().catch(() => null),
    ]);
    data = lista;
    available = ferramentas;
    signals = buildSignals(dashboard);
  };

  const draw = () => {
    const onDelete = async (project) => {
      const confirmed = window.confirm(
        `Remover "${project.name}" do DevCockpit?\n\n` +
          'Isso apaga apenas o registro. Nenhum arquivo do disco é tocado.'
      );
      if (!confirmed) return;

      try {
        await api.deleteProject(project.id);
        toast(`"${project.name}" removido do registro.`, { kind: 'success' });
        await carregar();
        draw();
      } catch (error) {
        showError(error);
      }
    };

    const onTogglePin = async (project) => {
      try {
        await api.updateProject(project.id, { is_pinned: !project.is_pinned });
        project.is_pinned = !project.is_pinned;
        window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
        draw();
      } catch (error) {
        showError(error);
      }
    };

    const onDetect = async (project, botao) => {
      const original = botao.textContent;
      botao.disabled = true;
      botao.textContent = 'Lendo…';
      try {
        const diff = await api.detectProject(project.id);
        if (diff.skipped) {
          toast(`${project.name}: a stack está travada; a detecção foi ignorada.`, {
            kind: 'warning',
            meta: 'Destrave em Settings do projeto para detectar de novo.',
          });
        } else if (diff.added.length || diff.services_added.length) {
          toast(`${project.name}: ${diff.added.join(', ') || 'stack atualizada'}.`, {
            kind: 'success',
            meta: diff.services_added.length
              ? `+${diff.services_added.length} serviço(s) sugerido(s)`
              : undefined,
          });
        } else {
          // Nada encontrado é resposta legítima — uma pasta com PDF e planilha
          // não tem stack. Dizer isso é melhor que repetir o mesmo botão.
          toast(`${project.name}: nada reconhecível neste diretório.`, {
            kind: 'warning',
            meta: diff.warnings[0] ?? 'Sem package.json, pyproject, Compose ou equivalente.',
          });
        }
        await carregar();
        draw();
      } catch (error) {
        botao.disabled = false;
        botao.textContent = original;
        showError(error);
      }
    };

    // Ligar ou parar muda o sinal do card, mas o estado real só reaparece
    // depois que o verificador de fundo rodar. Recarregar na hora mostraria o
    // valor velho com cara de novo; a espera curta deixa o cache alcançar.
    const onPowerChanged = () => {
      window.setTimeout(async () => {
        try {
          await carregar();
          draw();
        } catch {
          /* a tela continua utilizável com o dado anterior. */
        }
      }, 2000);
    };

    const todos = sortProjects(data.items);
    const counts = Object.fromEntries(
      FILTERS.map((filtro) => [filtro.key, todos.filter((p) => filtro.match(p, signals)).length])
    );
    const stacks = [...new Set(todos.flatMap((p) => p.technologies))].sort();

    const ativo = FILTERS.find((f) => f.key === state.filter) ?? FILTERS[0];
    const visiveis = todos.filter(
      (p) =>
        ativo.match(p, signals) &&
        matchesText(p, state.text) &&
        (!state.stack || p.technologies.includes(state.stack))
    );

    const header = pageHeader({
      title: 'Projects',
      subtitle:
        visiveis.length === todos.length
          ? `${todos.length} projeto(s) cadastrado(s)`
          : `${visiveis.length} de ${todos.length} projeto(s)`,
      actions: [
        el(
          'button',
          { class: 'btn', type: 'button', onClick: () => navigate('/discovery') },
          [icon('scan', { size: 15 }), 'Varrer diretório']
        ),
        el(
          'button',
          {
            class: 'btn btn--primary',
            type: 'button',
            onClick: () => {
              formVisible = !formVisible;
              draw();
            },
          },
          [icon(formVisible ? 'close' : 'plus', { size: 15 }),
           formVisible ? 'Fechar formulário' : 'Adicionar projeto']
        ),
      ],
    });

    const form = formVisible
      ? createForm({
          onCreated: async () => {
            formVisible = false;
            await carregar();
            draw();
          },
        })
      : null;

    const barra = todos.length
      ? filterBar({
          state,
          counts,
          stacks,
          onChange: (patch) => {
            Object.assign(state, patch);
            if (patch.text === '') clearGlobalSearch();
            draw();
          },
        })
      : null;

    let body;
    if (!todos.length) {
      body = emptyState({
        iconName: 'inbox',
        title: 'Nenhum projeto ainda',
        text:
          'Cadastre a pasta de um projeto, ou aponte um diretório raiz e deixe ' +
          'o DevCockpit encontrar tudo de uma vez.',
        actions: [
          el('button', {
            class: 'btn btn--primary',
            text: 'Varrer diretório',
            onClick: () => navigate('/discovery'),
          }),
          el('button', {
            class: 'btn',
            text: 'Adicionar pasta',
            onClick: () => {
              formVisible = true;
              draw();
            },
          }),
        ],
      });
    } else if (!visiveis.length) {
      body = emptyState({
        iconName: 'search',
        title: 'Nenhum projeto com esse filtro',
        text: 'Ajuste a busca ou volte para "Todos".',
        actions: [
          el('button', {
            class: 'btn',
            text: 'Limpar filtros',
            onClick: () => {
              Object.assign(state, { text: '', filter: 'all', stack: '' });
              clearGlobalSearch();
              draw();
            },
          }),
        ],
      });
    } else {
      body = el(
        'div',
        { class: 'grid-cards' },
        visiveis.map((project) =>
          projectCard(project, { onDelete, onTogglePin, onPowerChanged, onDetect, available, signals })
        )
      );
    }

    mount(container, header, form, barra, body);
  };

  // A busca é uma só, a da topbar (Ctrl+K). O ouvinte precisa morrer quando a
  // tela sai de cena: sem isso cada visita a Projects empilha mais um, e todos
  // continuam desenhando dentro de containers já descartados.
  const vida = new AbortController();
  window.addEventListener(
    'hashchange',
    () => {
      // `#/projects/<id>` é a tela de detalhe, não esta: comparar por prefixo
      // deixaria o ouvinte vivo desenhando num container já trocado.
      const rota = window.location.hash.split('?')[0].replace(/\/$/, '');
      if (rota !== '#/projects') vida.abort();
    },
    { signal: vida.signal }
  );

  window.addEventListener(
    'devcockpit:search',
    (event) => {
      state.text = String(event.detail ?? '').trim().toLowerCase();
      draw();
    },
    { signal: vida.signal }
  );

  try {
    await carregar();
  } catch (error) {
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }
  draw();
}

function createForm({ onCreated }) {
  const pathInput = el('input', {
    class: 'input input--mono',
    id: 'new-project-path',
    placeholder: 'C:/Users/User/Desktop/meu-projeto',
    autocomplete: 'off',
  });
  const nameInput = el('input', {
    class: 'input',
    id: 'new-project-name',
    placeholder: 'opcional — o padrão é o nome da pasta',
  });

  const submit = async (event) => {
    event.preventDefault();
    const path = pathInput.value.trim();
    if (!path) {
      toast('Informe o caminho da pasta.', { kind: 'error' });
      return;
    }

    try {
      const created = await api.createProject({
        path,
        name: nameInput.value.trim() || null,
      });
      pathInput.value = '';
      nameInput.value = '';
      toast(`Projeto "${created.name}" cadastrado.`, { kind: 'success' });
      onCreated();
    } catch (error) {
      if (error instanceof ApiError) showError(error);
      else throw error;
    }
  };

  return el('form', { class: 'form-panel', onSubmit: submit }, [
    el('h2', { class: 'section-title', text: 'Adicionar projeto' }),
    el('div', { class: 'field' }, [
      el('label', { class: 'field__label', for: 'new-project-path', text: 'Caminho da pasta' }),
      pathInput,
      el('span', {
        class: 'field__hint',
        text: 'Precisa estar dentro de um root permitido em configs/roots.yml.',
      }),
    ]),
    el('div', { class: 'field' }, [
      el('label', { class: 'field__label', for: 'new-project-name', text: 'Nome' }),
      nameInput,
    ]),
    el('button', { class: 'btn btn--primary', type: 'submit', text: 'Cadastrar' }),
  ]);
}
