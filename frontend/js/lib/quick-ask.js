// Pergunta rápida: o assistente de terminal, sem projeto e sem contexto.
//
// O chat da aba IA existe para falar *de um projeto* — ele manda memória,
// sessão, tarefas e README junto. Isso é certo lá e errado aqui: "como desfaço
// um commit?" não tem projeto, e num provedor local carregar contexto à toa
// triplica a espera (medido: ~17 s sem contexto, ~45 s com).
//
// Por isso este é um caminho separado, e não uma aba a mais: o que muda não é
// a aparência, é o que vai na requisição.
//
// Aberto por Ctrl+Espaço e pelo botão da barra superior. Ctrl+Espaço porque é
// gesto livre no navegador e no Windows, e porque a mão já está no teclado
// quando a dúvida aparece — que é o momento em que se decide entre perguntar
// aqui ou abrir outra coisa.

import { api } from './api.js';
import { el } from './dom.js';
import { icon } from './icons.js';
import { quemRespondeu, seletorDoRegistro } from './modelo-escolhido.js';
import { showError, toast } from './ui.js';

let aberta = null;

/** Estado do Cockpit AI, consultado uma vez por abertura.
 *
 * Não é cacheado entre aberturas de propósito: ligar a IA é editar o `.env` e
 * reiniciar, e o gasto do dia muda a cada pergunta. Um cache aqui mostraria
 * "0 tokens hoje" pelo resto da sessão.
 */
async function estado() {
  try {
    return await api.aiStatus();
  } catch {
    return null;
  }
}

function desligado(status) {
  const motivo =
    status?.reason ??
    'O Cockpit AI está desligado. Defina DEVCOCKPIT_AI_ENABLED=true no seu .env.';
  return el('p', { class: 'quick-ask__aviso', text: motivo });
}

function montar(status) {
  const fechar = () => {
    aberta?.remove();
    aberta = null;
    document.removeEventListener('keydown', aoTeclar, true);
  };

  function aoTeclar(evento) {
    if (evento.key !== 'Escape') return;
    evento.preventDefault();
    // `stopPropagation` porque Esc também limpa a busca global: fechar isto e
    // apagar o que a pessoa digitou lá com a mesma tecla seria surpresa.
    evento.stopPropagation();
    fechar();
  }

  const entrada = el('textarea', {
    class: 'input quick-ask__entrada',
    rows: '2',
    // O placeholder ensina as duas coisas que a caixa faz, porque uma delas
    // — mandar — não é adivinhável numa caixa de pergunta.
    placeholder: 'Pergunte ("como desfaço um commit?") ou mande ("sobe o kiteasy")',
  });
  const resposta = el('div', { class: 'quick-ask__resposta' });
  const rodape = el('div', { class: 'quick-ask__rodape' });

  /** Cartão de confirmação de uma ação proposta.
   *
   * Nunca executa sozinho o que não é leitura. O texto diz o que **vai**
   * acontecer, na segunda pessoa e no futuro, porque é uma promessa — e a
   * pessoa precisa poder recusar antes, não desfazer depois.
   */
  const cartaoDeAcao = (proposta) => {
    const cartao = el('div', { class: 'quick-ask__acao' }, [
      el('div', { class: 'quick-ask__acao-topo' }, [
        icon('power', { size: 14 }),
        el('span', { class: 'quick-ask__acao-nome', text: proposta.label }),
        proposta.project_name
          ? el('span', { class: 'quick-ask__acao-proj', text: proposta.project_name })
          : null,
      ]),
      el('p', { class: 'quick-ask__acao-texto', text: proposta.describe }),
    ]);

    const confirmar = el('button', { class: 'btn btn--primary btn--sm', type: 'button' }, [
      icon('check', { size: 13 }),
      'Confirmar',
    ]);
    const cancelar = el('button', {
      class: 'btn btn--sm',
      type: 'button',
      text: 'Cancelar',
      onClick: () => {
        resposta.replaceChildren(
          el('p', { class: 'field__hint', text: 'Cancelado. Nada foi executado.' })
        );
      },
    });

    confirmar.addEventListener('click', async () => {
      confirmar.disabled = true;
      cancelar.disabled = true;
      cartao.dataset.executando = 'true';
      try {
        await api.runProposal(proposta);
        toast(`${proposta.label}: ok.`, { kind: 'success' });
        resposta.replaceChildren(
          el('p', { class: 'field__hint', text: `${proposta.label} — feito.` })
        );
        // O resto da tela precisa saber: o trilho de ativos e os cards de
        // projeto mostram estado que acabou de mudar.
        window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
      } catch (error) {
        showError(error);
        confirmar.disabled = false;
        cancelar.disabled = false;
        delete cartao.dataset.executando;
      }
    });

    cartao.append(el('div', { class: 'quick-ask__acao-botoes' }, [confirmar, cancelar]));
    return cartao;
  };

  // Com registro, o modelo é escolhido aqui, e a mesma escolha vale no chat.
  const doRegistro = status.enabled && status.configured ? seletorDoRegistro(status) : null;

  const perguntar = async (texto, perfil) => {
    entrada.disabled = true;
    resposta.replaceChildren(el('span', { class: 'loading', text: 'Pensando…' }));
    rodape.replaceChildren();

    // Primeiro: isto é uma ordem? A maioria das frases resolve por regra no
    // servidor em milissegundos, então perguntar isso antes quase não custa —
    // e quando é ordem, o caminho do texto nem chega a ser aberto.
    try {
      const { proposal } = await api.proposeAction(texto, perfil);
      if (proposal) {
        entrada.disabled = false;
        entrada.focus();
        if (proposal.needs_confirmation) {
          resposta.replaceChildren(cartaoDeAcao(proposal));
        } else {
          // Leitura não precisa de confirmação, mas continua sendo ação: o
          // cartão aparece já executando, para a pessoa ver o que foi feito.
          resposta.replaceChildren(cartaoDeAcao(proposal));
          resposta.querySelector('.btn--primary')?.click();
        }
        return;
      }
    } catch {
      // Falhar a proposta não pode impedir a pergunta: o caminho de texto
      // continua valendo, e é o mais usado.
    }

    const saida = el('div', { class: 'quick-ask__texto', text: '' });
    let primeiro = true;
    let meta = null;

    try {
      await api.askQuick(texto, {
        model: perfil,
        modelo: doRegistro?.value ?? '',
        onMeta: (dados) => {
          meta = dados;
        },
        onChunk: (pedaco) => {
          if (primeiro) {
            resposta.replaceChildren(saida);
            primeiro = false;
          }
          saida.textContent += pedaco;
        },
        onError: (erro) => {
          resposta.replaceChildren(
            el('p', { class: 'quick-ask__aviso', text: erro.message ?? 'Falhou.' })
          );
        },
      });
    } catch (error) {
      showError(error);
      fechar();
      return;
    } finally {
      entrada.disabled = false;
      entrada.focus();
    }

    // "Refazer com o caprichado" só depois da primeira resposta, e só quando
    // ela veio do modelo rápido. É a orquestração barata: o modelo pequeno
    // responde sempre, o grande é a segunda tentativa — custa zero quando o
    // pequeno acerta, e ele acerta na maioria.
    if (doRegistro) {
      const frase = quemRespondeu(meta);
      if (frase && !primeiro) rodape.replaceChildren(el('span', { class: 'field__hint', text: frase }));
      return;
    }

    if (perfil === 'default' && status.model_alt && !primeiro) {
      const refazer = el('button', { class: 'btn btn--sm', type: 'button' }, [
        icon('refresh', { size: 13 }),
        'Refazer com o caprichado',
      ]);
      refazer.title = status.model_alt;
      refazer.addEventListener('click', () => perguntar(texto, 'alt'));
      rodape.replaceChildren(refazer);
    }
  };

  entrada.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter' || evento.shiftKey) return;
    evento.preventDefault();
    const texto = entrada.value.trim();
    if (texto) perguntar(texto, 'default');
  });

  const painel = el(
    'div',
    {
      class: 'quick-ask',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': 'Pergunta rápida',
    },
    [
      el('div', { class: 'quick-ask__head' }, [
        icon('terminal', { size: 15 }),
        el('h2', { text: 'Pergunta rápida' }),
        // O modelo aparece porque a espera depende dele: saber que o rápido
        // está respondendo explica por que voltou em 10 s e não em 40. Com
        // registro, é a escolha em si que aparece — automático ou fixado.
        doRegistro ?? el('span', {
          class: 'field__hint',
          text: status.enabled && status.configured ? status.model : '—',
        }),
        el('button', { class: 'btn btn--sm', type: 'button', text: 'Fechar', onClick: fechar }),
      ]),
      status.enabled && status.configured ? entrada : desligado(status),
      resposta,
      rodape,
      el('p', {
        class: 'field__hint',
        text:
          'Sem contexto de projeto: nada do seu código é enviado, só a frase. '
          + 'Ação só acontece depois de você confirmar. '
          + 'Confira comandos destrutivos antes de rodar.',
      }),
    ]
  );

  const fundo = el('div', { class: 'quick-ask__backdrop', onClick: fechar });
  aberta = el('div', { class: 'quick-ask__layer' }, [fundo, painel]);
  document.body.append(aberta);
  document.addEventListener('keydown', aoTeclar, true);
  entrada.focus();
}

/** Abre a pergunta rápida, ou fecha se já estiver aberta. */
export async function toggleQuickAsk() {
  if (aberta) {
    aberta.remove();
    aberta = null;
    return;
  }
  const status = await estado();
  montar(status ?? { enabled: false, configured: false, model: '', model_alt: '' });
}

/** Liga o Ctrl+Espaço global. Chamado uma vez, na partida. */
export function wireQuickAsk() {
  document.addEventListener('keydown', (evento) => {
    if (!(evento.ctrlKey || evento.metaKey) || evento.code !== 'Space') return;
    evento.preventDefault();
    toggleQuickAsk();
  });
}
