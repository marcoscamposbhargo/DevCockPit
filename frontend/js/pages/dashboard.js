// Dashboard agregado (US-080). Consome GET /api/dashboard, servido de cache.

//: O painel da máquina tem relógio próprio. Guardar o último permite pará-lo
//: quando a tela é redesenhada — senão cada visita empilha mais um relógio
//: desenhando dentro de um container que já saiu do DOM.
let maquinaAtual = null;

import { analyticsPanel } from '../lib/analytics-panel.js';
import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { machinePanel } from '../lib/machine-panel.js';
import { powerToggle } from '../lib/power.js';
import { emptyState, loading, pageHeader, showError, statCard, statusBadge } from '../lib/ui.js';

function freshness(data, onReload) {
  return el('div', { class: 'freshness' }, [
    el('span', {
      class: 'field__hint',
      // Nunca apresentar cache como tempo real (decisão D-18).
      text: `atualizado ${relativeTime(data.generated_at)}${data.from_cache ? ' · de cache' : ''}`,
    }),
    el(
      'button',
      { class: 'btn btn--sm', type: 'button', onClick: onReload },
      [icon('refresh', { size: 13 }), 'Recarregar']
    ),
  ]);
}

/**
 * Painel nomeado.
 *
 * A contagem vai no cabeçalho porque é a informação que decide se vale a pena
 * ler o corpo — e porque um painel vazio precisa dizer isso antes de ocupar
 * meia tela sem conteúdo.
 */
function panel({ title, count = null, action = null, body }) {
  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: title }),
      count !== null ? el('span', { class: 'panel__count', text: String(count) }) : null,
      action,
    ]),
    el('div', { class: 'panel__body' }, [body]),
  ]);
}

function panelEmpty(text) {
  return el('p', { class: 'panel__empty', text });
}

function portConflicts(conflitos) {
  if (!conflitos.length) return null;

  return el('div', { class: 'alert', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          conflitos.length === 1 ? 'Conflito de porta' : `${conflitos.length} conflitos de porta`,
      }),
      ...conflitos.map((item) =>
        el('div', { class: 'field__hint' }, [
          el('span', { class: 'mono', text: String(item.port) }),
          ` usada por ${item.projects.join(', ')}`,
        ])
      ),
      // Avisar sem oferecer o conserto obrigava a caçar o projeto na lista e
      // achar a aba certa. O conserto fica a um clique do aviso.
      el('div', { style: 'margin-top:var(--sp-2)' }, [
        el('a', { href: '#/ports', text: 'Resolver em Ports →' }),
      ]),
    ]),
  ]);
}

function pendingChanges(itens) {
  if (!itens.length) {
    return panelEmpty('Nenhuma alteração pendente conhecida.');
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        itens.map((item) =>
          el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(item.project_id)}?tab=git`,
                text: item.name,
              }),
            ]),
            el('td', { class: 'mono', text: item.branch ?? '—' }),
            el('td', { class: 'table__num', text: `${item.dirty_count} arquivo(s)` }),
          ])
        )
      ),
    ]),
  ]);
}

function activeServices(itens) {
  if (!itens.length) {
    return panelEmpty(
      'Nenhum serviço online. O verificador roda em background para projetos fixados e recentes.'
    );
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        itens.map((item) =>
          el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(item.project_id)}`,
                text: item.project_name,
              }),
            ]),
            el('td', { text: item.label }),
            el('td', {}, [
              item.url
                ? el('a', {
                    class: 'mono',
                    href: item.url,
                    target: '_blank',
                    rel: 'noreferrer',
                    text: item.url.replace(/^https?:\/\//, ''),
                  })
                : el('span', { class: 'mono', text: `:${item.port ?? '—'}` }),
            ]),
            el('td', { class: 'table__end' }, [
              // Duas afirmações diferentes, e a tela não pode dar a mesma cara
              // às duas: "no ar" é o painel dizendo que este serviço é deste
              // projeto; "ocupada" é o painel dizendo apenas que alguém
              // atende ali. Um projeto parado cuja porta padrão está tomada
              // por outro aparecia como rodando.
              item.proven === false
                ? el('span', { class: 'signal', dataset: { kind: 'partial' }, title: item.owner_hint ?? '' }, [
                    el('span', { class: 'signal__dot' }),
                    'porta ocupada',
                  ])
                : statusBadge('RUNNING'),
            ]),
          ])
        )
      ),
    ]),
  ]);
}

//: Quantas linhas de porta cabem no dashboard sem ele virar uma listagem.
//: Vinte e nove portas declaradas empurravam o resto da tela para baixo e
//: transformavam o painel de operação num relatório — a tela de Ports existe
//: justamente para a lista inteira.
const PORTAS_NO_DASHBOARD = 7;

/** As portas que merecem o espaço escasso do dashboard.
 *
 * Ordem: conflito primeiro (é o que exige decisão), depois o que está de fato
 * atendendo (é o que responde "o que está no ar agora"), e por último o
 * declarado e silencioso — que é informação de cadastro, não de operação.
 */
export function portasRelevantes(portas, noAr) {
  const peso = (item) => {
    if (item.conflict) return 0;
    if (noAr.get(item.port)?.forte) return 1;
    if (noAr.has(item.port)) return 2;
    return 3;
  };

  return [...portas]
    .sort((a, b) => peso(a) - peso(b) || a.port - b.port)
    .slice(0, PORTAS_NO_DASHBOARD);
}

/** Mapa de portas — o que a tela não mostrava e é a pergunta de todo dia:
 *  "quem está ocupando a 8000?". Conflito aparece marcado na própria linha. */
function portMap(portas, noAr) {
  if (!portas.length) {
    return panelEmpty('Nenhuma porta declarada pelos projetos cadastrados.');
  }

  const mostradas = portasRelevantes(portas, noAr);
  const ocultas = portas.length - mostradas.length;

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        mostradas.map((item) =>
          el('tr', { dataset: { conflict: String(item.conflict) } }, [
            el('td', { class: 'mono', text: String(item.port) }),
            el('td', { text: item.projects.join(', ') }),
            el('td', { class: 'table__end' }, [
              item.conflict
                ? el('span', { class: 'signal', dataset: { kind: 'dirty' } }, [
                    el('span', { class: 'signal__dot' }),
                    'conflito',
                  ])
                : // "Declarada" e "atendendo" são coisas diferentes, e o painel
                  // listava as duas do mesmo jeito: uma coluna de números onde
                  // metade é intenção e metade é fato. O visitante tinha que ir
                  // à tela de Ports para saber qual era qual.
                  noAr.get(item.port)?.forte
                  ? el('span', { class: 'signal', dataset: { kind: 'on' }, title: noAr.get(item.port).texto }, [
                      el('span', { class: 'signal__dot' }),
                      'no ar',
                    ])
                  : noAr.has(item.port)
                    ? el('span', { class: 'signal', dataset: { kind: 'partial' }, title: noAr.get(item.port).texto }, [
                        el('span', { class: 'signal__dot' }),
                        'ocupada',
                      ])
                    : null,
            ]),
          ])
        )
      ),
    ]),
    // O que não coube não pode sumir em silêncio: sem esta linha, sete de
    // vinte e nove pareceriam o total, e a tela mentiria por omissão.
    ocultas > 0
      ? el('div', { class: 'field__hint', style: 'margin-top:var(--sp-2)' }, [
          `mais ${ocultas} porta(s) declarada(s) · `,
          el('a', { href: '#/ports', text: 'ver todas em Ports →' }),
        ])
      : null,
  ]);
}

/** Retomar o trabalho: fixados e recentes, com o botão de ligar na frente.
 *
 * O dashboard era só leitura. O gesto da manhã — "ligar o que vou usar hoje" —
 * obrigava a sair daqui, ir a Projects e procurar o projeto na grade. Um painel
 * de operação sem operação é um relatório.
 *
 * Só entram os que **não estão no ar**: quem já está rodando aparece em
 * "Serviços ativos" logo acima, e repetir os dois lugares faria a tela dizer a
 * mesma coisa duas vezes.
 */
function retomar(projetos, ativos, aoMudar) {
  const noAr = new Set(ativos.map((s) => s.project_id));
  const candidatos = projetos
    .filter((p) => !noAr.has(p.id) && p.can_start && p.status !== 'MISSING')
    .slice(0, 6);

  if (!candidatos.length) {
    return panelEmpty(
      noAr.size
        ? 'Tudo o que dá para ligar já está no ar.'
        : 'Nenhum projeto com comando de subida conhecido.'
    );
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table' }, [
      el(
        'tbody',
        {},
        candidatos.map((project) =>
          el('tr', {}, [
            el('td', {}, [
              el('a', {
                href: `#/projects/${encodeURIComponent(project.id)}`,
                text: project.name,
              }),
            ]),
            el('td', { class: 'field__hint', text: relativeTime(project.last_accessed_at) }),
            el('td', { class: 'table__end' }, [
              powerToggle(project, { on: false, onChanged: aoMudar }),
            ]),
          ])
        )
      ),
    ]),
  ]);
}

function recent(itens) {
  if (!itens.length) return panelEmpty('Nenhum projeto acessado ainda.');

  return el(
    'ul',
    { class: 'recent-list' },
    itens.map((item) =>
      el('li', {}, [
        el('a', {
          class: 'recent-list__name',
          href: `#/projects/${encodeURIComponent(item.id)}`,
          text: item.name,
        }),
        el('span', { class: 'field__hint', text: relativeTime(item.last_accessed_at) }),
      ])
    )
  );
}

export async function renderDashboard(container) {
  mount(container, loading());

  // O mapa de portas é opcional: ele enriquece a tela, mas uma falha nele não
  // pode derrubar o dashboard inteiro.
  const [resultado, portas, lista] = await Promise.allSettled([
    api.dashboard(),
    api.ports(),
    // A lista alimenta o bloco de retomar trabalho. Opcional como o mapa de
    // portas: uma falha nela não pode derrubar o dashboard inteiro.
    api.listProjects({ limit: 200 }),
  ]);

  if (resultado.status === 'rejected') {
    showError(resultado.reason);
    mount(container, el('p', { class: 'loading', text: resultado.reason.message }));
    return;
  }

  const data = resultado.value;

  // O painel anterior continuaria com o relógio de pé, desenhando dentro de um
  // container já descartado — cada visita ao dashboard empilharia mais um.
  maquinaAtual?.parar();
  const maquina = machinePanel();
  maquinaAtual = maquina;
  const mapaDePortas = portas.status === 'fulfilled' ? portas.value.items : [];
  const projetos = lista.status === 'fulfilled' ? lista.value.items : [];

  // Quais dessas portas estão de fato atendendo agora. Vem da mesma resposta,
  // do lado observado — nenhuma chamada a mais.
  // Mesma distinção da tela de Ports: "no ar" exige prova de que o processo é
  // deste projeto; sem prova, a marca diz só que a porta está ocupada.
  const portasNoAr = new Map(
    (portas.status === 'fulfilled' ? (portas.value.observed ?? []) : []).map((porta) => [
      porta.port,
      {
        forte: Boolean(porta.strong_evidence),
        texto: porta.strong_evidence
          ? `${porta.process_name ?? 'processo'} de ${porta.project_name}`
          : `Ocupada por ${porta.process_name ?? 'processo desconhecido'} — ` +
            'o painel não consegue provar que é deste projeto.',
      },
    ])
  );

  if (data.totals.projects === 0) {
    mount(
      container,
      pageHeader({ title: 'Ambiente de desenvolvimento' }),
      emptyState({
        title: 'Ambiente vazio',
        text: 'Aponte uma pasta raiz e deixe o DevCockpit encontrar seus projetos.',
        actions: [
          el('a', { class: 'btn btn--primary', href: '#/discovery', text: 'Varrer diretório' }),
        ],
      })
    );
    return;
  }

  mount(
    container,
    pageHeader({ title: 'Ambiente de desenvolvimento' }),
    freshness(data, () => renderDashboard(container)),
    portConflicts(data.port_conflicts),
    // Os números levam à lista já filtrada. Antes respondiam "quantos" e não
    // "quais", e a resposta existia em Projects atrás de um filtro que era
    // preciso reencontrar na mão.
    el('div', { class: 'grid-stats' }, [
      statCard(data.totals.projects, 'Projetos', { href: '#/projects' }),
      statCard(data.totals.running, 'Rodando', {
        tone: 'running',
        href: '#/projects?filter=online',
      }),
      statCard(data.totals.stopped, 'Parados', { href: '#/projects' }),
      statCard(data.totals.with_docker, 'Com Docker', { href: '#/projects?filter=docker' }),
      statCard(data.totals.missing, 'Sem diretório', { href: '#/projects?filter=missing' }),
    ]),
    // Duas colunas, duas linhas. Antes era uma linha só, com a coluna da
    // esquerda quase sempre vazia e meia tela sobrando embaixo.
    el('div', { class: 'panel-grid' }, [
      panel({
        title: 'Serviços ativos',
        // A contagem do cabeçalho é a dos provados, a mesma do card "Rodando".
        // Duas contagens diferentes na mesma tela para a mesma pergunta é como
        // se perde a confiança no painel inteiro.
        count: data.active_services.filter((s) => s.proven !== false).length,
        body: activeServices(data.active_services),
      }),
      panel({
        title: 'Portas em uso',
        count: mapaDePortas.length,
        body: portMap(mapaDePortas, portasNoAr),
      }),
      // Só ocupa um quadrante quando tem o que dizer. O cache de Git é
      // preenchido pelas consultas que já foram feitas, então numa sessão em
      // que ninguém abriu a aba Git este painel fica permanentemente vazio —
      // um quarto da tela dizendo "não sei", todo dia.
      data.pending_changes.length
        ? panel({
            title: 'Alterações pendentes',
            count: data.pending_changes.length,
            body: pendingChanges(data.pending_changes),
          })
        : null,
      panel({
        title: 'Retomar trabalho',
        action: el('a', { class: 'panel__action', href: '#/projects', text: 'Ver todos' }),
        body: retomar(projetos, data.active_services, () =>
          // Ligar muda o estado de tudo o que esta tela mostra; a espera curta
          // deixa o verificador alcançar antes de redesenhar.
          window.setTimeout(() => renderDashboard(container), 2000)
        ),
      }),
    ]),

    // A máquina vem por último: é contexto, não o assunto. Quem abre o painel
    // quer saber dos projetos primeiro, e do processador só quando algo está
    // lento.
    panel({
      title: 'Máquina',
      body: maquina.element,
    }),

    // A análise fecha a tela porque muda de tempo verbal: tudo acima é agora,
    // daqui para baixo é histórico. Ela carrega por conta própria, depois do
    // resto — o dashboard não espera por ela.
    analyticsPanel().element
  );
}
