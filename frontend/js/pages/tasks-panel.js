// Lista de tarefas do projeto.
//
// Mínima de propósito: título, prioridade e estado. Sem sprint, sem estimativa,
// sem responsável — é um painel de um desenvolvedor só, e um Jira embutido
// seria a forma mais rápida de ninguém usar.
//
// A ordem é a opinião da tela: **em curso antes de aberta**, porque tarefa
// começada e largada é o que mais custa lembrar; depois prioridade; depois
// idade, para o backlog não virar depósito.

import { api } from '../lib/api.js';
import { el } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { showError, toast } from '../lib/ui.js';

const PRIORIDADES = [
  { value: 1, label: 'Alta' },
  { value: 2, label: 'Média' },
  { value: 3, label: 'Baixa' },
];

const ROTULO_DE_ESTADO = {
  OPEN: 'aberta',
  DOING: 'em curso',
  DONE: 'feita',
  DROPPED: 'descartada',
};

//: Cor por estado, reusando os tons que o painel já tem: em curso é o que
//: chama atenção; descartada não é erro, então não é vermelha.
const TOM_DE_ESTADO = {
  OPEN: 'partial',
  DOING: 'on',
  DONE: 'off',
  DROPPED: 'off',
};

function linha(tarefa, aoMudar, aoApagar) {
  const proximoEstado = tarefa.status === 'OPEN' ? 'DOING' : 'OPEN';

  return el('tr', { dataset: { done: String(!tarefa.is_open) } }, [
    el('td', {}, [
      el('span', { class: 'signal', dataset: { kind: TOM_DE_ESTADO[tarefa.status] ?? 'off' } }, [
        el('span', { class: 'signal__dot' }),
        ROTULO_DE_ESTADO[tarefa.status] ?? tarefa.status,
      ]),
    ]),
    el('td', {}, [
      el('div', { class: tarefa.is_open ? '' : 'task--done', text: tarefa.title }),
      tarefa.detail ? el('div', { class: 'field__hint', text: tarefa.detail }) : null,
      tarefa.source === 'ai_suggested'
        ? el('span', {
            class: 'signal',
            dataset: { kind: 'partial' },
            title: 'Sugerida pela IA, ainda não confirmada.',
            text: 'a confirmar',
          })
        : null,
    ]),
    el('td', { class: 'field__hint', text: PRIORIDADES[tarefa.priority - 1]?.label ?? '—' }),
    el('td', {
      class: 'field__hint',
      text: tarefa.done_at ? relativeTime(tarefa.done_at) : relativeTime(tarefa.created_at),
    }),
    el('td', { class: 'table__end' }, [
      tarefa.is_open
        ? el('button', {
            class: 'btn btn--sm',
            type: 'button',
            text: tarefa.status === 'OPEN' ? 'Começar' : 'Voltar',
            title:
              tarefa.status === 'OPEN'
                ? 'Marca como em curso — sobe para o topo da lista.'
                : 'Devolve para aberta.',
            onClick: () => aoMudar(tarefa, { status: proximoEstado }),
          })
        : null,
      tarefa.is_open
        ? el(
            'button',
            {
              class: 'btn btn--sm btn--primary',
              type: 'button',
              onClick: () => aoMudar(tarefa, { status: 'DONE' }),
            },
            [icon('check', { size: 12 }), 'Feita']
          )
        : el('button', {
            class: 'btn btn--sm',
            type: 'button',
            text: 'Reabrir',
            onClick: () => aoMudar(tarefa, { status: 'OPEN' }),
          }),
      tarefa.is_open
        ? el('button', {
            class: 'btn btn--sm',
            type: 'button',
            text: 'Descartar',
            title: 'Diferente de apagar: guarda que a ideia foi considerada e descartada.',
            onClick: () => aoMudar(tarefa, { status: 'DROPPED' }),
          })
        : el('button', {
            class: 'btn btn--sm btn--danger',
            type: 'button',
            text: 'Apagar',
            onClick: () => aoApagar(tarefa),
          }),
    ]),
  ]);
}

/**
 * Painel de tarefas.
 *
 * @param {object} project
 * @param {object} dados        resposta de `api.tasks`
 * @param {Function} recarregar
 * @param {string|null} sessionId  sessão aberta, para a tarefa nascer ligada a ela
 */
export function tasksPanel(project, dados, recarregar, sessionId = null) {
  const titulo = el('input', {
    class: 'input',
    type: 'text',
    placeholder: 'O que falta fazer.',
    maxlength: '200',
  });
  const prioridade = el(
    'select',
    { class: 'input' },
    PRIORIDADES.map((p) =>
      el('option', { value: String(p.value), text: p.label, selected: p.value === 2 })
    )
  );

  const criar = async () => {
    if (!titulo.value.trim()) {
      toast('A tarefa precisa de um título.', { kind: 'warning' });
      return;
    }
    try {
      await api.createTask(project.id, {
        title: titulo.value,
        priority: Number(prioridade.value),
        session_id: sessionId,
      });
      recarregar();
    } catch (error) {
      showError(error);
    }
  };

  const mudar = async (tarefa, mudanca) => {
    try {
      await api.updateTask(tarefa.id, mudanca);
      recarregar();
    } catch (error) {
      showError(error);
    }
  };

  const apagar = async (tarefa) => {
    if (!window.confirm(`Apagar "${tarefa.title}"?`)) return;
    try {
      await api.deleteTask(tarefa.id);
      recarregar();
    } catch (error) {
      showError(error);
    }
  };

  titulo.addEventListener('keydown', (evento) => {
    // Enter cria: é uma lista onde se digita várias em sequência, e obrigar a
    // buscar o botão a cada item mataria o uso.
    if (evento.key === 'Enter') criar();
  });

  return el('section', { class: 'panel' }, [
    el('header', { class: 'panel__header' }, [
      el('h2', { class: 'panel__title', text: 'Tarefas' }),
      el('span', { class: 'panel__count', text: `${dados.open_count} aberta(s)` }),
    ]),
    el('div', { class: 'panel__body' }, [
      dados.items.length
        ? el('div', { class: 'table-wrap' }, [
            el('table', { class: 'table' }, [
              el(
                'tbody',
                {},
                dados.items.map((tarefa) => linha(tarefa, mudar, apagar))
              ),
            ]),
          ])
        : el('p', {
            class: 'panel__empty',
            text: 'Nenhuma tarefa. O que ficar pendente aqui aparece na tela do dia.',
          }),

      el('div', { class: 'form-grid' }, [
        el('div', { class: 'field' }, [
          el('label', { class: 'field__label', text: 'Nova tarefa' }),
          titulo,
        ]),
        el('div', { class: 'field' }, [
          el('label', { class: 'field__label', text: 'Prioridade' }),
          prioridade,
        ]),
      ]),
      el('div', { class: 'form-actions' }, [
        el('button', { class: 'btn', type: 'button', onClick: criar }, [
          icon('plus', { size: 14 }),
          'Adicionar',
        ]),
      ]),
    ]),
  ]);
}
