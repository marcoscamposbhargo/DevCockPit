// Aba Server: o servidor de desenvolvimento do projeto e a saída dele.
//
// Existe por uma falha concreta. O painel passou a saber subir `npm run dev` e
// `uvicorn`, e a saída ia para arquivo — mas nenhuma tela mostrava esse
// arquivo. Quando um servidor não subia, o painel dizia "desligado" e a razão
// (`ModuleNotFoundError: No module named 'duckdb'`, em texto claro, no disco)
// não tinha caminho até os olhos de ninguém.
//
// Três coisas, nesta ordem de importância:
//
// 1. **o que vai rodar**, antes de clicar — ninguém deve descobrir o que o
//    botão faz depois de apertá-lo;
// 2. **a saída**, ao vivo e também depois da queda, que é quando ela importa;
// 3. os controles, que são consequência das duas primeiras.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { logView } from '../lib/log-view.js';
import { emptyState, showError, toast } from '../lib/ui.js';

const ORIGEM = {
  manifest: 'declarado no devcockpit.yml',
  node: 'deduzido do package.json',
  python: 'deduzido das dependências Python',
};

/** Cartão que explica o comando antes do clique. */
function comandoCard(estado) {
  return el('div', { class: 'server-cmd' }, [
    el('div', { class: 'server-cmd__head' }, [
      el('span', { class: 'field__hint', text: 'Comando' }),
      estado.source
        ? el('span', {
            class: 'server-cmd__origin',
            text: ORIGEM[estado.source] ?? estado.source,
            title: estado.evidence,
          })
        : null,
    ]),
    el('code', { class: 'server-cmd__code', text: estado.command }),
  ]);
}

function semComando(projectId) {
  return emptyState({
    iconName: 'terminal',
    title: 'O painel não sabe como subir este projeto',
    text:
      'Sem Compose, sem script de dev no package.json e sem framework Python ' +
      'reconhecido. Declare o bloco `run:` no devcockpit.yml do projeto — ' +
      'o comando fica visível aqui antes de qualquer clique.',
    actions: [
      el('a', {
        class: 'btn',
        href: `#/projects/${encodeURIComponent(projectId)}?tab=manifest`,
        text: 'Ver o manifesto',
      }),
    ],
  });
}

export async function renderServerPanel(panel) {
  const projectId = panel.dataset.projectId;

  let estado;
  try {
    estado = await api.serverStatus(projectId);
  } catch (error) {
    mount(panel, el('p', { class: 'loading', text: error.message }));
    return;
  }

  if (!estado.can_start && !estado.running) {
    mount(panel, semComando(projectId));
    return;
  }

  // O visor busca sempre, ligado ou não: depois de uma queda o log é a única
  // coisa que explica o que houve, e é exatamente aí que se quer lê-lo.
  const visor = logView({
    fetchLines: async () => (await api.serverLogs(projectId, 500)).lines,
    vazio: estado.running
      ? 'O servidor subiu e ainda não escreveu nada.'
      : 'Nenhuma saída registrada. Ligue o servidor para acompanhar aqui.',
  });

  const redesenhar = async () => {
    visor.parar();
    await renderServerPanel(panel);
  };

  const agir = async (botao, rotulo, acao) => {
    const original = botao.textContent;
    botao.disabled = true;
    botao.textContent = rotulo;
    try {
      await acao();
      // Uma volta imediata no log: o erro de partida aparece nos primeiros
      // instantes, e esperar o relógio de um segundo faz a tela parecer parada
      // justamente no momento em que a pessoa está olhando.
      await visor.atualizar();
      await redesenhar();
    } catch (error) {
      botao.disabled = false;
      botao.textContent = original;
      showError(error);
      await visor.atualizar();
    }
  };

  const ligar = el('button', { class: 'btn btn--primary', type: 'button' }, [
    icon('power', { size: 13 }),
    'Ligar',
  ]);
  ligar.addEventListener('click', () =>
    agir(ligar, 'Subindo…', async () => {
      await api.startServer(projectId);
      toast('Servidor iniciado. A saída aparece abaixo.', { kind: 'success' });
    })
  );

  const parar = el('button', { class: 'btn', type: 'button' }, [
    icon('power', { size: 13 }),
    'Parar',
  ]);
  parar.addEventListener('click', () =>
    agir(parar, 'Parando…', async () => {
      await api.stopServer(projectId);
      toast('Servidor parado.', { kind: 'success' });
    })
  );

  const reiniciar = el('button', { class: 'btn', type: 'button' }, [
    icon('refresh', { size: 13 }),
    'Reiniciar',
  ]);
  reiniciar.addEventListener('click', () =>
    agir(reiniciar, 'Reiniciando…', async () => {
      await api.restartServer(projectId);
      toast('Servidor reiniciado.', { kind: 'success' });
    })
  );

  mount(
    panel,
    el('div', { class: 'server-head' }, [
      el('div', { class: 'server-head__state', dataset: { on: String(estado.running) } }, [
        el('span', { class: 'server-head__dot', 'aria-hidden': 'true' }),
        el('strong', { text: estado.running ? 'No ar' : 'Parado' }),
        estado.running && estado.pid
          ? el('span', { class: 'field__hint mono', text: `pid ${estado.pid}` })
          : null,
        estado.running && estado.started_at
          ? el('span', { class: 'field__hint', text: `desde ${relativeTime(estado.started_at)}` })
          : null,
      ]),
      el('div', { class: 'server-head__actions' }, [
        estado.running ? reiniciar : null,
        estado.running ? parar : ligar,
      ]),
    ]),

    estado.command ? comandoCard(estado) : null,

    el('p', {
      class: 'field__hint',
      style: 'margin:var(--sp-4) 0 var(--sp-2)',
      text:
        'A saída é lida do arquivo de log, então continua disponível depois de ' +
        'o servidor cair — que é quando ela costuma importar.',
    }),
    visor.element
  );
}
