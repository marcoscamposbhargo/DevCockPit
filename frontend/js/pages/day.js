// Start My Day — a primeira tela da manhã.
//
// Ela responde uma pergunta só: **por onde começar hoje?** E responde dizendo
// o motivo, não só a ordem. Um ranking sem justificativa é adivinhação com
// aparência de método; com o motivo escrito, dá para discordar dele — que é o
// que torna a sugestão útil.
//
// Nada aqui vem de modelo de IA. Tudo sai de sessão registrada, próximo passo
// declarado, Git e verificador de serviço: coisas que o painel já media.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { relativeTime } from '../lib/format.js';
import { icon } from '../lib/icons.js';
import { emptyState, loading, pageHeader, showError } from '../lib/ui.js';

function saudacao() {
  const hora = new Date().getHours();
  if (hora < 5) return 'Boa madrugada';
  if (hora < 12) return 'Bom dia';
  if (hora < 18) return 'Boa tarde';
  return 'Boa noite';
}

function cartao(item, posicao) {
  const destino = `#/projects/${encodeURIComponent(item.project_id)}?tab=session`;

  return el('article', { class: 'day-card', dataset: { first: String(posicao === 0) } }, [
    el('header', { class: 'day-card__head' }, [
      el('span', { class: 'day-card__rank', text: String(posicao + 1) }),
      el('a', { class: 'day-card__name', href: destino, text: item.name }),
      item.open_session
        ? el('span', { class: 'signal', dataset: { kind: 'on' } }, [
            el('span', { class: 'signal__dot' }),
            'sessão aberta',
          ])
        : null,
    ]),

    // O motivo vem antes do conteúdo: é o que justifica a posição.
    el('p', { class: 'day-card__reason', text: item.reason }),

    // A tarefa vem antes do próximo passo: ela sobrevive a sessões e alguém
    // precisa fechá-la; o próximo passo é uma nota que a sessão seguinte
    // substitui.
    item.next_task
      ? el('div', { class: 'day-card__next' }, [
          el('span', { class: 'field__label' }, [
            item.next_task.status === 'DOING' ? 'Em curso' : 'Próxima tarefa',
            item.open_tasks > 1
              ? el('span', { class: 'field__hint', text: ` · ${item.open_tasks} abertas` })
              : null,
          ]),
          el('p', { text: item.next_task.title }),
        ])
      : null,

    item.next_step
      ? el('div', { class: 'day-card__step' }, [
          el('span', { class: 'field__label', text: 'Próximo passo da última sessão' }),
          el('p', { text: item.next_step }),
        ])
      : null,

    item.last_summary
      ? el('details', { class: 'day-card__last' }, [
          el('summary', {
            text: `Última sessão ${relativeTime(item.last_session_at)}`,
          }),
          el('p', { class: 'field__hint', text: item.last_summary }),
        ])
      : el('p', {
          class: 'field__hint',
          text: item.last_session_at
            ? `Última sessão ${relativeTime(item.last_session_at)}`
            : 'Sem sessão registrada ainda.',
        }),

    el('div', { class: 'day-card__foot' }, [
      el('a', { class: 'btn btn--sm btn--primary', href: destino }, [
        icon('power', { size: 13 }),
        item.open_session ? 'Continuar' : 'Iniciar sessão',
      ]),
      el('a', {
        class: 'btn btn--sm',
        href: `#/projects/${encodeURIComponent(item.project_id)}`,
        text: 'Abrir projeto',
      }),
    ]),
  ]);
}

export async function renderDay(container) {
  mount(container, loading());

  let dados;
  try {
    dados = await api.day();
  } catch (error) {
    showError(error);
    mount(container, el('p', { class: 'loading', text: error.message }));
    return;
  }

  if (!dados.items.length) {
    mount(
      container,
      pageHeader({ title: `${saudacao()}.` }),
      emptyState({
        title: 'Nada para retomar ainda',
        text:
          'Esta tela se alimenta do que você registra: tarefas abertas e sessões ' +
          'encerradas. Abra um projeto, anote o que falta e inicie uma sessão.',
        actions: [el('a', { class: 'btn btn--primary', href: '#/projects', text: 'Ver projetos' })],
      })
    );
    return;
  }

  const abertas = dados.open_sessions.length;

  mount(
    container,
    pageHeader({
      title: `${saudacao()}.`,
      subtitle:
        `${dados.total_projects} projeto(s) cadastrado(s)` +
        (abertas ? ` · ${abertas} com sessão aberta` : ''),
    }),

    dados.suggestion
      ? el('p', { class: 'day-suggestion' }, [
          'Sugestão de foco: ',
          el('strong', { text: dados.suggestion }),
        ])
      : null,

    el('div', { class: 'day-grid' }, dados.items.map(cartao)),

    el('p', {
      class: 'field__hint',
      text:
        'A ordem sai de sessão aberta, tarefa em curso, próximo passo declarado, ' +
        'alteração sem commit e serviço no ar — tudo medido pelo painel, sem IA.',
    })
  );
}
