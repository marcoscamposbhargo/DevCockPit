import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { getTheme, setTheme, THEME_LABELS, THEME_VALUES } from '../lib/theme.js';
import { loading, pageHeader, showError, toast } from '../lib/ui.js';

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

/** Tudo o que o painel subiu e ainda está de pé, num lugar só.
 *
 * Sem isto, saber o que está rodando exige abrir projeto por projeto — e no
 * fim do dia, lembrar quais foram. É a tela do "o que eu deixo ligado antes de
 * fechar o notebook", e o gesto é parar, não investigar.
 */
function runningSection(servidores, aoMudar) {
  if (!servidores.length) {
    return el('section', { id: 'running-section', style: 'margin-top:var(--sp-6)' }, [
      el('h2', { class: 'section-title', text: 'Servidores no ar' }),
      el('p', {
        class: 'field__hint',
        text: 'Nenhum servidor de desenvolvimento foi iniciado pelo painel.',
      }),
    ]);
  }

  const parar = async (servidor, botao) => {
    botao.disabled = true;
    botao.textContent = 'Parando…';
    try {
      await api.stopServer(servidor.project_id);
      toast(`${servidor.project_name}: servidor parado.`, { kind: 'success' });
      await aoMudar();
    } catch (error) {
      botao.disabled = false;
      botao.textContent = 'Parar';
      showError(error);
    }
  };

  return el('section', { id: 'running-section', style: 'margin-top:var(--sp-6)' }, [
    el('h2', { class: 'section-title' }, [
      'Servidores no ar',
      el('span', { class: 'section-title__count', text: String(servidores.length) }),
    ]),
    el('p', {
      class: 'field__hint',
      style: 'margin-bottom:var(--sp-3)',
      text:
        'Processos que o painel iniciou e que sobrevivem a um reinício dele. ' +
        'Parar aqui não mexe nos containers.',
    }),
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'table' }, [
        el('tbody', {}, servidores.map((servidor) => {
          const botao = el('button', { class: 'btn btn--sm', type: 'button', text: 'Parar' });
          botao.addEventListener('click', () => parar(servidor, botao));

          return el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(servidor.project_id)}?tab=server`,
                text: servidor.project_name,
              }),
            ]),
            el('td', { class: 'mono field__hint', text: `pid ${servidor.pid}` }),
            el('td', {
              class: 'activity__mensagem mono',
              text: servidor.command,
              title: servidor.command,
            }),
            el('td', { class: 'field__hint', text: relativeTime(servidor.started_at) }),
            el('td', { class: 'table__end' }, [botao]),
          ]);
        })),
      ]),
    ]),
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

  // Opcional: uma falha aqui não pode derrubar a tela de configuração inteira.
  const servidores = await api.runningServers().then((r) => r.items).catch(() => []);
  const recarregar = () => renderSettings(container);

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

    runningSection(servidores, recarregar),
    themeSection()
  );
}
