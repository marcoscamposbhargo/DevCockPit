// Aba Sessão: onde o trabalho de um dia fica registrado.
//
// A tela tem uma regra: **o resumo é montado dos fatos**, e os fatos aparecem
// ao lado dele. Quem encerra vê commits, ações e quedas que o painel observou —
// e pode reescrever o texto, porque quem viveu a sessão sabe coisas que log
// nenhum registra. O que não pode é o painel inventar.
//
// Sem IA. Toda esta tela funciona com provedor nenhum configurado, e é esse o
// argumento da Fase 1: memória e sessão valem por si; a IA só as torna mais
// rápidas de escrever e de consultar.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { showError, toast } from '../lib/ui.js';

const TIPOS_DE_MEMORIA = [
  { value: 'context', label: 'Contexto' },
  { value: 'architecture', label: 'Arquitetura' },
  { value: 'decision', label: 'Decisão' },
  { value: 'bug', label: 'Bug conhecido' },
  { value: 'debt', label: 'Dívida técnica' },
  { value: 'discovery', label: 'Descoberta' },
  { value: 'next_step', label: 'Próximo passo' },
];

const ROTULO_DE_TIPO = Object.fromEntries(TIPOS_DE_MEMORIA.map((t) => [t.value, t.label]));

// Mesmo idioma de formulário do resto do painel (`discovery.js`): `div.field`
// com rótulo, controle e dica.
function campo(rotulo, controle, dica = null) {
  return el('div', { class: 'field' }, [
    el('label', { class: 'field__label', text: rotulo }),
    controle,
    dica ? el('span', { class: 'field__hint', text: dica }) : null,
  ]);
}

/** Os fatos observados, em lista curta. É o que sustenta o resumo. */
function fatos(dados) {
  if (!dados) return null;

  const linhas = [];
  const inicio = dados.git_start ?? {};
  const fim = dados.git_end ?? {};

  if (dados.duration_minutes !== null && dados.duration_minutes !== undefined) {
    const horas = Math.floor(dados.duration_minutes / 60);
    const minutos = dados.duration_minutes % 60;
    linhas.push(['duração', horas ? `${horas}h${String(minutos).padStart(2, '0')}` : `${minutos} min`]);
  }
  if (inicio.is_repo) {
    linhas.push(['branch', fim.branch ?? inicio.branch ?? '—']);
    linhas.push(['commits no período', String(dados.commits?.length ?? 0)]);
    if (fim.dirty_count !== null && fim.dirty_count !== undefined) {
      linhas.push(['sem commit ao encerrar', `${fim.dirty_count} arquivo(s)`]);
    }
  }
  if (dados.actions?.length) linhas.push(['ações pelo painel', String(dados.actions.length)]);
  if (dados.services_down?.length) {
    const servicos = [...new Set(dados.services_down.map((q) => q.service))];
    linhas.push(['saiu do ar', servicos.join(', ')]);
  }

  if (!linhas.length) return null;

  return el('div', { class: 'session-facts' }, [
    el('span', { class: 'field__label', text: 'Observado pelo painel' }),
    el(
      'dl',
      { class: 'definition-list definition-list--compact' },
      linhas.flatMap(([rotulo, valor]) => [
        el('dt', { text: rotulo }),
        el('dd', { class: 'mono', text: valor }),
      ])
    ),
    dados.commits?.length
      ? el(
          'ul',
          { class: 'session-commits' },
          dados.commits.slice(0, 5).map((commit) =>
            el('li', {}, [
              el('span', { class: 'mono', text: (commit.sha ?? '').slice(0, 7) }),
              ` ${commit.subject ?? ''}`,
            ])
          )
        )
      : null,
  ]);
}

function sessaoAberta(sessao, aoEncerrar) {
  const resumo = el('textarea', {
    class: 'input',
    rows: '4',
    placeholder: 'Deixe vazio para o painel montar dos fatos observados.',
  });
  const proximos = el('textarea', {
    class: 'input',
    rows: '2',
    placeholder: 'O que fica para a próxima sessão.',
  });

  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Sessão em andamento' }),
      el('span', {
        class: 'panel__count',
        text: `desde ${relativeTime(sessao.started_at)}`,
      }),
    ]),
    el('div', { class: 'panel__body' }, [
      sessao.objective
        ? el('p', {}, [el('strong', { text: 'Objetivo: ' }), sessao.objective])
        : el('p', { class: 'field__hint', text: 'Sem objetivo declarado.' }),
      fatos(sessao.facts),
      campo('O que aconteceu', resumo, 'Vazio = o painel escreve a partir do que observou.'),
      campo('Próximo passo', proximos),
      el('div', { class: 'form-actions' }, [
        el(
          'button',
          {
            class: 'btn btn--primary',
            type: 'button',
            onClick: () => aoEncerrar(resumo.value, proximos.value),
          },
          [icon('check', { size: 14 }), 'Encerrar sessão']
        ),
      ]),
    ]),
  ]);
}

function sessaoFechada(anterior, aoIniciar) {
  const objetivo = el('input', {
    class: 'input',
    type: 'text',
    placeholder: 'O que você quer terminar hoje neste projeto.',
    maxlength: '500',
  });

  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Iniciar sessão' }),
    ]),
    el('div', { class: 'panel__body' }, [
      anterior
        ? el('div', { class: 'session-previous' }, [
            el('span', { class: 'field__label', text: 'Última sessão' }),
            el('p', { class: 'field__hint', text: relativeTime(anterior.ended_at) }),
            anterior.summary ? el('p', { text: anterior.summary }) : null,
            anterior.next_steps
              ? el('p', {}, [
                  el('strong', { text: 'Ficou para depois: ' }),
                  anterior.next_steps,
                ])
              : null,
          ])
        : el('p', {
            class: 'field__hint',
            text: 'Nenhuma sessão registrada ainda neste projeto.',
          }),
      campo('Objetivo (opcional)', objetivo),
      el('div', { class: 'form-actions' }, [
        el(
          'button',
          {
            class: 'btn btn--primary',
            type: 'button',
            onClick: () => aoIniciar(objetivo.value),
          },
          [icon('power', { size: 14 }), 'Iniciar sessão']
        ),
      ]),
    ]),
  ]);
}

function historico(itens) {
  const fechadas = itens.filter((s) => !s.is_open);
  if (!fechadas.length) return null;

  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Sessões anteriores' }),
      el('span', { class: 'panel__count', text: String(fechadas.length) }),
    ]),
    el('div', { class: 'panel__body' }, [
      el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table' }, [
          el(
            'tbody',
            {},
            fechadas.map((sessao) =>
              el('tr', {}, [
                el('td', { class: 'field__hint', text: relativeTime(sessao.ended_at) }),
                el('td', {}, [
                  sessao.objective ? el('div', { text: sessao.objective }) : null,
                  el('div', { class: 'field__hint', text: sessao.summary ?? '' }),
                ]),
              ])
            )
          ),
        ]),
      ]),
    ]),
  ]);
}

function memoria(itens, aoGravar, aoApagar) {
  const tipo = el(
    'select',
    { class: 'input' },
    TIPOS_DE_MEMORIA.map((t) => el('option', { value: t.value, text: t.label }))
  );
  const titulo = el('input', { class: 'input', type: 'text', placeholder: 'Em uma linha.' });
  const corpo = el('textarea', {
    class: 'input',
    rows: '3',
    placeholder: 'O porquê, a alternativa descartada, o que se aprendeu.',
  });

  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Memória do projeto' }),
      el('span', { class: 'panel__count', text: String(itens.length) }),
    ]),
    el('div', { class: 'panel__body' }, [
      el('p', {
        class: 'field__hint',
        text:
          'O que não se deduz do código: decisão tomada, alternativa descartada, ' +
          'armadilha já paga. É o que evita reexplicar o projeto toda vez.',
      }),
      itens.length
        ? el('div', { class: 'table-wrap' }, [
            el('table', { class: 'table' }, [
              el(
                'tbody',
                {},
                itens.map((item) =>
                  el('tr', {}, [
                    el('td', {}, [
                      el('span', { class: 'chip', text: ROTULO_DE_TIPO[item.kind] ?? item.kind }),
                    ]),
                    el('td', {}, [
                      el('div', {}, [
                        el('strong', { text: item.title }),
                        // Sugestão não confirmada nunca aparece como afirmação
                        // do projeto: é a mesma regra do "no ar" sem prova.
                        item.confirmed
                          ? null
                          : el('span', {
                              class: 'signal',
                              dataset: { kind: 'partial' },
                              title: 'Sugerido pela IA, ainda não confirmado por você.',
                              text: ' a confirmar',
                            }),
                      ]),
                      item.body ? el('div', { class: 'field__hint', text: item.body }) : null,
                    ]),
                    el('td', { class: 'table__end' }, [
                      el('button', {
                        class: 'btn btn--sm btn--danger',
                        type: 'button',
                        text: 'Apagar',
                        onClick: () => aoApagar(item),
                      }),
                    ]),
                  ])
                )
              ),
            ]),
          ])
        : el('p', { class: 'panel__empty', text: 'Nada registrado ainda.' }),
      el('div', { class: 'form-grid' }, [
        campo('Tipo', tipo),
        campo('Título', titulo),
      ]),
      campo('Detalhe', corpo),
      el('div', { class: 'form-actions' }, [
        el(
          'button',
          {
            class: 'btn',
            type: 'button',
            onClick: () => aoGravar({ kind: tipo.value, title: titulo.value, body: corpo.value }),
          },
          [icon('plus', { size: 14 }), 'Gravar memória']
        ),
      ]),
    ]),
  ]);
}

export async function renderSessionPanel(container, project) {
  const redesenhar = () => renderSessionPanel(container, project);

  let sessoes;
  let memorias;
  try {
    [sessoes, memorias] = await Promise.all([
      api.sessions(project.id),
      api.projectMemory(project.id),
    ]);
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  const iniciar = async (objetivo) => {
    try {
      await api.startSession(project.id, objetivo);
      toast(`${project.name}: sessão iniciada.`, { kind: 'success' });
      redesenhar();
    } catch (error) {
      showError(error);
    }
  };

  const encerrar = async (resumo, proximos) => {
    try {
      const sessao = await api.endSession(project.id, resumo, proximos);
      toast('Sessão encerrada.', { kind: 'success', meta: sessao.summary ?? '' });
      redesenhar();
    } catch (error) {
      showError(error);
    }
  };

  const gravar = async (dados) => {
    if (!dados.title.trim()) {
      toast('A memória precisa de um título.', { kind: 'warning' });
      return;
    }
    try {
      await api.createProjectMemory(project.id, {
        ...dados,
        session_id: sessoes.current?.id ?? null,
      });
      toast('Memória gravada.', { kind: 'success' });
      redesenhar();
    } catch (error) {
      showError(error);
    }
  };

  const apagar = async (item) => {
    if (!window.confirm(`Apagar a memória "${item.title}"?`)) return;
    try {
      await api.deleteMemory(item.id);
      redesenhar();
    } catch (error) {
      showError(error);
    }
  };

  mount(
    container,
    sessoes.current
      ? sessaoAberta(sessoes.current, encerrar)
      : sessaoFechada(sessoes.previous, iniciar),
    memoria(memorias.items, gravar, apagar),
    historico(sessoes.items)
  );
}
