// Os comandos de barra: o que eles resolvem, e o que se recusam a resolver.

import assert from 'node:assert/strict';
import { test } from 'node:test';

const { COMANDOS, interpretarComando, sugerir } = await import(
  new URL('../../frontend/js/lib/comandos.js', import.meta.url).href
);

test('comando vira pergunta com o chapéu certo', () => {
  const r = interpretarComando('/why');

  assert.equal(r.agente, 'devops');
  assert.ok(r.pergunta.length > 20, 'a frase enviada é a longa, não o comando');
});

test('o que a pessoa escreveu depois do comando não se perde', () => {
  // Quem digita "/why o banco" tinha algo específico em mente; jogar isso fora
  // seria pior do que não ter comando nenhum.
  const r = interpretarComando('/why o banco não conecta');

  assert.ok(r.pergunta.includes('o banco não conecta'));
});

test('texto comum não é comando', () => {
  assert.equal(interpretarComando('por que não sobe?'), null);
  assert.equal(interpretarComando('/inexistente'), null);
  assert.equal(interpretarComando(''), null);
});

test('a sugestão filtra pelo que já foi digitado', () => {
  assert.equal(sugerir('/').length, COMANDOS.length);
  assert.deepEqual(sugerir('/pl').map((c) => c.nome), ['/plan']);
  assert.equal(sugerir('nada').length, 0);
});

test('com o comando inteiro e um argumento, a lista sai da frente', () => {
  assert.equal(sugerir('/why o banco').length, 0);
});

test('todo comando aponta para um chapéu que existe', () => {
  const chapeus = new Set(['devops', 'fullstack', 'qa']);
  for (const comando of COMANDOS) {
    assert.ok(chapeus.has(comando.agente), `${comando.nome} aponta para ${comando.agente}`);
    assert.ok(comando.nome.startsWith('/'));
    assert.ok(comando.resumo.length > 0);
  }
});
