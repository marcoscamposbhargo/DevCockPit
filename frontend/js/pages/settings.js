import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { getTheme, setTheme, THEME_LABELS, THEME_VALUES } from '../lib/theme.js';
import { loading, pageHeader, showError, techChip, toast } from '../lib/ui.js';

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

// --- providers de IA (REQ-14) ---------------------------------------------
//
// Esta seção mostra **estado**, e nada além disso. O único campo relacionado à
// chave que a rota devolve é `api_key_env` — o *nome* da variável de ambiente
// —, e é ele que aparece: saber onde mexer é o que resolve "não configurado".
// Valor de chave não passa por aqui nem em pedaço, e nada aqui é editável: a
// chave vive no ambiente e a interface não a escreve (P-05).
//
// Também não há botão de reverificar. Não é esquecimento: a chave é lida do
// ambiente na abertura do processo, então reconsultar sem reabrir o painel
// mostraria o mesmo estado com cara de novidade.

const ESTADO_ROTULO = {
  conectado: 'conectado',
  nao_configurado: 'não configurado',
  desligado: 'desligado',
  indisponivel: 'indisponível',
};

const TIPO_ROTULO = { local: 'local', cloud: 'nuvem' };

function estadoBadge(estado) {
  return el('span', { class: 'status-badge', dataset: { estado } }, [
    el('span', { class: 'status-badge__dot' }),
    ESTADO_ROTULO[estado] ?? estado,
  ]);
}

/** Latência da última sondagem.
 *
 * Ausência vira "não medido", nunca "0 ms": não existe latência de quem não
 * respondeu, e um zero com cara de medição é pior que a falta do número
 * (P-02). Zero medido de verdade — provider local na mesma máquina — continua
 * sendo zero, e por isso a comparação é com `null`, não com falsidade.
 */
function latenciaTexto(ms) {
  return ms === null || ms === undefined ? 'não medido' : `${ms} ms`;
}

/** O que fazer com este provider, quando há o que fazer.
 *
 * `nao_configurado` é o único estado que a pessoa resolve sozinha, e o texto
 * dele é montado aqui nomeando a variável que falta — mesmo que a rota não
 * mande motivo. Rótulo mudo justamente aqui desperdiçaria a única informação
 * acionável da tela.
 */
function detalheDoEstado(provider) {
  const variavel = provider.api_key_env || 'a variável declarada em configs/ai.yml';

  switch (provider.estado) {
    case 'nao_configurado':
      return (
        `Falta ${variavel} no ambiente. Defina-a no .env, na pasta do painel, ` +
        'e reabra o DevCockpit.'
      );
    case 'desligado':
      return provider.motivo || 'Desligado em configs/ai.yml (`enabled: false`).';
    case 'indisponivel':
      return provider.motivo || 'Não respondeu à sondagem e não disse por quê.';
    default:
      return '';
  }
}

function providerRow(provider, sonda) {
  const modelos = provider.modelos ?? [];
  const detalhe = detalheDoEstado(provider);
  const latencia = sonda ? sonda.latencia_ms : null;
  const medido = latencia !== null && latencia !== undefined;

  return el('tr', {}, [
    el('td', {}, [
      el('div', { class: 'mono', text: provider.id }),
      el('div', { class: 'field__hint', text: TIPO_ROTULO[provider.type] ?? provider.type }),
    ]),
    el('td', {}, [
      estadoBadge(provider.estado),
      detalhe ? el('div', { class: 'field__hint', text: detalhe }) : null,
    ]),
    el('td', {}, [
      modelos.length
        ? el('div', { class: 'chip-row' }, modelos.map((id) => techChip(id)))
        : el('span', { class: 'field__hint', text: 'nenhum declarado' }),
    ]),
    el('td', {
      // Cinza quando não há medição: o mesmo tratamento do Health Score, para
      // "não medido" nunca se ler como um valor apurado.
      class: medido ? 'table__num' : 'table__num field__hint',
      text: latenciaTexto(latencia),
      title: medido
        ? 'Ida e volta da última sondagem deste provider.'
        : 'Ninguém mediu: o provider não respondeu à sondagem.',
    }),
    el('td', {}, [
      provider.api_key_env
        ? el('span', {
            class: 'mono',
            text: provider.api_key_env,
            title: 'Nome da variável de ambiente. O valor fica no ambiente, e não vem para cá.',
          })
        : el('span', { class: 'field__hint', text: 'não usa chave' }),
    ]),
  ]);
}

function coluna(rotulo) {
  return el('th', { scope: 'col', text: rotulo });
}

/**
 * A tabela de providers.
 *
 * `registro` é a resposta de `GET /api/ai/providers`, ou `{ falha }` quando a
 * chamada não voltou. `saude` é a de `GET /api/ai/health`, ou `null` — sem ela
 * a latência fica "não medido", que é exatamente o que ela é.
 */
export function providersSection(registro, saude) {
  const sondas = new Map((saude?.items ?? []).map((item) => [item.id, item]));
  const itens = registro?.items ?? [];

  let corpo;
  if (registro?.falha) {
    corpo = el('p', {
      class: 'field__hint',
      text: `Não foi possível ler o registro de providers: ${registro.falha}`,
    });
  } else if (registro?.erro) {
    corpo = el('p', {
      class: 'field__hint',
      text: `configs/ai.yml não pôde ser lido: ${registro.erro}`,
    });
  } else if (!itens.length) {
    corpo = el('p', {
      class: 'field__hint',
      text:
        'Nenhum provider declarado. Copie configs/ai.example.yml para configs/ai.yml e ' +
        'liste os providers. O painel funciona inteiro sem isso — só sem IA.',
    });
  } else {
    corpo = el('div', { class: 'table-wrap', style: 'overflow-x:auto' }, [
      el('table', { class: 'table' }, [
        el('thead', {}, [
          el('tr', {}, [
            coluna('Provider'),
            coluna('Estado'),
            coluna('Modelos declarados'),
            coluna('Latência'),
            coluna('Chave'),
          ]),
        ]),
        el('tbody', {}, itens.map((item) => providerRow(item, sondas.get(item.id)))),
      ]),
    ]);
  }

  return el('section', { id: 'ai-providers-section', style: 'margin-top:var(--sp-6)' }, [
    el('h2', { class: 'section-title', text: 'AI Providers' }),
    el('p', {
      class: 'field__hint',
      style: 'margin-bottom:var(--sp-3)',
      text:
        'Declarados em configs/ai.yml e ligados por variável de ambiente. O painel mostra o ' +
        'nome da variável, nunca o valor da chave — e não há como editar a chave por aqui.',
    }),
    corpo,
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

  // As duas rotas de IA em paralelo, e nenhuma obrigatória: `/providers`
  // classifica o estado, `/health` é quem mediu a latência. Em paralelo porque
  // as duas sondam, e em série a tela pagaria dois timeouts em fila. Falha de
  // qualquer uma vira estado exibido, não tela quebrada (P-06).
  const [registroDeIa, saudeDaIa] = await Promise.all([
    api.aiProviders().catch((error) => ({ falha: error.message })),
    api.aiHealth().catch(() => null),
  ]);
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

    providersSection(registroDeIa, saudeDaIa),
    runningSection(servidores, recarregar),
    themeSection()
  );
}
