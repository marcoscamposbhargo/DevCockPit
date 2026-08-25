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
import { el, mount } from '../lib/dom.js';
import { icon } from '../lib/icons.js';
import { showError } from '../lib/ui.js';

function bolha(mensagem) {
  const minha = mensagem.role === 'user';
  return el('div', { class: 'chat-msg', dataset: { role: mensagem.role } }, [
    el('div', { class: 'chat-msg__quem', text: minha ? 'você' : 'Cockpit AI' }),
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

function medidor(status) {
  const teto = status.daily_budget || 0;
  const usado = status.tokens_today || 0;
  const fracao = teto ? Math.min(1, usado / teto) : 0;

  return el('div', { class: 'chat-uso' }, [
    el('span', { class: 'field__hint', text: `${status.provider} · ${status.model}` }),
    teto
      ? el('span', { class: 'field__hint' }, [
          `${usado.toLocaleString('pt-BR')} de ${teto.toLocaleString('pt-BR')} tokens hoje`,
          el('span', { class: 'bar' }, [
            el('span', {
              class: 'bar__fill',
              style: `width:${(fracao * 100).toFixed(1)}%`,
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

  const entrada = el('textarea', {
    class: 'input',
    rows: '2',
    placeholder: 'O que você quer saber sobre este projeto?',
  });
  const botao = el('button', { class: 'btn btn--primary', type: 'button' }, [
    icon('search', { size: 14 }),
    'Perguntar',
  ]);

  const perguntar = async () => {
    const pergunta = entrada.value.trim();
    if (!pergunta) return;

    entrada.value = '';
    botao.disabled = true;

    if (conversa.querySelector?.('.panel__empty')) conversa.replaceChildren();
    conversa.append(bolha({ role: 'user', content: pergunta }));

    const resposta = el('div', { class: 'chat-msg', dataset: { role: 'assistant' } }, [
      el('div', { class: 'chat-msg__quem', text: 'Cockpit AI' }),
    ]);
    const texto = el('div', { class: 'chat-msg__texto', text: '…' });
    resposta.append(texto);
    conversa.append(resposta);

    try {
      // Stream por SSE, mesmo transporte do console de job: a resposta aparece
      // conforme chega, em vez de o painel ficar mudo por dez segundos.
      await api.chatStream(project.id, pergunta, {
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
        medidor(status),
      ]),
      el('div', { class: 'panel__body' }, [
        conversa,
        el('div', { class: 'chat-entrada' }, [entrada, botao]),
        el('p', {
          class: 'field__hint',
          text:
            'O painel envia memória, sessões, tarefas e estado deste projeto. ' +
            'Arquivos de segredo nunca são lidos, e chaves em código saem redigidas.',
        }),
      ]),
    ])
  );
}
