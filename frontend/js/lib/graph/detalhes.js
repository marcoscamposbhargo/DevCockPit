// O que um projeto tem dentro: tarefas, sessões, decisões e serviços.
//
// MVP 3 do HyperBrain. O desenho em `docs/ai/HYPERBRAIN.md` fala em "clique no
// nó → tasks() | sessions() | memory() | services()", sugerindo satélites no
// grafo. Aqui eles viram **seções do painel de contexto**, por decisão tomada
// com o usuário em 2026-09-20: com 19 projetos, um satélite por tarefa daria
// centenas de nós na tela — exatamente o risco 4 que o próprio documento
// levanta ("virar enfeite"). A informação é a mesma; o mapa continua legível.
//
// Duas regras que o resto da tela também segue:
//
// 1. **Uma chamada por clique, nunca tudo de uma vez.** Abrir um projeto não
//    dispara quatro requisições; cada seção busca o seu quando é aberta, e só
//    na primeira vez.
// 2. **Nada é inventado.** Lista vazia diz que está vazia. Falha de rede diz
//    que falhou. Nenhuma das duas vira zero nem sumiço silencioso (**P-02**).

import { api } from '../api.js';
import { el, mount } from '../dom.js';
import { relativeTime } from '../format.js';

//: Quantos itens a seção mostra antes de parar. O painel é estreito e a
//: pergunta aqui é "o que tem neste projeto?", não "me dê o histórico
//: inteiro" — para isso existem as telas próprias de cada assunto.
const TETO = 8;

/** Rótulo e ordem das seções. A ordem é a do trabalho: o que fazer, o que foi
 *  feito, o que se aprendeu, e o que está de pé. */
const SECOES = [
  { chave: 'tarefas', titulo: 'Tarefas', carregar: (id) => api.tasks(id), render: itensDeTarefa },
  { chave: 'sessoes', titulo: 'Sessões', carregar: (id) => api.sessions(id), render: itensDeSessao },
  { chave: 'decisoes', titulo: 'Decisões', carregar: (id) => api.memory(id), render: itensDeMemoria },
  {
    chave: 'servicos',
    titulo: 'Serviços',
    carregar: (id) => api.listServices(id),
    render: itensDeServico,
  },
];

function linha(titulo, detalhe, extra = null) {
  return el('li', { class: 'hb-detalhe__item' }, [
    el('span', { class: 'hb-detalhe__titulo', text: titulo }),
    detalhe ? el('span', { class: 'hb-detalhe__meta', text: detalhe }) : null,
    extra,
  ]);
}

function itensDeTarefa(dados) {
  const itens = dados.items ?? [];
  // Abertas primeiro: é o que se quer ver ao abrir um projeto. Dentro de cada
  // grupo vale a ordem que a rota devolveu.
  const ordenadas = [...itens.filter((t) => t.is_open), ...itens.filter((t) => !t.is_open)];
  return ordenadas.slice(0, TETO).map((t) =>
    linha(
      t.title,
      t.is_open ? 'aberta' : t.status === 'DROPPED' ? 'descartada' : 'concluída',
      el('span', { class: `hb-detalhe__pip hb-detalhe__pip--${t.is_open ? 'aberta' : 'fechada'}` })
    )
  );
}

function itensDeSessao(dados) {
  return (dados.items ?? []).slice(0, TETO).map((s) => {
    const minutos = s.facts?.duration_minutes;
    const quando = s.started_at ? relativeTime(s.started_at) : 'sem data';
    // Sessão aberta não tem duração, e inventar uma ("0 min") seria afirmar o
    // que não terminou. Diz que está aberta.
    const detalhe = s.is_open
      ? `${quando} · em aberto`
      : minutos
        ? `${quando} · ${minutos} min`
        : quando;
    return linha(s.objective || 'Sessão sem objetivo declarado', detalhe);
  });
}

function itensDeMemoria(dados) {
  return (dados.items ?? [])
    .slice(0, TETO)
    .map((m) => linha(m.content ?? m.title ?? 'registro', m.kind ?? null));
}

function itensDeServico(dados) {
  return (dados.items ?? []).slice(0, TETO).map((s) => {
    const estado = (s.state ?? 'desconhecido').toLowerCase();
    return linha(
      s.label || s.key,
      `${s.host ?? 'localhost'}:${s.port} · ${estado}`,
      el('span', { class: `hb-detalhe__pip hb-detalhe__pip--${estado}` })
    );
  });
}

/** Uma seção que só busca quando é aberta, e só na primeira vez.
 *
 * O estado vive no fecho: `carregado` impede refazer a chamada ao reabrir, e
 * `emCurso` impede duas chamadas se alguém clicar rápido duas vezes.
 */
function criarSecao(secao, projetoId) {
  // `hidden` é definido como propriedade, não por `el({ hidden: true })`: o
  // helper faria `setAttribute('hidden','')`, e depender da reflexão
  // atributo↔propriedade é contar com um comportamento de navegador que o
  // resto deste código não precisa. Uma fonte de verdade só.
  const corpo = el('div', { class: 'hb-detalhe__corpo' });
  corpo.hidden = true;
  let carregado = false;
  let emCurso = false;

  const botao = el('button', {
    class: 'hb-detalhe__cabecalho',
    type: 'button',
    'aria-expanded': 'false',
    onClick: alternar,
  }, [
    el('span', { class: 'hb-detalhe__seta', 'aria-hidden': 'true', text: '›' }),
    el('span', { text: secao.titulo }),
  ]);

  async function buscar() {
    if (carregado || emCurso) return;
    emCurso = true;
    mount(corpo, el('p', { class: 'field__hint', text: 'carregando…' }));
    try {
      const dados = await secao.carregar(projetoId);
      const itens = secao.render(dados);
      const total = (dados.items ?? []).length;
      mount(
        corpo,
        itens.length
          ? el('ul', { class: 'hb-detalhe__lista' }, itens)
          : el('p', { class: 'field__hint', text: 'nada registrado' }),
        // Só avisa do corte quando ele de fato aconteceu: dizer "8 de 8"
        // seria ruído.
        total > TETO
          ? el('p', { class: 'field__hint', text: `mostrando ${TETO} de ${total}` })
          : null
      );
      carregado = true;
    } catch (erro) {
      // Falha vira texto na própria seção, e não some nem vira lista vazia:
      // "nada registrado" e "não consegui perguntar" são coisas diferentes.
      mount(corpo, el('p', { class: 'field__hint', text: `não carregou: ${erro.message}` }));
    } finally {
      emCurso = false;
    }
  }

  function alternar() {
    const abrindo = corpo.hidden;
    corpo.hidden = !abrindo;
    botao.setAttribute('aria-expanded', String(abrindo));
    if (abrindo) buscar();
  }

  return el('div', { class: 'hb-detalhe' }, [botao, corpo]);
}

/**
 * As quatro seções de um projeto, fechadas.
 *
 * @param {string} projetoId  id do projeto, sem o prefixo `p:` do nó
 */
export function detalhesDoProjeto(projetoId) {
  return el(
    'div',
    { class: 'hb-panel__bloco hb-detalhes' },
    SECOES.map((secao) => criarSecao(secao, projetoId))
  );
}
