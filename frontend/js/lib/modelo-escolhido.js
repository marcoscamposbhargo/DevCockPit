// Modelo fixado na tela (REQ-08 do AI Harness).
//
// A escolha é uma só para o chat de projeto e para a pergunta rápida: quem
// fixou o Claude num lugar espera o Claude no outro. Vai ao servidor como id
// lógico do registro (`claude-principal`), nunca como nome no fornecedor — o
// servidor ignora id que não conhece e segue o automático (P-06).
//
// Vazio é o automático: o router decide pela complexidade da pergunta.

import { el } from './dom.js';

const CHAVE = 'devcockpit.ai.modelo';

/** O id salvo, se ainda for um dos oferecidos. Senão, o automático. */
export function modeloEscolhido(status) {
  let salvo = '';
  try {
    salvo = window.localStorage.getItem(CHAVE) ?? '';
  } catch {
    // localStorage bloqueado não pode impedir a pergunta: vale o automático.
  }
  return (status.modelos ?? []).some((m) => m.id === salvo) ? salvo : '';
}

function gravar(id) {
  try {
    if (id) window.localStorage.setItem(CHAVE, id);
    else window.localStorage.removeItem(CHAVE);
  } catch {
    /* sem memória entre aberturas; a escolha vale só nesta tela. */
  }
}

/** `<select>` entre o automático e os modelos que o servidor ofereceu.
 *
 * `null` quando o registro não oferece nada — aí vale o seletor antigo de
 * rápido/caprichado, que escolhe entre os dois modelos do `.env`.
 */
export function seletorDoRegistro(status) {
  const modelos = status.modelos ?? [];
  if (!modelos.length) return null;

  const seletor = el('select', {
    class: 'chat-modelo-select',
    'aria-label': 'Modelo',
    title: 'Automático: o painel escolhe pela complexidade da pergunta.',
  }, [
    el('option', { value: '', text: 'Automático' }),
    ...modelos.map((m) =>
      el('option', {
        value: m.id,
        text: m.local ? `${m.model} · local` : m.model,
      })
    ),
  ]);
  seletor.value = modeloEscolhido(status);
  seletor.addEventListener('change', () => gravar(seletor.value));
  return seletor;
}

/** Frase curta de quem respondeu, a partir do `event: meta` do servidor. */
export function quemRespondeu(meta) {
  return meta?.model ? `respondido por ${meta.model}` : '';
}
