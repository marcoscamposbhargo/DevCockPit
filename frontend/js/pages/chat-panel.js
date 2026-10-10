// Chat contextual do projeto.
//
// A promessa é uma só: **você não precisa explicar de qual projeto está
// falando**. O contexto sai da memória, das sessões, das tarefas e do estado
// que o painel já mede — e a tela mostra quais camadas entraram, para a
// resposta poder ser conferida.
//
// Desligado por padrão. Sem provedor configurado, esta aba explica o que fazer
// em vez de quebrar: é a mesma regra do Docker desligado, que nunca vira erro
// de tela.

import { api } from '../lib/api.js';
import { COMANDOS, interpretarComando, sugerir } from '../lib/comandos.js';
import { el, mount } from '../lib/dom.js';
import { icon } from '../lib/icons.js';
import { quemRespondeu, seletorDoRegistro } from '../lib/modelo-escolhido.js';
import { showError, toast } from '../lib/ui.js';

const NOME_DO_CHAPEU = { devops: 'DevOps', fullstack: 'Full Stack', qa: 'QA' };

// Quem assina a resposta. Sem o chapéu, três instruções de sistema diferentes
// produziriam respostas com tom e prioridade distintos sob o mesmo nome — e
// ninguém saberia por quê. Mensagem antiga (anterior à Fase 3.2) não tem chapéu
// gravado, e aí volta a assinar como o painel inteiro.
function assinatura(mensagem) {
  if (mensagem.role === 'user') return 'você';
  const chapeu = NOME_DO_CHAPEU[mensagem.agent];
  return chapeu ? `Cockpit AI · ${chapeu}` : 'Cockpit AI';
}

function bolha(mensagem) {
  const minha = mensagem.role === 'user';
  return el('div', { class: 'chat-msg', dataset: { role: mensagem.role } }, [
    el('div', { class: 'chat-msg__quem', text: assinatura(mensagem) }),
    el('div', { class: 'chat-msg__texto', text: mensagem.content }),
    // Proveniência: dá para conferir o que a IA sabia quando respondeu — e,
    // quando a resposta estiver errada, ver qual bloco estava velho.
    !minha && mensagem.context_summary
      ? el('details', { class: 'chat-msg__contexto' }, [
          el('summary', {
            text: `contexto: ${mensagem.context_tokens} tokens estimados`,
          }),
          el('p', { class: 'field__hint', text: mensagem.context_summary }),
        ])
      : null,
  ]);
}

function desligado(status) {
  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Cockpit AI' }),
      el('span', { class: 'panel__count', text: 'desligado' }),
    ]),
    el('div', { class: 'panel__body' }, [
      el('p', { text: status.reason ?? 'A IA está desligada.' }),
      el('p', { class: 'field__hint' }, [
        'Ligar é um ato fora da interface, de propósito: a partir daí, conteúdo ',
        'dos seus projetos passa a ser enviado ao provedor. Um projeto pode ser ',
        'excluído individualmente, e ',
        el('code', { text: '.env' }),
        ', chaves e credenciais nunca são lidos.',
      ]),
      el('pre', { class: 'code-block' }, [
        el('code', {
          text:
            '# .env, ao lado do executável\n' +
            'DEVCOCKPIT_AI_ENABLED=true\n' +
            'DEVCOCKPIT_AI_PROVIDER=anthropic   # ou openai, ou local\n' +
            'DEVCOCKPIT_AI_MODEL=claude-sonnet-5\n' +
            'DEVCOCKPIT_AI_API_KEY=...          # nunca vai para o banco\n' +
            'DEVCOCKPIT_AI_DAILY_TOKEN_BUDGET=200000',
        }),
      ]),
      el('p', { class: 'field__hint' }, [
        'Com ',
        el('code', { text: 'DEVCOCKPIT_AI_PROVIDER=local' }),
        ' (Ollama), nada sai da máquina e nenhuma chave é necessária.',
      ]),
    ]),
  ]);
}

/** Seletor entre os dois modelos configurados.
 *
 * Só aparece quando existe um segundo: oferecer escolha entre uma coisa só é
 * ruído. Os rótulos dizem o **efeito** — rápido, caprichado — e o nome do
 * modelo fica no `title`, porque é o efeito que decide o clique.
 *
 * A escolha fica no elemento e vai como `'default'` ou `'alt'`; o nome do
 * modelo nunca sai daqui para o servidor.
 */
function seletorDeModelo(status) {
  const caixa = el('div', { class: 'chat-modelo', role: 'group' });
  caixa.dataset.escolha = 'default';

  const opcoes = [
    { valor: 'default', rotulo: 'Rápido', modelo: status.model },
    { valor: 'alt', rotulo: 'Caprichado', modelo: status.model_alt },
  ];

  const botoes = opcoes.map(({ valor, rotulo, modelo }) => {
    const botao = el('button', {
      class: 'chat-modelo__opcao',
      type: 'button',
      text: rotulo,
      title: modelo,
      'aria-pressed': valor === 'default' ? 'true' : 'false',
    });
    botao.addEventListener('click', () => {
      caixa.dataset.escolha = valor;
      for (const outro of botoes) {
        const ativo = outro === botao;
        outro.setAttribute('aria-pressed', ativo ? 'true' : 'false');
      }
    });
    return botao;
  });

  caixa.append(...botoes);
  return caixa;
}

function medidor(status) {
  const teto = status.daily_budget || 0;
  const usado = status.tokens_today || 0;
  const fracao = teto ? Math.min(1, usado / teto) : 0;

  return el('div', { class: 'chat-uso' }, [
    // Com registro, quem responde é decidido por pergunta: o modelo do `.env`
    // aqui seria um rótulo errado na maior parte das respostas.
    status.modelos?.length
      ? null
      : el('span', { class: 'field__hint', text: `${status.provider} · ${status.model}` }),
    teto
      ? el('span', { class: 'field__hint' }, [
          `${usado.toLocaleString('pt-BR')} de ${teto.toLocaleString('pt-BR')} tokens hoje`,
          el('span', { class: 'bar' }, [
            el('span', {
              class: 'bar__fill',
              // Com qualquer gasto, no mínimo um ponto da altura da barra: 483
              // de 200.000 tokens dão 0,2 px, e a barra parecia sem uso nenhum.
              style: usado
                ? `width:max(6px, ${(fracao * 100).toFixed(1)}%)`
                : 'width:0',
            }),
          ]),
        ])
      : el('span', { class: 'field__hint', text: `${usado} tokens hoje · sem teto` }),
  ]);
}

export async function renderChatPanel(container, project) {
  let status;
  try {
    status = await api.aiStatus();
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  if (!status.enabled || !status.configured) {
    mount(container, desligado(status));
    return;
  }

  const historico = await api.chatHistory(project.id).catch(() => ({ items: [] }));
  const conversa = el(
    'div',
    { class: 'chat-fluxo' },
    historico.items.length
      ? historico.items.map(bolha)
      : [
          el('p', {
            class: 'panel__empty',
            text:
              'Pergunte sobre este projeto. O painel já manda o contexto: memória, ' +
              'última sessão, tarefas abertas e estado atual.',
          }),
        ]
  );

  // Especialistas e seus atalhos. Falhar aqui não impede o chat: sem a lista, o
  // roteamento automático do servidor continua valendo.
  let perfis = { items: [], padrao: 'fullstack' };
  try {
    perfis = await api.especialistas(project.id);
  } catch {
    /* sem chapéus na tela; o servidor escolhe sozinho, como antes. */
  }

  //: `null` = deixa a regra do servidor escolher. Fixar é escolha da pessoa.
  let fixado = null;

  const entrada = el('textarea', {
    class: 'input',
    rows: '2',
    placeholder: 'Pergunte, ou digite / para os comandos.',
  });
  const botao = el('button', { class: 'btn btn--primary', type: 'button' }, [
    icon('search', { size: 14 }),
    'Perguntar',
  ]);
  // O registro (`configs/ai.yml`) manda quando existe; sem ele, o seletor
  // antigo entre os dois modelos do `.env`. `null` quando não há escolha.
  const doRegistro = seletorDoRegistro(status);
  const seletor = doRegistro ?? (status.model_alt ? seletorDeModelo(status) : null);

  const perguntar = async () => {
    const digitado = entrada.value.trim();
    if (!digitado) return;

    // Comando vira pergunta com o chapéu certo já escolhido. Ele não abre
    // capacidade nova: economiza a digitação e a dúvida de qual perfil pediria
    // aquilo.
    const comando = interpretarComando(digitado);
    const pergunta = comando ? comando.pergunta : digitado;
    const agente = comando ? comando.agente : fixado;

    entrada.value = '';
    listaDeComandos.replaceChildren();
    botao.disabled = true;

    if (conversa.querySelector?.('.panel__empty')) conversa.replaceChildren();
    conversa.append(bolha({ role: 'user', content: comando ? digitado : pergunta }));

    // Só assina o chapéu quando ele foi escolhido aqui (comando ou seletor).
    // No modo automático quem escolhe é a regra do servidor, e o painel só
    // descobre qual foi ao recarregar o histórico — chutar seria pior.
    const quem = el('div', {
      class: 'chat-msg__quem',
      text: assinatura({ role: 'assistant', agent: agente }),
    });
    const resposta = el('div', { class: 'chat-msg', dataset: { role: 'assistant' } }, [quem]);
    const texto = el('div', { class: 'chat-msg__texto', text: '…' });
    resposta.append(texto);
    conversa.append(resposta);

    try {
      // Stream por SSE, mesmo transporte do console de job: a resposta aparece
      // conforme chega, em vez de o painel ficar mudo por dez segundos.
      await api.chatStream(project.id, pergunta, {
        model: doRegistro ? 'default' : (seletor?.dataset.escolha ?? 'default'),
        modelo: doRegistro?.value ?? '',
        agente,
        onMeta: (meta) => {
          const frase = quemRespondeu(meta);
          if (frase) quem.textContent += ` · ${frase}`;
        },
        onChunk: (pedaco) => {
          if (texto.textContent === '…') texto.textContent = '';
          texto.textContent += pedaco;
        },
        onError: (erro) => {
          texto.textContent = erro.message ?? 'Falhou.';
          resposta.dataset.error = 'true';
        },
      });
    } catch (error) {
      showError(error);
    } finally {
      botao.disabled = false;
    }
  };

  // --- chapéus, atalhos e comandos ---------------------------------------

  const listaDeComandos = el('div', { class: 'chat-comandos' });
  const barraDeAtalhos = el('div', { class: 'chat-atalhos' });

  function desenharAtalhos() {
    const perfil = perfis.items.find((p) => p.key === (fixado ?? perfis.padrao));
    const atalhos = perfil?.atalhos ?? [];

    mount(
      barraDeAtalhos,
      ...atalhos.map((proposta) =>
        el('button', {
          class: 'btn btn--sm',
          type: 'button',
          title: proposta.describe,
          text: proposta.label,
          onClick: async (evento) => {
            // Um clique em vez de uma frase. A execução é a mesma rota de
            // sempre, com o mesmo bilhete: a auditoria registra como ação
            // proposta pela IA e confirmada por você.
            const alvo = evento.currentTarget;
            alvo.disabled = true;
            try {
              await api.runProposal(proposta);
              toast(`${proposta.label}: ok.`, { kind: 'success' });
            } catch (erro) {
              showError(erro);
            } finally {
              // O bilhete valeu uma vez; recarrega para pegar outro.
              const novos = await api.especialistas(project.id).catch(() => perfis);
              perfis = novos;
              desenharAtalhos();
            }
          },
        })
      )
    );
  }

  const chapeus = el(
    'div',
    { class: 'chat-chapeus', role: 'group', 'aria-label': 'Especialista' },
    [
      el('button', {
        class: `filter-chip${fixado === null ? ' filter-chip--on' : ''}`,
        type: 'button',
        title: 'A regra do servidor escolhe pelo que você escrever.',
        text: 'Automático',
        onClick: () => {
          fixado = null;
          redesenharChapeus();
        },
      }),
      ...perfis.items.map((perfil) =>
        el('button', {
          class: 'filter-chip',
          type: 'button',
          title: perfil.descricao,
          text: perfil.label,
          onClick: () => {
            fixado = fixado === perfil.key ? null : perfil.key;
            redesenharChapeus();
          },
        })
      ),
    ]
  );

  function redesenharChapeus() {
    const botoes = [...chapeus.children];
    botoes.forEach((b, i) => {
      const chave = i === 0 ? null : perfis.items[i - 1]?.key;
      const ligado = chave === fixado;
      b.className = `filter-chip${ligado ? ' filter-chip--on' : ''}`;
      b.setAttribute('aria-pressed', String(ligado));
    });
    desenharAtalhos();
  }

  redesenharChapeus();

  entrada.addEventListener('input', () => {
    const casaram = sugerir(entrada.value);
    mount(
      listaDeComandos,
      ...casaram.map((comando) =>
        el('button', {
          class: 'chat-comando',
          type: 'button',
          onClick: () => {
            entrada.value = `${comando.nome} `;
            entrada.focus();
            listaDeComandos.replaceChildren();
          },
        }, [
          el('span', { class: 'chat-comando__nome', text: comando.nome }),
          el('span', { class: 'chat-comando__resumo', text: comando.resumo }),
        ])
      )
    );
  });

  botao.addEventListener('click', perguntar);
  entrada.addEventListener('keydown', (evento) => {
    // Enter envia, Shift+Enter quebra linha: é um chat, não um formulário.
    if (evento.key === 'Enter' && !evento.shiftKey) {
      evento.preventDefault();
      perguntar();
    }
  });

  mount(
    container,
    el('section', { class: 'panel' }, [
      el('header', { class: 'panel__header' }, [
        el('h2', { class: 'panel__title', text: 'Cockpit AI' }),
        ...(seletor ? [seletor] : []),
        medidor(status),
      ]),
      el('div', { class: 'panel__body' }, [
        chapeus,
        barraDeAtalhos,
        conversa,
        el('div', { class: 'chat-entrada' }, [listaDeComandos, entrada, botao]),
        el('p', {
          class: 'field__hint',
          text:
            `Comandos: ${COMANDOS.map((c) => c.nome).join(', ')}. ` +
            'O painel envia memória, sessões, tarefas e estado deste projeto. ' +
            'Arquivos de segredo nunca são lidos, e chaves em código saem redigidas.',
        }),
      ]),
    ])
  );
}
