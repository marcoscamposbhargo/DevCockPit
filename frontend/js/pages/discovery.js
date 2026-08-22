// Varredura de diretório e importação em lote (US-023, US-024).

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { jobConsole } from '../lib/job-console.js';
import { emptyState, pageHeader, showError, techChip, toast } from '../lib/ui.js';
import { navigate } from '../router.js';

function candidateRow(candidate, selected) {
  const checkbox = el('input', {
    type: 'checkbox',
    checked: !candidate.already_registered,
    disabled: candidate.already_registered,
    onChange: (event) => {
      if (event.target.checked) selected.add(candidate.path);
      else selected.delete(candidate.path);
    },
  });

  if (!candidate.already_registered) selected.add(candidate.path);

  return el('tr', {}, [
    el('td', {}, [checkbox]),
    el('td', { text: candidate.suggested_name }),
    el('td', { class: 'mono', text: candidate.path }),
    el(
      'td',
      {},
      candidate.technologies.length
        ? [el('div', { class: 'chip-row' }, candidate.technologies.map((t) => techChip(t)))]
        : [el('span', { class: 'field__hint', text: '—' })]
    ),
    el('td', { text: candidate.is_git_repo ? 'sim' : '—' }),
    el('td', {
      text: candidate.already_registered ? 'já cadastrado' : 'novo',
      style: candidate.already_registered ? 'color:var(--fg-muted)' : '',
    }),
  ]);
}

export async function renderDiscovery(container) {
  const selected = new Set();
  let allowedRoots = [];

  try {
    allowedRoots = (await api.health()).allowed_roots;
  } catch {
    allowedRoots = [];
  }

  const rootInput = el('input', {
    class: 'input input--mono',
    id: 'scan-root',
    value: allowedRoots[0] ?? '',
    placeholder: 'C:/Users/User/Desktop',
  });

  const depthInput = el('input', {
    class: 'input',
    id: 'scan-depth',
    type: 'number',
    min: '0',
    max: '6',
    value: '3',
  });

  const results = el('div', {});

  const runScan = async (event) => {
    event.preventDefault();
    selected.clear();

    const root = rootInput.value.trim();

    // A varredura é um job: erro de allowlist volta na hora, o resto acompanha
    // no console (D-23).
    let accepted;
    try {
      accepted = await api.scan(root, Number(depthInput.value));
    } catch (error) {
      showError(error);
      results.replaceChildren(el('p', { class: 'loading', text: error.message }));
      return;
    }

    const consoleView = jobConsole({
      jobId: accepted.job_id,
      title: 'Varredura de diretório',
      onFinish: (status) => {
        if (status === 'SUCCESS') showCandidates();
        else if (status !== 'CANCELLED') toast('A varredura não terminou bem.', { kind: 'error' });
      },
    });
    results.replaceChildren(consoleView.element);
    return;
  };

  const showCandidates = async () => {
    const root = rootInput.value.trim();

    let data;
    try {
      data = await api.candidates(root);
    } catch (error) {
      showError(error);
      return;
    }

    if (!data.items.length) {
      results.append(
        emptyState({
          title: 'Nenhum projeto encontrado',
          text:
            `${data.scanned_dirs} diretório(s) varrido(s) em ${data.root}. ` +
            'Tente aumentar a profundidade ou apontar outra raiz.',
        })
      );
      return;
    }

    const novos = data.items.filter((item) => !item.already_registered);

    const importar = async () => {
      const paths = [...selected];
      if (!paths.length) {
        toast('Nenhum projeto selecionado.', { kind: 'error' });
        return;
      }
      try {
        const resposta = await api.importCandidates(paths);
        toast(
          `${resposta.imported} projeto(s) cadastrado(s)` +
            (resposta.failed ? `, ${resposta.failed} com erro.` : '.'),
          { kind: resposta.failed ? 'error' : 'success' }
        );
        for (const item of resposta.items.filter((i) => !i.ok)) {
          toast(`${item.path}: ${item.message}`, { kind: 'error' });
        }
        window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
        navigate('/projects');
      } catch (error) {
        showError(error);
      }
    };

    results.append(
      el('div', { class: 'page-header' }, [
        el('div', { class: 'page-header__text' }, [
          el('h2', { text: `${data.items.length} candidato(s)` }),
          el('p', {
            class: 'field__hint',
            text:
              `${novos.length} novo(s) · ${data.scanned_dirs} diretório(s) varrido(s)` +
              (data.truncated ? ' · lista truncada' : '') +
              (data.skipped_dirs.length
                ? ` · ${data.skipped_dirs.length} sem permissão, ignorado(s)`
                : ''),
          }),
        ]),
        el('div', { class: 'page-header__actions' }, [
          el('button', {
            class: 'btn btn--primary',
            onClick: importar,
            disabled: novos.length === 0,
            text: 'Cadastrar selecionados',
          }),
        ]),
      ]),
      el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table' }, [
          el('thead', {}, [
            el('tr', {}, [
              el('th', { text: '' }),
              el('th', { text: 'Nome' }),
              el('th', { text: 'Caminho' }),
              el('th', { text: 'Stack' }),
              el('th', { text: 'Git' }),
              el('th', { text: 'Situação' }),
            ]),
          ]),
          el('tbody', {}, data.items.map((item) => candidateRow(item, selected))),
        ]),
      ])
    );
  };

  const form = el('form', { class: 'form-panel', onSubmit: runScan }, [
    el('div', { class: 'field' }, [
      el('label', { class: 'field__label', for: 'scan-root', text: 'Diretório raiz' }),
      rootInput,
      el('span', {
        class: 'field__hint',
        text: allowedRoots.length
          ? `Permitidos: ${allowedRoots.join(' · ')}`
          : 'Nenhum root permitido configurado em configs/roots.yml.',
      }),
    ]),
    el('div', { class: 'field' }, [
      el('label', { class: 'field__label', for: 'scan-depth', text: 'Profundidade máxima' }),
      depthInput,
      el('span', {
        class: 'field__hint',
        text: 'A varredura não entra em projeto já encontrado, nem em node_modules e afins.',
      }),
    ]),
    el('button', { class: 'btn btn--primary', type: 'submit', text: 'Varrer' }),
  ]);

  mount(
    container,
    pageHeader({
      title: 'Descobrir projetos',
      subtitle: 'Aponte uma pasta raiz e cadastre em lote o que for encontrado.',
      actions: [
        el('button', { class: 'btn', onClick: () => navigate('/projects'), text: '← Projects' }),
      ],
    }),
    form,
    results
  );
}
