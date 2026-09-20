// MVP 3 do HyperBrain: o que um projeto tem dentro.
//
// O que se protege aqui não é o desenho das seções — é a regra que elas
// existem para cumprir: **uma chamada por clique, nunca tudo de uma vez**, e
// nenhuma lista vazia se passando por falha (nem o contrário).

import assert from 'node:assert/strict';
import test from 'node:test';

import { FakeNode, instalarDom } from './dom.mjs';

instalarDom();

const { detalhesDoProjeto } = await import('../../frontend/js/lib/graph/detalhes.js');

/** `fetch` de mentira que conta quantas vezes cada rota foi chamada. */
function instalarFetch(rotas) {
  const chamadas = [];
  globalThis.fetch = async (url) => {
    const caminho = String(url.pathname ?? url).split('?')[0];
    chamadas.push(caminho);
    if (!(caminho in rotas)) throw new Error(`rota não prevista: ${caminho}`);
    const valor = rotas[caminho];
    if (valor instanceof Error) throw valor;
    return { ok: true, status: 200, json: async () => valor };
  };
  return chamadas;
}

function botoes(raiz) {
  return raiz.findByClass('hb-detalhe__cabecalho');
}

/** Espera o microtask do clique drenar — o carregamento é assíncrono. */
const assentar = () => new Promise((r) => setTimeout(r, 0));

test('as quatro seções nascem fechadas e não buscam nada', () => {
  const chamadas = instalarFetch({});
  const raiz = detalhesDoProjeto('loja-virtual');

  assert.equal(botoes(raiz).length, 4, 'tarefas, sessões, decisões e serviços');
  assert.equal(chamadas.length, 0, 'abrir um projeto não pode disparar quatro requisições');
  for (const b of botoes(raiz)) {
    assert.equal(b.getAttribute('aria-expanded'), 'false');
  }
});

test('abrir uma seção busca só a rota dela', async () => {
  const chamadas = instalarFetch({
    '/api/projects/loja-virtual/tasks': {
      items: [{ id: 1, title: 'Subir o ambiente', is_open: true, status: 'OPEN' }],
    },
  });
  const raiz = detalhesDoProjeto('loja-virtual');

  botoes(raiz)[0].emit('click');
  await assentar();

  assert.deepEqual(chamadas, ['/api/projects/loja-virtual/tasks']);
  assert.ok(raiz.textContent.includes('Subir o ambiente'));
});

test('reabrir a mesma seção não busca de novo', async () => {
  const chamadas = instalarFetch({
    '/api/projects/loja-virtual/tasks': { items: [{ id: 1, title: 'X', is_open: true }] },
  });
  const raiz = detalhesDoProjeto('loja-virtual');
  const botao = botoes(raiz)[0];

  botao.emit('click');
  await assentar();
  botao.emit('click'); // fecha
  botao.emit('click'); // abre de novo
  await assentar();

  assert.equal(chamadas.length, 1, 'o dado já estava em mãos; pedir de novo é desperdício');
});

test('lista vazia diz que está vazia, e não some', async () => {
  instalarFetch({ '/api/projects/loja-virtual/tasks': { items: [] } });
  const raiz = detalhesDoProjeto('loja-virtual');

  botoes(raiz)[0].emit('click');
  await assentar();

  assert.ok(raiz.textContent.includes('nada registrado'));
});

test('falha de rede vira texto na seção, não lista vazia', async () => {
  instalarFetch({ '/api/projects/loja-virtual/tasks': new Error('rede fora') });
  const raiz = detalhesDoProjeto('loja-virtual');

  botoes(raiz)[0].emit('click');
  await assentar();

  const texto = raiz.textContent;
  assert.ok(texto.includes('não carregou'), '"não consegui perguntar" ≠ "não há nada"');
  assert.ok(!texto.includes('nada registrado'));
});

test('sessão em aberto não inventa duração', async () => {
  instalarFetch({
    '/api/projects/loja-virtual/sessions': {
      items: [
        { id: 's1', objective: 'Ajustar portas', is_open: true, started_at: null, facts: {} },
      ],
    },
  });
  const raiz = detalhesDoProjeto('loja-virtual');

  botoes(raiz)[1].emit('click');
  await assentar();

  const texto = raiz.textContent;
  assert.ok(texto.includes('em aberto'));
  assert.ok(!texto.includes('0 min'), 'sessão que não terminou não tem duração');
});

test('o corte só é anunciado quando de fato cortou', async () => {
  const muitas = Array.from({ length: 12 }, (_, i) => ({
    id: i,
    title: `Tarefa ${i}`,
    is_open: true,
  }));
  instalarFetch({ '/api/projects/loja-virtual/tasks': { items: muitas } });
  const raiz = detalhesDoProjeto('loja-virtual');

  botoes(raiz)[0].emit('click');
  await assentar();

  assert.ok(raiz.textContent.includes('mostrando 8 de 12'));
});
