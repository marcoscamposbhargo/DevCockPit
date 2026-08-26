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
import {
  estadoDoProjeto,
  montarGrafo,
  tecnologiasExclusivas,
  vizinhos,
} from '../lib/graph/adapter.js';
import { criarNucleo, ESTADOS } from '../lib/graph/core.js';
import { ligarInteracao } from '../lib/graph/interaction.js';
import { criarLayout } from '../lib/graph/layout.js';
import {
  ajustarRotulos,
  iluminar,
  aplicarDestaque,
  aplicarPosicoes,
  criarPalco,
  desenharAresta,
  desenharNo,
} from '../lib/graph/render.js';
import { posicionarRotulos } from '../lib/graph/labels.js';
import { interpretar, pareceOrdem } from '../lib/graph/intent.js';
import { criarEstado, definirMovimento, movimentoReduzido } from '../lib/graph/state.js';
import { icon } from '../lib/icons.js';
import { emptyState, loading, showError, statusBadge, techChip } from '../lib/ui.js';
import { aoSairDaRota } from '../router.js';

//: Acima disto, partículas e arestas animadas saem. O limite não é estético:
//: é onde o custo por quadro começa a aparecer em máquina modesta.
const NOS_PARA_MODO_DENSO = 150;

const CHAVE_MODO = 'devcockpit:hyperbrain:modo';

/** A máquina desenha em WebGL? Sem isso, não há 3D possível. */
function suportaWebgl() {
  try {
    const tela = document.createElement('canvas');
    return Boolean(tela.getContext('webgl2') || tela.getContext('webgl'));
  } catch {
    return false;
  }
}

/** `3d` por padrão; `2d` quando a pessoa escolhe, ou quando não há WebGL.
 *
 * O mapa em SVG não foi aposentado: ele é a saída quando o WebGL falta — e ele
 * é o único dos dois onde cada nó é um elemento real, alcançável por `Tab`.
 */
function modoEscolhido() {
  if (!suportaWebgl()) return '2d';
  try {
    return window.localStorage.getItem(CHAVE_MODO) === '2d' ? '2d' : '3d';
  } catch {
    return '3d';
  }
}

function guardarModo(modo) {
  try {
    window.localStorage.setItem(CHAVE_MODO, modo);
  } catch {
    // Preferência que não persiste ainda vale para esta sessão.
  }
}

const LEGENDA = [
  ['core', 'núcleo'],
  ['projeto', 'projeto'],
  ['tecnologia', 'tecnologia compartilhada'],
];

/** Controle do mapa: ícone, sem rótulo.
 *
 * Cinco botões com texto comiam metade da largura do topo e competiam com o
 * título. Num mapa, zoom e enquadramento são gesto conhecido — o ícone basta,
 * e o nome vive no `title` e no `aria-label`, onde o teclado e o leitor de tela
 * também o alcançam.
 */
function controle(titulo, nomeIcone, aoClicar, { pressionado = null } = {}) {
  return el('button', {
    class: 'hb-ctl',
    type: 'button',
    title: titulo,
    'aria-label': titulo,
    'aria-pressed': pressionado === null ? null : String(pressionado),
    onClick: aoClicar,
  }, [icon(nomeIcone, { size: 15 })]);
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

/** O que o filtro local encontrou. Sem IA, sem token, sem espera. */
function cartaoDeFiltro(resultado, { aoLimpar }) {
  return el('aside', { class: 'hb-panel hb-panel--filtro' }, [
    el('header', { class: 'hb-panel__head' }, [
      el('h2', { class: 'hb-panel__name', text: resultado.rotulo }),
      el('button', {
        class: 'btn btn--sm',
        type: 'button',
        text: 'Limpar',
        onClick: aoLimpar,
      }),
    ]),
    el('p', {
      text:
        resultado.total === 0
          ? 'Nenhum projeto atende a isso.'
          : `${resultado.total} projeto(s) em destaque.`,
    }),
    el('p', {
      class: 'field__hint',
      text: 'Filtro resolvido no navegador, sobre o que o painel já sabia. Nenhum modelo foi consultado.',
    }),
  ]);
}

/** Cartão de confirmação de uma ação proposta.
 *
 * A IA escolhe um nome do registro fechado; o servidor valida; **a pessoa
 * confirma**; e a execução vai pela rota que o botão equivalente já usava
 * (defesa D-A3). O mesmo desenho da pergunta rápida, na tela do grafo.
 */
function cartaoDeAcao(proposta, { aoFechar, aoExecutar }) {
  const corpo = el('div', { class: 'hb-panel__bloco' });

  const cartao = el('aside', { class: 'hb-panel hb-panel--acao' }, [
    el('header', { class: 'hb-panel__head' }, [
      el('h2', { class: 'hb-panel__name', text: proposta.label }),
      proposta.project_name
        ? el('span', { class: 'tech-chip', text: proposta.project_name })
        : null,
    ]),
    el('p', { text: proposta.describe }),
    proposta.reason ? el('p', { class: 'field__hint', text: proposta.reason }) : null,
    corpo,
    el('div', { class: 'hb-panel__acoes' }, [
      el('button', {
        class: 'btn btn--sm btn--primary',
        type: 'button',
        text: 'Confirmar',
        onClick: async (evento) => {
          const botao = evento.currentTarget;
          botao.disabled = true;
          try {
            await aoExecutar();
            mount(corpo, el('p', { class: 'field__hint', text: `${proposta.label} — feito.` }));
          } catch (erro) {
            showError(erro);
            mount(corpo, el('p', { class: 'field__hint', text: erro.message }));
          } finally {
            botao.disabled = false;
          }
        },
      }),
      el('button', { class: 'btn btn--sm', type: 'button', text: 'Cancelar', onClick: aoFechar }),
    ]),
  ]);

  return cartao;
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
  const denso = grafo.nos.length > NOS_PARA_MODO_DENSO;
  let movimentoCurto = movimentoReduzido();

  const modo = modoEscolhido();
  // A profundidade precisa existir na simulação, não só na câmera: um grafo
  // resolvido no plano e girado depois continua sendo um desenho plano visto
  // de lado.
  const layout = criarLayout(grafo.nos, grafo.arestas, { dimensoes: modo === '3d' ? 3 : 2 });

  const moldura = el('div', { class: 'hb-stage-wrap', dataset: { modo } });

  //: Os dois desenhos — SVG e WebGL — vivem atrás da mesma interface, e o
  //: resto da tela não sabe qual está montado. É o que permite trocar de modo
  //: sem duplicar a conversa, o filtro, o painel e os atalhos.
  const visual = modo === '3d' ? await montarEmTresDimensoes() : montarEmSvg();

  async function montarEmTresDimensoes() {
    // Importação dinâmica: quem fica no modo 2D não baixa 1,3 MB de three.js.
    const { criarCena3D } = await import('../lib/graph/scene3d.js');

    const cena = criarCena3D({
      container: moldura,
      grafo,
      layout,
      aoSelecionar: (id) => estado.definir({ selecionado: id ?? null }),
    });

    if (movimentoCurto) cena.definirGiro(false);

    return {
      tipo: '3d',
      desenhar: () =>
        // O relógio vem de `performance.now()`, e não de um contador de
        // quadros: a pulsação precisa ter a mesma velocidade numa tela de
        // 60 Hz e numa de 144.
        cena.desenhar({ girarSozinho: !movimentoCurto, tempo: performance.now() }),
      assentar: () => cena.enquadrar(),
      enquadrar: () => cena.enquadrar(),
      ampliar: () => cena.aproximar(1 / 1.2),
      reduzir: () => cena.aproximar(1.2),
      reorganizar: () => {
        for (const no of grafo.nos) if (!no.fixo) layout.soltar(no.id);
        layout.reaquecer(1);
        cena.definirGiro(!movimentoCurto);
      },
      destacar: (situacao) => cena.aplicarDestaque(situacao),
      acender: (projetoId) => cena.acender(projetoId ? `core->p:${projetoId}` : null),
      nucleo: (nome, texto) => cena.definirEstadoNucleo(nome, texto),
      movimento: (reduzido) => cena.definirGiro(!reduzido),
      //: Em WebGL a câmera vive: enquanto ela gira, cada quadro é um desenho
      //: novo, mesmo com o grafo parado.
      continuo: () => !movimentoCurto || !layout.energia,
      reler: () => cena.reler(),
      destruir: () => cena.destruir(),
    };
  }

  function montarEmSvg() {
    const palco = criarPalco();
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

    let ordemDeEntrada = 0;
    for (const no of grafo.nos) {
      if (no.tipo === 'core') continue;
      const elemento = desenharNo(no, ordemDeEntrada++);
      elementosDeNo.set(no.id, elemento);
      palco.nos.append(elemento);
    }

    const alvos = { elementosDeNo, elementosDeAresta, arestas: grafo.arestas };
    palco.svg.dataset.denso = String(denso);
    palco.svg.dataset.movimento = movimentoCurto ? 'reduzido' : 'completo';
    moldura.append(palco.svg);

    const interacao = ligarInteracao(
      { svg: palco.svg, viewport: palco.viewport, layout, palco: palco.svg },
      {
        aoSelecionar: (id) => estado.definir({ selecionado: id ?? null }),
        aoMover: () => acordar(),
        aoReenquadrar: () => interacao.enquadrar(layout.posicoes()),
      }
    );

    return {
      tipo: '2d',
      desenhar: () => aplicarPosicoes(layout.posicoes(), alvos),
      assentar: () => {
        const posicoes = layout.posicoes();
        ajustarRotulos(posicoes, { elementosDeNo, nos: grafo.nos }, posicionarRotulos);
        iluminar(posicoes, { elementosDeNo });
        interacao.enquadrar(posicoes);
      },
      enquadrar: () => interacao.enquadrar(layout.posicoes()),
      ampliar: () => interacao.ampliar(),
      reduzir: () => interacao.reduzir(),
      reorganizar: () => interacao.reorganizar(grafo.nos),
      destacar: (situacao) => aplicarDestaque(alvos, situacao),
      acender: (projetoId) => {
        for (const linha of elementosDeAresta.values()) delete linha.dataset.ativa;
        if (!projetoId) return;
        const linha = elementosDeAresta.get(`core->p:${projetoId}`);
        if (linha) linha.dataset.ativa = 'true';
      },
      nucleo: (nome) => nucleo.definirEstado(nome),
      movimento: (reduzido) => {
        palco.svg.dataset.movimento = reduzido ? 'reduzido' : 'completo';
      },
      continuo: () => false,
      reler: () => {},
      destruir: () => interacao.destruir(),
      //: Só o SVG tem elemento por nó; o estado do projeto é atributo dele.
      atualizarEstado: (projetoId, estadoNovo) => {
        const elemento = elementosDeNo.get(`p:${projetoId}`);
        if (elemento) elemento.dataset.estado = estadoNovo;
      },
    };
  }

  // --- painel lateral -----------------------------------------------------

  const painel = el('div', { class: 'hb-side' });
  const corpo = el('div', { class: 'hb-body', dataset: { painel: 'vazio' } });

  //: Cartão que a conversa produziu — filtro, ação proposta ou resposta. Fica
  //: **acima** do contexto do nó, e não no lugar dele: perguntar sobre um
  //: projeto não deveria apagar da tela o projeto sobre o qual se perguntou.
  let cartao = null;

  function painelDoNo() {
    const id = estado.get('selecionado');

    if (!id) {
      return el('aside', { class: 'hb-panel hb-panel--vazio' }, [
        el('p', { text: 'Selecione um nó para ver o contexto dele.' }),
        el('p', {
          class: 'field__hint',
          text: 'Arraste para organizar, role para aproximar, Esc limpa foco e destaque.',
        }),
      ]);
    }

    if (id === 'core') return painelDoNucleo(statusIa);

    const no = grafo.nos.find((n) => n.id === id);
    if (!no) return null;

    const emFoco = estado.get('foco') === id;
    const alternarFoco = () => estado.definir({ foco: emFoco ? null : id });

    return no.tipo === 'tecnologia'
      ? painelDeTecnologia(no, grafo, { aoFocar: alternarFoco, emFoco })
      : painelDeProjeto(no, grafo, { aoFocar: alternarFoco, emFoco });
  }

  function redesenharPainel() {
    const conteudo = painelDoNo();
    mount(painel, cartao, conteudo);
    // Sem nada selecionado, a coluna encolhe e devolve a largura ao mapa —
    // que é o conteúdo desta tela, não o painel.
    corpo.dataset.painel = cartao || estado.get('selecionado') ? 'cheio' : 'vazio';
  }

  function mostrarCartao(node) {
    cartao = node;
    redesenharPainel();
  }

  function limparCartao() {
    cartao = null;
    redesenharPainel();
  }

  function redesenharDestaque() {
    const foco = estado.get('foco');
    visual.destacar({
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

  // --- a conversa ---------------------------------------------------------

  const iaLigada = Boolean(statusIa?.enabled && statusIa?.configured);

  /** Relê o que o painel mede, sem refazer o layout.
   *
   * Depois de uma ação confirmada, o estado do projeto pode ter mudado. O que
   * **não** muda é a posição dos nós: recalcular o layout aqui faria o mapa
   * inteiro se reorganizar por causa de um botão, e quem apertou o botão perde
   * a referência de onde estava olhando.
   */
  async function recarregarEstados() {
    let novos;
    try {
      novos = (await api.listProjects({ limit: 200 })).items;
    } catch {
      return;
    }

    projetos = novos;
    for (const projeto of novos) {
      const no = grafo.nos.find((n) => n.id === `p:${projeto.id}`);
      if (no) no.projeto = projeto;
      visual.atualizarEstado?.(projeto.id, estadoDoProjeto(projeto));
    }
  }

  /** Acende a aresta do núcleo até um projeto — **só com fato por trás**.
   *
   * Os três fatos que autorizam: a proposta resolveu aquele projeto, o chat
   * montou contexto dele, ou ele é o projeto em foco na pergunta. Acender por
   * qualquer outro motivo seria a tela afirmando uma consulta que não houve.
   */
  function acender(projetoId) {
    visual.acender(projetoId ?? null);
  }

  function apagar() {
    visual.acender(null);
  }

  /** Estado do núcleo.
   *
   * De propósito **fora** do estado observável da tela: o núcleo é um elemento
   * só, e mandar cada mudança dele redesenhar o painel lateral criava uma
   * corrida real — o `blur` do campo de pergunta chegava junto com o clique no
   * cartão, o painel era remontado no meio do gesto, e o clique se perdia. Quem
   * ia confirmar uma ação apertava Cancelar e não acontecia nada.
   */
  //: Estados de fim de curso não são um lugar onde ficar: "feito" pendurado na
  //: tela por meia hora vira enfeite, e depois mentira.
  const PASSAGEIROS = new Set(['success', 'warning', 'error']);
  let voltaAoRepouso = null;

  function cerebro(nome) {
    if (voltaAoRepouso) {
      window.clearTimeout(voltaAoRepouso);
      voltaAoRepouso = null;
    }
    const efetivo = iaLigada || nome === 'desligado' ? nome : 'desligado';
    visual.nucleo(efetivo, ESTADOS[efetivo] ?? '');
    if (PASSAGEIROS.has(nome)) {
      voltaAoRepouso = window.setTimeout(() => cerebro('idle'), 2600);
    }
  }

  /** O projeto sobre o qual se está falando, se houver um. */
  function projetoEmPauta() {
    const id = estado.get('foco') ?? estado.get('selecionado');
    const no = id ? grafo.nos.find((n) => n.id === id) : null;
    return no?.tipo === 'projeto' ? no.projeto : null;
  }

  function cartaoDeResposta(titulo, { projeto, aviso }) {
    const corpo = el('p', { class: 'hb-resposta__texto', text: '' });

    mostrarCartao(
      el('aside', { class: 'hb-panel hb-panel--resposta' }, [
        el('header', { class: 'hb-panel__head' }, [
          el('h2', { class: 'hb-panel__name', text: titulo }),
          el('button', { class: 'btn btn--sm', type: 'button', text: 'Fechar', onClick: limparCartao }),
        ]),
        aviso ? el('p', { class: 'field__hint', text: aviso }) : null,
        corpo,
        el('p', {
          class: 'field__hint',
          text: projeto
            ? `Respondido com o contexto de ${projeto.name}.`
            : 'Pergunta avulsa: nenhum contexto de projeto foi enviado.',
        }),
      ])
    );

    return corpo;
  }

  async function perguntar(texto) {
    const frase = texto.trim();
    if (!frase) return;

    // 1. Filtro de visão. Regra local, sem rede e sem modelo — funciona com o
    //    Cockpit AI desligado, e responde antes de a mão sair do teclado.
    const filtro = interpretar(frase, projetos);
    if (filtro) {
      estado.definir({ destacados: filtro.ids, foco: null });
      apagar();
      mostrarCartao(
        cartaoDeFiltro(filtro, {
          aoLimpar: () => {
            estado.definir({ destacados: null });
            limparCartao();
          },
        })
      );
      cerebro('success');
      return;
    }

    // 2. Ação — só quando a frase soa como ordem. A regra do servidor decide a
    //    maioria em milissegundos, mas quando ela não decide o modelo entra, e
    //    num provedor local isso são 15 a 40 segundos. Fazer toda pergunta
    //    pagar esse pedágio antes de virar pergunta é o que separa uma tela
    //    que se usa de uma que se abandona.
    cerebro('thinking');
    let proposta = null;
    let recado = '';
    if (pareceOrdem(frase)) {
      try {
        const resultado = await api.proposeAction(frase);
        proposta = resultado.proposal;
        recado = resultado.message ?? '';
      } catch (erro) {
        recado = erro.message;
      }
    }

    if (proposta) {
      estado.definir({ destacados: null });
      if (proposta.project_id) {
        acender(proposta.project_id);
        estado.definir({ selecionado: `p:${proposta.project_id}` });
      }
      cerebro('executing');
      mostrarCartao(
        cartaoDeAcao(proposta, {
          aoFechar: () => {
            apagar();
            limparCartao();
            cerebro('idle');
          },
          aoExecutar: async () => {
            await api.runProposal(proposta);
            cerebro('success');
            apagar();
            // `environment.up` responde 202 e segue em job: reler agora pode
            // mostrar o estado de antes, e isso é o certo — a tela diz o que
            // mediu, não o que espera que aconteça.
            await recarregarEstados();
          },
        })
      );
      return;
    }

    // Ordem que o servidor recusou não vira pergunta. "faz o deploy em
    // produção" não existe no registro fechado, e a resposta certa é a recusa
    // — não trinta segundos de modelo explicando o que ele acha que faria.
    if (pareceOrdem(frase) && recado) {
      cerebro('warning');
      mostrarCartao(
        el('aside', { class: 'hb-panel hb-panel--recusa' }, [
          el('header', { class: 'hb-panel__head' }, [
            el('h2', { class: 'hb-panel__name', text: 'Sem ação para isso' }),
            el('button', { class: 'btn btn--sm', type: 'button', text: 'Fechar', onClick: limparCartao }),
          ]),
          el('p', { text: recado }),
          el('p', {
            class: 'field__hint',
            text: 'O painel só propõe o que ele já faz por botão. Reformule como pergunta se quiser conversar sobre isso.',
          }),
        ])
      );
      return;
    }

    // 3. Pergunta. Daqui para baixo é IA de verdade — e sem ela, para aqui.
    if (!iaLigada) {
      cerebro('desligado');
      mostrarCartao(
        el('aside', { class: 'hb-panel hb-panel--resposta' }, [
          el('header', { class: 'hb-panel__head' }, [
            el('h2', { class: 'hb-panel__name', text: 'Cockpit AI desligado' }),
            el('button', { class: 'btn btn--sm', type: 'button', text: 'Fechar', onClick: limparCartao }),
          ]),
          el('p', { text: recado || statusIa?.reason || 'Ligue o Cockpit AI para perguntar.' }),
          el('p', {
            class: 'field__hint',
            text: 'Destacar, focar e navegar continuam funcionando sem IA nenhuma.',
          }),
        ])
      );
      return;
    }

    const projeto = projetoEmPauta();
    // Projeto fora do Cockpit AI não vira contexto — nem por engano, nem por
    // conveniência (defesa D-A1). A pergunta segue sem ele, e a tela diz isso.
    const usaContexto = Boolean(projeto && projeto.ai_enabled !== false);

    const corpo = cartaoDeResposta(usaContexto ? projeto.name : 'Pergunta', {
      projeto: usaContexto ? projeto : null,
      aviso:
        projeto && !usaContexto
          ? `${projeto.name} está fora do Cockpit AI: perguntei sem o contexto dele.`
          : null,
    });

    cerebro(usaContexto ? 'accessing' : 'thinking');
    if (usaContexto) acender(projeto.id);

    const escrever = (pedaco) => {
      corpo.textContent += pedaco;
    };

    try {
      if (usaContexto) await api.chatStream(projeto.id, frase, { onChunk: escrever });
      else await api.askQuick(frase, { onChunk: escrever });
      cerebro('success');
    } catch (erro) {
      showError(erro);
      corpo.textContent = erro.message;
      cerebro('error');
    } finally {
      apagar();
    }
  }

  const campo = el('input', {
    class: 'hb-ask__campo',
    type: 'text',
    placeholder: 'Ask HyperBrain…',
    'aria-label': 'Perguntar ao HyperBrain',
    onFocus: () => cerebro('listening'),
    onBlur: () => cerebro('idle'),
  });

  const formulario = el(
    'form',
    {
      class: 'hb-ask',
      onSubmit: async (evento) => {
        evento.preventDefault();
        const texto = campo.value;
        campo.value = '';
        await perguntar(texto);
      },
    },
    [campo, el('button', { class: 'btn btn--sm btn--primary', type: 'submit', text: 'Perguntar' })]
  );

  // --- laço de desenho ----------------------------------------------------

  let quadro = null;
  let vivo = true;
  //: Enquadrar no meio do movimento faria a câmera perseguir nós que ainda
  //: estão se acomodando. Espera-se a simulação parar, e aí se enquadra uma vez.
  let enquadrarAoParar = true;

  function desenharUmaVez() {
    visual.desenhar();
  }

  /** O que só vale a pena fazer com o grafo parado: acomodar rótulo (que
   *  custa medir texto) e enquadrar a câmera. */
  function acomodarRotulos() {
    visual.assentar();
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
      acomodarRotulos();
    }

    // Em WebGL a câmera continua viva depois de o grafo parar: enquanto ela
    // gira, cada quadro é um desenho novo. No SVG o laço encerra aqui, e a
    // tela deixa de custar quadro nenhum.
    if (visual.continuo()) quadro = window.requestAnimationFrame(laco);
  }

  function acordar() {
    if (!vivo || movimentoCurto) return;
    if (quadro === null) quadro = window.requestAnimationFrame(laco);
  }

  function aoTrocarVisibilidade() {
    if (document.visibilityState === 'visible') acordar();
  }

  document.addEventListener('visibilitychange', aoTrocarVisibilidade);

  // O tema é trocado fora desta tela, e em WebGL a cor não vem do CSS: sem
  // ouvir a troca, o mapa ficaria com a paleta do tema anterior até recarregar.
  const observadorDeTema = new MutationObserver(() => {
    visual.reler();
    if (!visual.continuo()) desenharUmaVez();
  });
  observadorDeTema.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });

  // Esc vive no documento, e não no palco: sair do foco costuma ser pedido
  // logo depois de clicar no botão do painel lateral — e aí o foco do teclado
  // está no botão, longe do SVG. Preso ao palco, o atalho só funcionava se a
  // pessoa tivesse clicado num nó antes, que é justamente quando ela não
  // precisa dele.
  function aoTeclarNoDocumento(evento) {
    if (evento.key !== 'Escape') return;
    const temAlgo =
      estado.get('foco') || estado.get('selecionado') || estado.get('destacados') || cartao;
    if (!temAlgo) return;
    cartao = null;
    apagar();
    estado.definir({ foco: null, selecionado: null, destacados: null });
    redesenharPainel();
  }

  document.addEventListener('keydown', aoTeclarNoDocumento);

  // --- montagem -----------------------------------------------------------

  function alternarMovimento() {
    movimentoCurto = !movimentoCurto;
    definirMovimento(movimentoCurto);
    visual.movimento(movimentoCurto);
    if (movimentoCurto) {
      if (quadro !== null) window.cancelAnimationFrame(quadro);
      quadro = null;
      layout.estabilizar();
      desenharUmaVez();
      acomodarRotulos();
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
          class: 'hb-bar__meta',
          text: `${projetos.length} projetos · ${grafo.nos.length} nós · ${grafo.arestas.length} conexões`,
        }),
      ]),
      el('div', { class: 'hb-bar__acoes', role: 'group', 'aria-label': 'Controles do mapa' }, [
        controle('Aproximar', 'plus', () => visual.ampliar()),
        controle('Afastar', 'minus', () => visual.reduzir()),
        controle('Enquadrar o grafo inteiro na tela', 'grid', () => visual.enquadrar()),
        controle('Reorganizar: solta os nós presos e refaz o arranjo', 'refresh', () => {
          visual.reorganizar();
          enquadrarAoParar = true;
          acordar();
        }),
        controle(
          modo === '3d' ? 'Ver o mapa em duas dimensões' : 'Ver o mapa em três dimensões',
          'graph',
          () => {
            guardarModo(modo === '3d' ? '2d' : '3d');
            // Recarregar a rota é o caminho honesto: trocar de motor de desenho
            // no meio da vida da tela deixaria metade do estado no anterior.
            window.location.reload();
          },
          { pressionado: modo === '3d' }
        ),
        controle(
          movimentoCurto ? 'Movimento reduzido — ligar animação' : 'Reduzir o movimento do mapa',
          'pulse',
          alternarMovimento,
          { pressionado: movimentoCurto }
        ),
      ])
    );
  }

  montarBarra();

  moldura.append(
    formulario,
    el(
      'ul',
      { class: 'hb-legend', 'aria-label': 'Tipos de nó' },
      LEGENDA.map(([tipo, rotulo]) =>
        el('li', { class: 'hb-legend__item', dataset: { tipo } }, [
          el('span', { class: 'hb-legend__mark', 'aria-hidden': 'true' }),
          rotulo,
        ])
      )
    )
  );

  mount(corpo, moldura, painel);

  mount(
    container,
    el('div', { class: 'hb', dataset: { movimento: movimentoCurto ? 'reduzido' : 'completo' } }, [
      barra,
      corpo,
    ])
  );

  redesenharPainel();
  redesenharDestaque();

  // O enquadramento só é possível depois da montagem: antes disso a moldura
  // não tem tamanho, e dividir por zero deixaria tudo no canto.
  cerebro(iaLigada ? 'idle' : 'desligado');

  if (movimentoCurto) {
    // Sem animação: estabiliza de uma vez e desenha o resultado. A tela
    // continua inteira — o que se perde é só o caminho até ela.
    layout.estabilizar();
    desenharUmaVez();
    acomodarRotulos();
    enquadrarAoParar = false;
  } else {
    acordar();
  }

  aoSairDaRota(() => {
    vivo = false;
    if (quadro !== null) window.cancelAnimationFrame(quadro);
    quadro = null;
    if (voltaAoRepouso) window.clearTimeout(voltaAoRepouso);
    document.removeEventListener('visibilitychange', aoTrocarVisibilidade);
    document.removeEventListener('keydown', aoTeclarNoDocumento);
    observadorDeTema.disconnect();
    visual.destruir();
  });
}
