// HyperBrain — o ecossistema de projetos como grafo.
//
// A lista de projetos responde bem "quais são os meus projetos" e mal "o que
// este projeto tem a ver com aquele". Esta tela existe para a segunda pergunta,
// e só para ela: quem abre, liga, para ou configura projeto continua sendo o
// resto do painel. Daqui se olha e se navega.
//
// Duas promessas que o código precisa manter:
//
// 1. **Nada é inventado.** Só existe aresta entre coisas que o painel já sabia
//    que estavam ligadas — tecnologia declarada, projeto cadastrado. Nenhuma
//    afinidade deduzida, nenhuma relação "provável".
// 2. **A tela funciona com o Cockpit AI desligado.** O grafo é dado, não IA. O
//    núcleo apenas *diz* o estado da IA, e diz a verdade sobre ele.
//
// Ver `docs/ai/HYPERBRAIN.md` e `docs/adr/ADR-009-graph-rendering.md`.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { montarGrafo, tecnologiasExclusivas, vizinhos } from '../lib/graph/adapter.js';
import { criarNucleo } from '../lib/graph/core.js';
import { ligarInteracao } from '../lib/graph/interaction.js';
import { criarLayout } from '../lib/graph/layout.js';
import { aplicarDestaque, aplicarPosicoes, criarPalco, desenharAresta, desenharNo } from '../lib/graph/render.js';
import { criarEstado, definirMovimento, movimentoReduzido } from '../lib/graph/state.js';
import { icon } from '../lib/icons.js';
import { emptyState, loading, showError, statusBadge, techChip } from '../lib/ui.js';
import { aoSairDaRota } from '../router.js';

//: Acima disto, partículas e arestas animadas saem. O limite não é estético:
//: é onde o custo por quadro começa a aparecer em máquina modesta.
const NOS_PARA_MODO_DENSO = 150;

const LEGENDA = [
  ['core', 'núcleo'],
  ['projeto', 'projeto'],
  ['tecnologia', 'tecnologia compartilhada'],
];

function botao(rotulo, nomeIcone, aoClicar, { titulo = rotulo } = {}) {
  return el('button', {
    class: 'btn btn--sm hb-tool',
    type: 'button',
    title: titulo,
    'aria-label': titulo,
    onClick: aoClicar,
  }, [icon(nomeIcone, { size: 14 }), el('span', { class: 'hb-tool__label', text: rotulo })]);
}

/** Painel lateral de um projeto. Contexto e dois caminhos — não um dashboard. */
function painelDeProjeto(no, grafo, { aoFocar, emFoco }) {
  const projeto = no.projeto;
  const exclusivas = tecnologiasExclusivas(projeto, grafo);
  const compartilhadas = (projeto.technologies ?? []).filter((t) => !exclusivas.includes(t));

  return el('aside', { class: 'hb-panel', 'aria-label': `Contexto de ${projeto.name}` }, [
    el('header', { class: 'hb-panel__head' }, [
      el('h2', { class: 'hb-panel__name', text: projeto.name }),
      statusBadge(projeto.status),
    ]),

    el('p', { class: 'hb-panel__path', text: projeto.path }),

    compartilhadas.length
      ? el('div', { class: 'hb-panel__bloco' }, [
          el('span', { class: 'field__label', text: 'Compartilhadas no grafo' }),
          el('div', { class: 'chip-row' }, compartilhadas.map((t) => techChip(t))),
        ])
      : null,

    exclusivas.length
      ? el('div', { class: 'hb-panel__bloco' }, [
          el('span', { class: 'field__label', text: 'Só deste projeto' }),
          el('div', { class: 'chip-row' }, exclusivas.map((t) => techChip(t))),
        ])
      : null,

    el('div', { class: 'hb-panel__bloco' }, [
      el('span', { class: 'field__label', text: 'Último acesso' }),
      el('p', {
        text: projeto.last_accessed_at
          ? relativeTime(projeto.last_accessed_at)
          : 'nunca aberto pelo painel',
      }),
    ]),

    projeto.services_total
      ? el('p', { class: 'field__hint', text: `${projeto.services_total} serviço(s) declarado(s)` })
      : null,

    el('div', { class: 'hb-panel__acoes' }, [
      el('a', {
        class: 'btn btn--sm btn--primary',
        href: `#/projects/${encodeURIComponent(projeto.id)}`,
        text: 'Abrir projeto',
      }),
      el('button', {
        class: 'btn btn--sm',
        type: 'button',
        text: emFoco ? 'Sair do foco' : 'Focar',
        onClick: aoFocar,
      }),
    ]),

    el('p', {
      class: 'field__hint',
      text: 'Ligar, parar, portas e Git continuam na tela do projeto — aqui só se olha e se navega.',
    }),
  ]);
}

function painelDeTecnologia(no, grafo, { aoFocar, emFoco }) {
  const usam = grafo.arestas
    .filter((a) => a.para === no.id)
    .map((a) => grafo.nos.find((n) => n.id === a.de))
    .filter(Boolean);

  return el('aside', { class: 'hb-panel', 'aria-label': `Contexto de ${no.rotulo}` }, [
    el('header', { class: 'hb-panel__head' }, [
      el('h2', { class: 'hb-panel__name', text: no.rotulo }),
      el('span', { class: 'tech-chip', text: `${usam.length} projetos` }),
    ]),

    el('div', { class: 'hb-panel__bloco' }, [
      el('span', { class: 'field__label', text: 'Usada por' }),
      el(
        'ul',
        { class: 'hb-panel__lista' },
        usam.map((projetoNo) =>
          el('li', {}, [
            el('a', {
              href: `#/projects/${encodeURIComponent(projetoNo.projeto.id)}`,
              text: projetoNo.rotulo,
            }),
          ])
        )
      ),
    ]),

    el('div', { class: 'hb-panel__acoes' }, [
      el('button', {
        class: 'btn btn--sm',
        type: 'button',
        text: emFoco ? 'Sair do foco' : 'Focar',
        onClick: aoFocar,
      }),
    ]),
  ]);
}

function painelDoNucleo(status) {
  const linhas = [];

  if (!status) {
    linhas.push('Não foi possível ler o estado do Cockpit AI.');
  } else if (!status.enabled || !status.configured) {
    linhas.push(status.reason ?? 'O Cockpit AI está desligado.');
  } else {
    linhas.push(`${status.provider} · ${status.model}`);
    if (status.daily_budget) {
      linhas.push(`${status.tokens_today} de ${status.daily_budget} tokens hoje`);
    }
  }

  return el('aside', { class: 'hb-panel', 'aria-label': 'Núcleo' }, [
    el('header', { class: 'hb-panel__head' }, [el('h2', { class: 'hb-panel__name', text: 'HyperBrain' })]),
    ...linhas.map((texto) => el('p', { class: 'hb-panel__path', text: texto })),
    el('p', {
      class: 'field__hint',
      text:
        'Este grafo é montado do que o painel já registrou — projetos cadastrados e ' +
        'tecnologias detectadas. Nada aqui passa por modelo de IA.',
    }),
  ]);
}

export async function renderHyperbrain(container) {
  mount(container, loading('Montando o mapa…'));

  let projetos;
  try {
    // Limite alto e uma chamada só: o grafo precisa de todos, e paginar aqui
    // faria a tela desenhar metade do ecossistema como se fosse ele inteiro.
    const dados = await api.listProjects({ limit: 200 });
    projetos = dados.items;
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  if (!projetos.length) {
    mount(
      container,
      emptyState({
        iconName: 'layers',
        title: 'Nenhum projeto para desenhar',
        text: 'O HyperBrain mostra o que já está cadastrado. Cadastre ou importe um projeto primeiro.',
        actions: [el('a', { class: 'btn btn--primary', href: '#/projects', text: 'Ir para Projects' })],
      })
    );
    return;
  }

  // O estado da IA é lido para o núcleo poder dizer a verdade. Falhar aqui não
  // impede nada: o grafo não depende de IA nenhuma.
  let statusIa = null;
  try {
    statusIa = await api.aiStatus();
  } catch {
    statusIa = null;
  }

  const grafo = montarGrafo(projetos);
  const estado = criarEstado();
  const palco = criarPalco();
  const layout = criarLayout(grafo.nos, grafo.arestas);

  const elementosDeNo = new Map();
  const elementosDeAresta = new Map();

  for (const aresta of grafo.arestas) {
    const linha = desenharAresta(aresta);
    elementosDeAresta.set(aresta.id, linha);
    palco.arestas.append(linha);
  }

  const nucleo = criarNucleo();
  elementosDeNo.set('core', nucleo.no);
  palco.nos.append(nucleo.no);

  for (const no of grafo.nos) {
    if (no.tipo === 'core') continue;
    const elemento = desenharNo(no);
    elementosDeNo.set(no.id, elemento);
    palco.nos.append(elemento);
  }

  nucleo.definirEstado(statusIa?.enabled && statusIa?.configured ? 'idle' : 'desligado');

  const alvos = { elementosDeNo, elementosDeAresta, arestas: grafo.arestas };
  const denso = grafo.nos.length > NOS_PARA_MODO_DENSO;
  let movimentoCurto = movimentoReduzido();

  palco.svg.dataset.denso = String(denso);
  palco.svg.dataset.movimento = movimentoCurto ? 'reduzido' : 'completo';

  // --- painel lateral -----------------------------------------------------

  const painel = el('div', { class: 'hb-side' });

  function redesenharPainel() {
    const id = estado.get('selecionado');
    if (!id) {
      mount(
        painel,
        el('aside', { class: 'hb-panel hb-panel--vazio' }, [
          el('p', { text: 'Selecione um nó para ver o contexto dele.' }),
          el('p', {
            class: 'field__hint',
            text: 'Arraste para organizar, role para aproximar, Esc sai do foco.',
          }),
        ])
      );
      return;
    }

    if (id === 'core') {
      mount(painel, painelDoNucleo(statusIa));
      return;
    }

    const no = grafo.nos.find((n) => n.id === id);
    if (!no) return;

    const emFoco = estado.get('foco') === id;
    const alternarFoco = () => estado.definir({ foco: emFoco ? null : id });

    mount(
      painel,
      no.tipo === 'tecnologia'
        ? painelDeTecnologia(no, grafo, { aoFocar: alternarFoco, emFoco })
        : painelDeProjeto(no, grafo, { aoFocar: alternarFoco, emFoco })
    );
  }

  function redesenharDestaque() {
    const foco = estado.get('foco');
    aplicarDestaque(alvos, {
      foco,
      proximos: foco ? vizinhos(grafo, foco) : new Set(),
      destacados: estado.get('destacados'),
      selecionado: estado.get('selecionado'),
    });
  }

  estado.aoMudar(() => {
    redesenharPainel();
    redesenharDestaque();
  });

  // --- laço de desenho ----------------------------------------------------

  let quadro = null;
  let vivo = true;
  //: Enquadrar no meio do movimento faria a câmera perseguir nós que ainda
  //: estão se acomodando. Espera-se a simulação parar, e aí se enquadra uma vez.
  let enquadrarAoParar = true;

  function desenharUmaVez() {
    aplicarPosicoes(layout.posicoes(), alvos);
  }

  function laco() {
    quadro = null;
    if (!vivo) return;

    // Aba escondida não precisa de simulação. Sem isto, o painel deixado
    // aberto atrás de outra janela continuaria consumindo CPU o dia inteiro.
    if (document.visibilityState === 'hidden') return;

    const continua = layout.passo();
    desenharUmaVez();

    if (continua) {
      quadro = window.requestAnimationFrame(laco);
      return;
    }

    if (enquadrarAoParar) {
      enquadrarAoParar = false;
      interacao.enquadrar(layout.posicoes());
    }
  }

  function acordar() {
    if (!vivo || movimentoCurto) return;
    if (quadro === null) quadro = window.requestAnimationFrame(laco);
  }

  function aoTrocarVisibilidade() {
    if (document.visibilityState === 'visible') acordar();
  }

  document.addEventListener('visibilitychange', aoTrocarVisibilidade);

  // Esc vive no documento, e não no palco: sair do foco costuma ser pedido
  // logo depois de clicar no botão do painel lateral — e aí o foco do teclado
  // está no botão, longe do SVG. Preso ao palco, o atalho só funcionava se a
  // pessoa tivesse clicado num nó antes, que é justamente quando ela não
  // precisa dele.
  function aoTeclarNoDocumento(evento) {
    if (evento.key !== 'Escape') return;
    if (!estado.get('foco') && !estado.get('selecionado')) return;
    estado.definir({ foco: null, selecionado: null });
  }

  document.addEventListener('keydown', aoTeclarNoDocumento);

  // --- montagem -----------------------------------------------------------

  const interacao = ligarInteracao(
    { svg: palco.svg, viewport: palco.viewport, layout, palco: palco.svg },
    {
      aoSelecionar: (id) => estado.definir({ selecionado: id ?? null }),
      aoMover: () => {
        if (movimentoCurto) {
          layout.estabilizar(60);
          desenharUmaVez();
        } else acordar();
      },
      aoReenquadrar: () => {
        if (movimentoCurto) {
          layout.estabilizar();
          desenharUmaVez();
          interacao.enquadrar(layout.posicoes());
        } else enquadrarAoParar = true;
      },
    }
  );

  function alternarMovimento() {
    movimentoCurto = !movimentoCurto;
    definirMovimento(movimentoCurto);
    palco.svg.dataset.movimento = movimentoCurto ? 'reduzido' : 'completo';
    if (movimentoCurto) {
      if (quadro !== null) window.cancelAnimationFrame(quadro);
      quadro = null;
      layout.estabilizar();
      desenharUmaVez();
    } else {
      layout.reaquecer(0.5);
      acordar();
    }
    montarBarra();
  }

  const barra = el('div', { class: 'hb-bar' });

  function montarBarra() {
    mount(
      barra,
      el('div', { class: 'hb-bar__titulo' }, [
        el('h1', { text: 'HyperBrain' }),
        el('p', {
          class: 'field__hint',
          text: `${projetos.length} projetos · ${grafo.nos.length} nós · ${grafo.arestas.length} conexões`,
        }),
      ]),
      el('div', { class: 'hb-bar__acoes' }, [
        botao('Aproximar', 'plus', () => interacao.ampliar()),
        botao('Afastar', 'chevron', () => interacao.reduzir(), { titulo: 'Afastar' }),
        botao('Enquadrar', 'grid', () => interacao.enquadrar(layout.posicoes()), {
          titulo: 'Enquadrar o grafo inteiro na tela',
        }),
        botao('Reorganizar', 'refresh', () => interacao.reorganizar(grafo.nos)),
        botao(movimentoCurto ? 'Movimento: reduzido' : 'Movimento: completo', 'pulse', alternarMovimento, {
          titulo: 'Alternar animação do grafo',
        }),
      ])
    );
  }

  montarBarra();

  mount(
    container,
    el('div', { class: 'hb', dataset: { movimento: movimentoCurto ? 'reduzido' : 'completo' } }, [
      barra,
      el('div', { class: 'hb-body' }, [
        el('div', { class: 'hb-stage-wrap' }, [
          palco.svg,
          el(
            'ul',
            { class: 'hb-legend', 'aria-label': 'Tipos de nó' },
            LEGENDA.map(([tipo, rotulo]) =>
              el('li', { class: 'hb-legend__item', dataset: { tipo } }, [
                el('span', { class: 'hb-legend__mark', 'aria-hidden': 'true' }),
                rotulo,
              ])
            )
          ),
        ]),
        painel,
      ]),
    ])
  );

  redesenharPainel();
  redesenharDestaque();

  // A câmera só pode ser centralizada depois da montagem: antes disso o SVG
  // não tem tamanho, e dividir por zero deixaria tudo no canto.
  interacao.centralizar();

  if (movimentoCurto) {
    // Sem animação: estabiliza de uma vez e desenha o resultado. A tela
    // continua inteira — o que se perde é só o caminho até ela.
    layout.estabilizar();
    desenharUmaVez();
    interacao.enquadrar(layout.posicoes());
    enquadrarAoParar = false;
  } else {
    acordar();
  }

  aoSairDaRota(() => {
    vivo = false;
    if (quadro !== null) window.cancelAnimationFrame(quadro);
    quadro = null;
    document.removeEventListener('visibilitychange', aoTrocarVisibilidade);
    document.removeEventListener('keydown', aoTeclarNoDocumento);
    interacao.destruir();
  });
}
