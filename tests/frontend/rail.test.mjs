// O que a barra lateral afirma sobre cada projeto.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { instalarDom } from './dom.mjs';

instalarDom();

const { combinar } = await import(new URL('../../frontend/js/lib/rail.js', import.meta.url).href);

const projeto = (id, extra = {}) => ({ id, name: id, services_total: 1, ...extra });

test('projeto que ninguém mediu não é dado como parado', () => {
  // "0 de 1 online" e "ninguém verificou ainda" são fatos diferentes, e a
  // lateral dizia o primeiro nos dois casos — inclusive para um projeto com os
  // containers de pé, que foi como o defeito apareceu.
  const [linha] = combinar([projeto('a')], { active_services: [], checked_project_ids: [] });

  assert.equal(linha.medido, false);
  assert.equal(linha.online, 0);
});

test('projeto medido e sem resposta é parado de verdade', () => {
  const [linha] = combinar([projeto('a')], {
    active_services: [],
    checked_project_ids: ['a'],
  });

  assert.equal(linha.medido, true);
  assert.equal(linha.online, 0);
});

test('serviço sem dono provado não conta como no ar', () => {
  // `proven: false` é "alguém responde nessa porta", não "este projeto está no
  // ar": dois projetos na mesma porta padrão é o caso comum.
  const [linha] = combinar([projeto('a')], {
    active_services: [{ project_id: 'a', proven: false, port: 3000 }],
    checked_project_ids: ['a'],
  });

  assert.equal(linha.online, 0);
});

test('serviço provado conta', () => {
  const [linha] = combinar([projeto('a')], {
    active_services: [{ project_id: 'a', proven: true, port: 3000, url: 'http://x' }],
    checked_project_ids: ['a'],
  });

  assert.equal(linha.online, 1);
  assert.equal(linha.medido, true);
});
