import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { getTheme, setTheme, THEME_LABELS, THEME_VALUES } from '../lib/theme.js';
import { loading, pageHeader } from '../lib/ui.js';

function toolRow(name, available) {
  return el('tr', {}, [
    el('td', { class: 'mono', text: name }),
    el('td', {
      text: available ? 'disponível' : 'não encontrado no PATH',
      style: `color:${available ? 'var(--status-running)' : 'var(--status-warning)'}`,
    }),
  ]);
}

function themeSection() {
  const atual = getTheme();

  const botoes = THEME_VALUES.map((valor) =>
    el('button', {
      class: `btn btn--sm${valor === atual ? ' btn--primary' : ''}`,
      text: THEME_LABELS[valor],
      'aria-pressed': valor === atual ? 'true' : 'false',
      onClick: () => {
        setTheme(valor);
        // Redesenha só esta seção: trocar de tema não deve recarregar a tela.
        const secao = document.getElementById('theme-section');
        if (secao) secao.replaceWith(themeSection());
      },
    })
  );

  return el('section', { id: 'theme-section', style: 'margin-top:var(--sp-6)' }, [
    el('h2', { class: 'section-title', text: 'Aparência' }),
    el('p', {
      class: 'field__hint',
      style: 'margin-bottom:var(--sp-3)',
      text:
        'A preferência fica neste navegador, não no banco: é ajuste de quem olha a tela. ' +
        '"Sistema" segue a configuração do Windows.',
    }),
    el('div', { class: 'card__footer' }, botoes),
  ]);
}

export async function renderSettings(container) {
  mount(container, loading());

  let health;
  try {
    health = await api.health();
  } catch (error) {
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  const roots = health.allowed_roots.length
    ? el(
        'ul',
        {},
        health.allowed_roots.map((root) => el('li', { class: 'mono', text: root }))
      )
    : el('p', {
        class: 'field__hint',
        text:
          'Nenhum root configurado. Copie configs/roots.example.yml para ' +
          'configs/roots.yml e liste os diretórios permitidos.',
      });

  mount(
    container,
    pageHeader({ title: 'Settings', subtitle: `DevCockpit ${health.version}` }),

    el('section', {}, [
      el('h2', { class: 'section-title', text: 'Diretórios permitidos' }),
      el('p', {
        class: 'field__hint',
        style: 'margin-bottom:var(--sp-3)',
        text:
          'Editável apenas em configs/roots.yml, no disco. A API nunca altera esta lista — ' +
          'uma allowlist que o cliente amplia não é uma allowlist.',
      }),
      roots,
    ]),

    el('section', { style: 'margin-top:var(--sp-6)' }, [
      el('h2', { class: 'section-title', text: 'Ferramentas externas' }),
      el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table' }, [
          el('tbody', {}, [
            toolRow('git', health.tools.git),
            toolRow('docker', health.tools.docker),
            toolRow('code', health.tools.code),
          ]),
        ]),
      ]),
    ]),

    themeSection()
  );
}
