import { quickTools, tools } from '../lib/actions.js';
import { api, ApiError } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { emptyState, loading, pageHeader, showError, statusBadge, techChip, toast } from '../lib/ui.js';
import { navigate } from '../router.js';

function projectCard(project, { onDelete, available }) {
  const isMissing = project.status === 'MISSING';

  return el('article', { class: `card${isMissing ? ' card--missing' : ''}` }, [
    el('div', { class: 'card__header' }, [
      el('div', {}, [
        el('a', { class: 'card__title', href: `#/projects/${encodeURIComponent(project.id)}`, text: project.name }),
        el('div', { class: 'card__path', text: project.path }),
      ]),
      el('div', { style: 'margin-left:auto' }, [statusBadge(project.status)]),
    ]),

    project.technologies.length
      ? el('div', { class: 'chip-row' }, project.technologies.map((tech) => techChip(tech)))
      : el('span', { class: 'field__hint', text: 'Stack ainda não detectada' }),

    el('div', { class: 'field__hint', text: `Último acesso: ${relativeTime(project.last_accessed_at)}` }),

    // Abrir o editor é o motivo mais comum de procurar um projeto aqui; exigir
    // dois cliques a mais para chegar na aba Overview era atrito puro.
    quickTools(project, available),

    el('div', { class: 'card__footer' }, [
      el('button', {
        class: 'btn btn--sm',
        onClick: () => navigate(`/projects/${encodeURIComponent(project.id)}`),
        text: 'Abrir',
      }),
      el('button', {
        class: 'btn btn--sm btn--danger',
        onClick: () => onDelete(project),
        text: 'Remover',
      }),
    ]),
  ]);
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

export async function renderProjects(container, _params, query) {
  mount(container, loading());

  let formVisible = false;

  const draw = async () => {
    let data;
    let available;
    try {
      [data, available] = await Promise.all([
        api.listProjects({ q: query.q, limit: 200 }),
        tools(),
      ]);
    } catch (error) {
      mount(container, el('p', { class: 'loading', text: error.message }));
      return;
    }

    const onDelete = async (project) => {
      const confirmed = window.confirm(
        `Remover "${project.name}" do DevCockpit?\n\n` +
          'Isso apaga apenas o registro. Nenhum arquivo do disco é tocado.'
      );
      if (!confirmed) return;

      try {
        await api.deleteProject(project.id);
        toast(`"${project.name}" removido do registro.`, { kind: 'success' });
        draw();
      } catch (error) {
        showError(error);
      }
    };

    const header = pageHeader({
      title: 'Projects',
      subtitle: `${data.total} projeto(s) cadastrado(s)`,
      actions: [
        el('button', {
          class: 'btn',
          text: 'Varrer diretório',
          onClick: () => navigate('/discovery'),
        }),
        el('button', {
          class: 'btn btn--primary',
          text: formVisible ? 'Fechar formulário' : 'Adicionar projeto',
          onClick: () => {
            formVisible = !formVisible;
            draw();
          },
        }),
      ],
    });

    const form = formVisible
      ? createForm({
          onCreated: () => {
            formVisible = false;
            draw();
          },
        })
      : null;

    const body = data.items.length
      ? el(
          'div',
          { class: 'grid-cards' },
          data.items.map((project) => projectCard(project, { onDelete, available }))
        )
      : emptyState({
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

    mount(container, header, form, body);
  };

  await draw();
}
