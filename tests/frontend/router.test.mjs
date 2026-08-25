// Roteamento: resolução de rota e, principalmente, a limpeza ao sair dela.
//
// O bug que motivou este arquivo: a tela Ports mantinha um timer de recarga
// que se protegia com `container.isConnected`. Como o `<main id="view">` é o
// mesmo elemento em todas as rotas, esse teste nunca era falso — o timer
// sobrevivia à navegação e, a cada seis segundos, redesenhava Ports por cima
// da tela aberta.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { instalarDom } from './dom.mjs';

const MODULO = new URL('../../frontend/js/router.js', import.meta.url).href;

async function carregarRouter(opcoes) {
  const utilidades = instalarDom(opcoes);
  // `?fresh=` força um módulo novo: o roteador guarda estado em variáveis de
  // módulo (rotas registradas, limpezas pendentes), e um teste não pode herdar
  // o estado do anterior.
  const router = await import(`${MODULO}?fresh=${Math.random()}`);
  return { router, ...utilidades };
}

test('resolve rota com parâmetro e query', async () => {
  const { router } = await carregarRouter();
  router.register('project', '/projects/:id', () => {});

  const alvo = router.resolve('#/projects/meu-app?tab=git');

  assert.equal(alvo.name, 'project');
  assert.equal(alvo.params.id, 'meu-app');
  assert.equal(alvo.query.tab, 'git');
});

test('rota desconhecida não resolve', async () => {
  const { router } = await carregarRouter();
  router.register('dashboard', '/dashboard', () => {});

  assert.equal(router.resolve('#/inexistente'), null);
});

test('a limpeza registrada roda ao trocar de rota', async () => {
  const { router, navegar } = await carregarRouter({ hash: '#/ports' });

  let parou = 0;
  router.register('ports', '/ports', () => router.aoSairDaRota(() => (parou += 1)));
  router.register('dashboard', '/dashboard', () => {});

  const view = new globalThis.Node('main');
  await router.start(view);
  assert.equal(parou, 0, 'nada a limpar enquanto a tela está aberta');

  await navegar('#/dashboard');

  assert.equal(parou, 1, 'sair da rota precisa parar o que ela deixou de pé');
});

test('a limpeza só roda uma vez', async () => {
  const { router, navegar } = await carregarRouter({ hash: '#/ports' });

  let parou = 0;
  router.register('ports', '/ports', () => router.aoSairDaRota(() => (parou += 1)));
  router.register('dashboard', '/dashboard', () => {});

  const view = new globalThis.Node('main');
  await router.start(view);
  await navegar('#/dashboard');
  await navegar('#/dashboard');

  assert.equal(parou, 1);
});

test('limpeza que falha não impede a próxima tela', async () => {
  const { router, navegar } = await carregarRouter({ hash: '#/ports' });

  let renderizou = false;
  router.register('ports', '/ports', () =>
    router.aoSairDaRota(() => {
      throw new Error('timer teimoso');
    })
  );
  router.register('dashboard', '/dashboard', () => {
    renderizou = true;
  });

  const view = new globalThis.Node('main');
  await router.start(view);
  await navegar('#/dashboard');

  assert.equal(renderizou, true);
});
