// Aba Manifest: estado do `devcockpit.yml`, comparação e sincronização.
//
// Nenhuma das duas direções roda sozinha, e exportar pede confirmação: é a
// única escrita do DevCockpit dentro de pasta de projeto (FR-112).

import { api } from '../lib/api.js';
import { el } from '../lib/dom.js';
import { loading, showError, toast } from '../lib/ui.js';

function warningList(warnings) {
  if (!warnings.length) return null;
  return el('div', { class: 'card card--missing' }, [
    el('h3', { text: warnings.length === 1 ? 'Aviso' : 'Avisos' }),
    el(
      'ul',
      {},
      warnings.map((aviso) => el('li', { class: 'field__hint', text: aviso }))
    ),
  ]);
}

function diffTable(diff) {
  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', { text: 'Campo' }),
          el('th', { text: 'No DevCockpit' }),
          el('th', { text: 'No arquivo' }),
        ]),
      ]),
      el(
        'tbody',
        {},
        diff.map((item) =>
          el('tr', {}, [
            el('td', { class: 'mono', text: item.field }),
            el('td', { text: item.database ?? '—' }),
            el('td', { text: item.manifest ?? '—' }),
          ])
        )
      ),
    ]),
  ]);
}

function summary(status) {
  if (!status.exists) {
    return el('p', {
      class: 'field__hint',
      text:
        'Este projeto não tem devcockpit.yml. O DevCockpit funciona sem ele — ' +
        'exportar cria o arquivo com a configuração atual, versionável junto do código.',
    });
  }
  if (!status.valid) {
    return el('p', {
      class: 'field__hint',
      text: `${status.filename} existe, mas foi ignorado. O projeto segue funcionando pelo banco.`,
    });
  }
  if (status.in_sync) {
    return el('p', {
      class: 'field__hint',
      text: `${status.filename} está em sincronia com o DevCockpit.`,
    });
  }
  return el('p', {
    class: 'field__hint',
    text:
      `${status.filename} divergiu do DevCockpit em ${status.diff.length} campo(s). ` +
      'Nada é resolvido automaticamente: escolha uma direção.',
  });
}

export async function renderManifestPanel(container) {
  const projectId = container.dataset.projectId;
  container.replaceChildren(loading());

  const recarregar = () => renderManifestPanel(container);

  const importar = async () => {
    try {
      const resultado = await api.importManifest(projectId);
      toast(
        resultado.applied.length
          ? `Manifesto importado. Alterados: ${resultado.applied.join(', ')}.`
          : 'Manifesto importado. Nada mudou.',
        { kind: 'success' }
      );
      window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
      await recarregar();
    } catch (error) {
      showError(error);
    }
  };

  const exportar = async () => {
    const confirmado = window.confirm(
      'Escrever devcockpit.yml na pasta do projeto?\n\n' +
        'É a única vez que o DevCockpit escreve dentro de um projeto. ' +
        'Um arquivo existente será substituído.'
    );
    if (!confirmado) return;

    try {
      const resultado = await api.exportManifest(projectId);
      toast(
        `${resultado.overwritten ? 'Substituído' : 'Criado'} ${resultado.path} ` +
          `(${resultado.bytes_written} bytes).`,
        { kind: 'success' }
      );
      await recarregar();
    } catch (error) {
      showError(error);
    }
  };

  let status;
  let preview;
  try {
    [status, preview] = await Promise.all([
      api.manifestStatus(projectId),
      api.manifestPreview(projectId),
    ]);
  } catch (error) {
    showError(error);
    container.replaceChildren(el('p', { class: 'loading', text: error.message }));
    return;
  }

  container.replaceChildren(
    el('div', { class: 'freshness' }, [
      summary(status),
      el('div', { class: 'card__footer' }, [
        el('button', {
          class: 'btn btn--sm',
          text: 'Importar do arquivo',
          disabled: !status.valid,
          title: status.valid ? null : 'Não há manifesto válido para importar.',
          onClick: importar,
        }),
        el('button', {
          class: 'btn btn--sm btn--primary',
          text: status.exists ? 'Exportar e substituir' : 'Exportar',
          onClick: exportar,
        }),
      ]),
    ]),
    warningList(status.warnings ?? []),
    status.diff.length
      ? el('section', { style: 'margin-top:var(--sp-5)' }, [
          el('h2', { class: 'section-title', text: 'Diferenças' }),
          diffTable(status.diff),
        ])
      : null,
    el('section', { style: 'margin-top:var(--sp-5)' }, [
      el('h2', { class: 'section-title', text: 'O que a exportação escreveria' }),
      el('pre', { class: 'code-block' }, [el('code', { text: preview.content })]),
    ])
  );
}
