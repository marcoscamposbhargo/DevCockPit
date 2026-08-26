// Activity: o que o painel fez, e o que deu errado.
//
// Era um muro. Cento e quarenta e cinco linhas em ordem cronológica, sem filtro
// nenhum, com `system.browser` e `project.detect` repetindo dezenas de vezes e
// as falhas perdidas no meio. A informação estava toda lá e nenhuma pergunta
// tinha resposta: "o que quebrou hoje?", "o que aconteceu com este projeto?".
//
// A API já aceitava `project_id`, `action` e `status` — a tela é que não
// perguntava. Três mudanças:
//
// 1. **filtros** para as perguntas que se faz de verdade, com "só problemas"
//    em primeiro lugar: é o motivo número um de abrir esta tela;
// 2. **agrupamento por dia**, porque "há 7 horas" repetido quarenta vezes não
//    situa ninguém no tempo;
// 3. **falha em destaque**, porque uma linha vermelha entre cem verdes ainda
//    é uma linha entre cem.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { duration, relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { emptyState, loading, pageHeader, showError } from '../lib/ui.js';

const PAGINA = 60;

const PROBLEMAS = new Set(['FAILED', 'TIMEOUT', 'DENIED']);

//: Famílias de ação, agrupadas pelo que a pessoa quer procurar. O filtro por
//: ação da API é exato, então cada família vira um pedido separado — mas quem
//: usa a tela pensa em "docker", não em "docker.up" e "docker.down".
const FAMILIAS = [
  { key: '', label: 'Tudo' },
  { key: 'server', label: 'Servidor', prefixo: 'server.' },
  { key: 'docker', label: 'Docker', prefixo: 'docker.' },
  { key: 'environment', label: 'Ambiente', prefixo: 'environment.' },
  { key: 'project', label: 'Projeto', prefixo: 'project.' },
  { key: 'system', label: 'Abrir', prefixo: 'system.' },
];

const ROTULO_ACAO = {
  'server.start': 'subiu o servidor',
  'server.stop': 'parou o servidor',
  'environment.up': 'subiu o ambiente',
  'docker.up': 'subiu os containers',
  'docker.down': 'derrubou os containers',
  'docker.stop': 'parou os containers',
  'docker.restart': 'reiniciou os containers',
  'project.create': 'cadastrou',
  'project.delete': 'removeu',
  'project.update': 'editou',
  'project.detect': 'detectou a stack',
  'system.vscode': 'abriu no VS Code',
  'system.folder': 'abriu a pasta',
  'system.terminal': 'abriu o terminal',
  'system.browser': 'abriu no navegador',
  'manifest.import': 'importou o manifesto',
  'manifest.export': 'exportou o manifesto',
  'discovery.scan': 'varreu o diretório',
};

function diaDe(iso) {
  const data = new Date(iso);
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);

  const mesmoDia = (a, b) => a.toDateString() === b.toDateString();
  if (mesmoDia(data, hoje)) return 'Hoje';
  if (mesmoDia(data, ontem)) return 'Ontem';
  return data.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
}

function linha(entry) {
  const problema = PROBLEMAS.has(entry.status);

  return el('tr', { dataset: { problema: String(problema) } }, [
    el('td', {
      class: 'activity__quando',
      text: relativeTime(entry.created_at),
      title: new Date(entry.created_at).toLocaleString('pt-BR'),
    }),
    el('td', {}, [
      // O nome técnico continua no tooltip: quem depura precisa dele, quem só
      // quer saber o que houve não deveria decorar `system.vscode`.
      el('span', { title: entry.action, text: ROTULO_ACAO[entry.action] ?? entry.action }),
      // Autoria só aparece quando não é a pessoa: marcar toda linha com "você"
      // seria ruído em 99% delas, e o que interessa é justamente a exceção.
      entry.actor === 'ai'
        ? el('span', {
            class: 'signal',
            dataset: { kind: 'ia' },
            title: entry.reason ?? 'Proposta pela IA, confirmada por você.',
          }, [icon('graph', { size: 11 }), 'IA'])
        : null,
    ]),
    el('td', {}, [
      entry.project_id
        ? el('a', {
            href: `#/projects/${encodeURIComponent(entry.project_id)}`,
            text: entry.project_id,
          })
        : el('span', { class: 'field__hint', text: '—' }),
    ]),
    el('td', {}, [
      problema
        ? el('span', { class: 'signal', dataset: { kind: 'dirty' } }, [
            icon('alert', { size: 11 }),
            entry.status.toLowerCase(),
          ])
        : el('span', { class: 'field__hint', text: 'ok' }),
    ]),
    // Duração só aparece quando existe: a coluna era quase toda "—", ocupando
    // largura sem informar nada.
    el('td', { class: 'field__hint', text: entry.duration_ms ? duration(entry.duration_ms) : '' }),
    el('td', { class: 'activity__mensagem', text: entry.message ?? '', title: entry.message ?? '' }),
  ]);
}

function tabela(itens) {
  const corpo = [];
  let diaAtual = null;

  for (const entry of itens) {
    const dia = diaDe(entry.created_at);
    if (dia !== diaAtual) {
      diaAtual = dia;
      corpo.push(
        el('tr', { class: 'activity__dia' }, [
          el('td', { colspan: '6', text: dia }),
        ])
      );
    }
    corpo.push(linha(entry));
  }

  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'table table--activity' }, [
      el('thead', {}, [
        el('tr', {}, [
          el('th', { text: 'Quando' }),
          el('th', { text: 'O que' }),
          el('th', { text: 'Projeto' }),
          el('th', { text: 'Resultado' }),
          el('th', { text: 'Duração' }),
          el('th', { text: 'Detalhe' }),
        ]),
      ]),
      el('tbody', {}, corpo),
    ]),
  ]);
}

export async function renderActivity(container) {
  mount(container, loading());

  const estado = { familia: '', projeto: '', soProblemas: false, soIa: false, mostrando: PAGINA };
  let projetos = [];

  try {
    projetos = (await api.listProjects({ limit: 200 })).items;
  } catch {
    /* sem a lista, o filtro por projeto some e o resto da tela funciona. */
  }

  const buscar = async () => {
    // O filtro por ação da API é exato e a tela pensa em famílias, então a
    // filtragem por prefixo acontece aqui. O de projeto e o de status vão para
    // o servidor, que é onde eles cortam o volume.
    const dados = await api.listActivity({
      limit: 200,
      project_id: estado.projeto || undefined,
      // O filtro por autor vai para o servidor: "o que o agente fez ontem?" é a
      // pergunta que a Fase 3.6 existe para responder, e ela não deveria
      // depender de a resposta caber nas 200 linhas trazidas.
      actor: estado.soIa ? 'ai' : undefined,
    });

    const familia = FAMILIAS.find((f) => f.key === estado.familia);
    return dados.items.filter((entry) => {
      if (estado.soProblemas && !PROBLEMAS.has(entry.status)) return false;
      if (familia?.prefixo && !entry.action.startsWith(familia.prefixo)) return false;
      return true;
    });
  };

  const desenhar = (itens) => {
    const visiveis = itens.slice(0, estado.mostrando);

    const chip = (rotulo, ligado, aoClicar, extra = {}) =>
      el('button', {
        class: `filter-chip${ligado ? ' filter-chip--on' : ''}`,
        type: 'button',
        'aria-pressed': ligado ? 'true' : 'false',
        onClick: aoClicar,
        ...extra,
      }, [rotulo]);

    const barra = el('div', { class: 'filter-bar' }, [
      // "Só problemas" vem primeiro e separado: é o motivo número um de abrir
      // esta tela, e enterrá-lo entre as famílias faria procurar por ele.
      chip(
        el('span', {}, [icon('alert', { size: 12 }), ' Só problemas']),
        estado.soProblemas,
        () => {
          estado.soProblemas = !estado.soProblemas;
          estado.mostrando = PAGINA;
          recarregar();
        },
        { title: 'Falhas, tempos esgotados e ações recusadas.' }
      ),
      chip(
        el('span', {}, [icon('graph', { size: 12 }), ' Feito pela IA']),
        estado.soIa,
        () => {
          estado.soIa = !estado.soIa;
          estado.mostrando = PAGINA;
          recarregar();
        },
        { title: 'Ações que o agente propôs e você confirmou.' }
      ),
      el('span', { class: 'filter-bar__sep', 'aria-hidden': 'true' }),
      ...FAMILIAS.map((f) =>
        chip(f.label, estado.familia === f.key, () => {
          estado.familia = f.key;
          estado.mostrando = PAGINA;
          recarregar();
        })
      ),
      el(
        'select',
        {
          class: 'input filter-bar__stack',
          'aria-label': 'Filtrar por projeto',
          onChange: (evento) => {
            estado.projeto = evento.target.value;
            estado.mostrando = PAGINA;
            recarregar();
          },
        },
        [
          el('option', { value: '', text: 'Qualquer projeto' }),
          ...projetos.map((p) =>
            el('option', {
              value: p.id,
              text: p.name,
              selected: p.id === estado.projeto ? 'selected' : null,
            })
          ),
        ]
      ),
    ]);

    const corpo = visiveis.length
      ? tabela(visiveis)
      : emptyState({
          iconName: estado.soProblemas ? 'check' : 'search',
          title: estado.soProblemas
            ? 'Nenhum problema registrado'
            : 'Nada com esse filtro',
          text: estado.soProblemas
            ? 'Nenhuma ação falhou, estourou o tempo ou foi recusada no período guardado.'
            : 'Ajuste os filtros acima para ver mais.',
        });

    const maisVezes = itens.length > estado.mostrando;

    mount(
      container,
      pageHeader({
        title: 'Activity',
        subtitle:
          `${itens.length} registro(s)` +
          (visiveis.length < itens.length ? ` · mostrando ${visiveis.length}` : ''),
        actions: [
          el('button', {
            class: 'btn',
            type: 'button',
            onClick: () => recarregar(),
          }, [icon('refresh', { size: 15 }), 'Recarregar']),
        ],
      }),
      barra,
      corpo,
      maisVezes
        ? el('div', { class: 'activity__mais' }, [
            el('button', {
              class: 'btn',
              type: 'button',
              text: `Mostrar mais ${Math.min(PAGINA, itens.length - estado.mostrando)}`,
              onClick: () => {
                estado.mostrando += PAGINA;
                desenhar(itens);
              },
            }),
          ])
        : null
    );
  };

  const recarregar = async () => {
    try {
      desenhar(await buscar());
    } catch (error) {
      showError(error);
      mount(container, el('p', { class: 'loading', text: error.message }));
    }
  };

  await recarregar();
}
