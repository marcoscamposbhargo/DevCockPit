// Folha de atalhos, aberta com `?`.
//
// A aplicação tem seis gestos de teclado e nenhum era descobrível: Ctrl+K
// aparecia no placeholder da busca e o resto só existia para quem leu o código.
// Atalho que ninguém encontra é trabalho jogado fora — e pior, faz a pessoa
// repetir com o mouse algo que já estava resolvido.
//
// `?` é a convenção: GitHub, Gmail, Linear, Slack. Herdar o gesto custa menos
// que ensinar um novo, e quem já tem o hábito acha sem procurar.

import { el, mount } from './dom.js';

const ATALHOS = [
  { teclas: ['Ctrl', 'K'], o_que: 'Focar a busca' },
  { teclas: ['Ctrl', 'B'], o_que: 'Recolher ou expandir a barra lateral' },
  { teclas: ['Ctrl', 'Alt', 'B'], o_que: 'Mostrar ou ocultar os projetos ativos' },
  { teclas: ['R'], o_que: 'Recarregar a tela atual' },
  { teclas: ['Esc'], o_que: 'Limpar a busca, ou fechar o que estiver aberto' },
  { teclas: ['?'], o_que: 'Abrir esta lista' },
];

let aberta = null;

function tecla(texto) {
  return el('kbd', { class: 'kbd', text: texto });
}

function montar() {
  const fechar = () => {
    aberta?.remove();
    aberta = null;
    document.removeEventListener('keydown', aoTeclar, true);
  };

  function aoTeclar(evento) {
    if (evento.key === 'Escape') {
      evento.preventDefault();
      // `stopPropagation` porque o Esc também limpa a busca: fechar a folha e
      // apagar o que a pessoa digitou com a mesma tecla seria surpresa.
      evento.stopPropagation();
      fechar();
    }
  }

  const painel = el(
    'div',
    { class: 'shortcuts', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Atalhos de teclado' },
    [
      el('div', { class: 'shortcuts__head' }, [
        el('h2', { text: 'Atalhos' }),
        el('button', {
          class: 'btn btn--sm',
          type: 'button',
          text: 'Fechar',
          onClick: fechar,
        }),
      ]),
      el(
        'dl',
        { class: 'shortcuts__list' },
        ATALHOS.flatMap((atalho) => [
          el(
            'dt',
            {},
            atalho.teclas.flatMap((t, i) => (i ? [' + ', tecla(t)] : [tecla(t)]))
          ),
          el('dd', { text: atalho.o_que }),
        ])
      ),
    ]
  );

  const fundo = el('div', {
    class: 'shortcuts__backdrop',
    onClick: fechar,
  });

  aberta = el('div', { class: 'shortcuts__layer' }, [fundo, painel]);
  document.body.append(aberta);
  document.addEventListener('keydown', aoTeclar, true);
  painel.querySelector('button')?.focus();
}

/** Liga o `?` global. Chamado uma vez, na partida. */
export function wireShortcuts() {
  document.addEventListener('keydown', (evento) => {
    if (evento.key !== '?') return;

    // Digitar "?" num campo de texto é digitar, não pedir ajuda.
    const alvo = evento.target;
    const digitando =
      alvo instanceof HTMLElement &&
      (alvo.tagName === 'INPUT' ||
        alvo.tagName === 'TEXTAREA' ||
        alvo.tagName === 'SELECT' ||
        alvo.isContentEditable);
    if (digitando) return;

    evento.preventDefault();
    if (aberta) {
      aberta.remove();
      aberta = null;
      return;
    }
    montar();
  });
}

/** Dica discreta na barra lateral, para quem nunca apertaria `?` por conta. */
export function shortcutsHint() {
  const botao = el('button', {
    class: 'shortcuts-hint',
    type: 'button',
    title: 'Ver os atalhos de teclado',
    onClick: () => {
      if (!aberta) montar();
    },
  });
  mount(botao, tecla('?'), el('span', { text: 'atalhos' }));
  return botao;
}
