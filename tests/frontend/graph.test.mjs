// O que o grafo do HyperBrain afirma, e o que ele se recusa a afirmar.
//
// `adapter.js` e `layout.js` não tocam em DOM de propósito — é o que permite
// testá-los aqui sem nenhum dublê de navegador.

import assert from 'node:assert/strict';
import { test } from 'node:test';

const { montarGrafo, estadoDoProjeto, vizinhos, tecnologiasExclusivas } = await import(
  new URL('../../frontend/js/lib/graph/adapter.js', import.meta.url).href
);
const { criarLayout, posicaoInicial } = await import(
  new URL('../../frontend/js/lib/graph/layout.js', import.meta.url).href
);
const { encurtar } = await import(
  new URL('../../frontend/js/lib/graph/render.js', import.meta.url).href
);

function projeto(id, extras = {}) {
  return {
    id,
    name: id,
    path: `C:/dev/${id}`,
    status: 'REGISTERED',
    is_pinned: false,
    technologies: [],
    services_total: 0,
    last_accessed_at: null,
    can_start: false,
    app_running: false,
    ...extras,
  };
}

// --- adaptador ------------------------------------------------------------

test('todo projeto se liga ao núcleo', () => {
  const { nos, arestas } = montarGrafo([projeto('a'), projeto('b')]);

  assert.equal(nos.filter((no) => no.tipo === 'projeto').length, 2);
  assert.equal(arestas.filter((aresta) => aresta.kind === 'core').length, 2);
});

test('tecnologia usada por um projeto só não vira nó', () => {
  const { nos } = montarGrafo([projeto('a', { technologies: ['Rust'] })]);

  assert.equal(nos.filter((no) => no.tipo === 'tecnologia').length, 0);
});

test('tecnologia compartilhada vira nó e liga os dois projetos', () => {
  const { nos, arestas } = montarGrafo([
    projeto('a', { technologies: ['Python', 'Rust'] }),
    projeto('b', { technologies: ['python'] }),
  ]);

  const tecnologias = nos.filter((no) => no.tipo === 'tecnologia');
  assert.equal(tecnologias.length, 1, 'só Python é compartilhada');
  assert.equal(tecnologias[0].contagem, 2);

  const ligacoes = arestas.filter((aresta) => aresta.kind === 'tech').map((a) => a.de);
  assert.deepEqual(ligacoes.sort(), ['p:a', 'p:b']);
});

test('projeto sem aplicação separada não é declarado parado', () => {
  // `app_running: null` significa "a stack inteira roda em container": dizer
  // "parado" seria afirmar o que ninguém mediu.
  assert.equal(estadoDoProjeto(projeto('a', { app_running: null })), 'desconhecido');
  assert.equal(estadoDoProjeto(projeto('a', { app_running: false })), 'parado');
  assert.equal(estadoDoProjeto(projeto('a', { app_running: true })), 'no-ar');
});

test('projeto no ar é desenhado maior que projeto ocioso', () => {
  const { nos } = montarGrafo([projeto('a', { app_running: true }), projeto('b')]);
  const [a, b] = ['p:a', 'p:b'].map((id) => nos.find((no) => no.id === id));

  assert.ok(a.tamanho > b.tamanho);
});

test('o painel lateral separa tecnologia compartilhada da exclusiva', () => {
  const projetos = [
    projeto('a', { technologies: ['Python', 'Rust'] }),
    projeto('b', { technologies: ['Python'] }),
  ];
  const grafo = montarGrafo(projetos);

  assert.deepEqual(tecnologiasExclusivas(projetos[0], grafo), ['Rust']);
});

test('os vizinhos de um projeto incluem o núcleo e ele mesmo', () => {
  const grafo = montarGrafo([
    projeto('a', { technologies: ['Python'] }),
    projeto('b', { technologies: ['Python'] }),
  ]);

  const perto = vizinhos(grafo, 'p:a');

  assert.ok(perto.has('p:a'));
  assert.ok(perto.has('core'));
  assert.ok(perto.has('t:python'));
  assert.ok(!perto.has('p:b'), 'o outro projeto está a dois passos, não a um');
});

// --- rótulos --------------------------------------------------------------

test('nome comprido é encurtado no desenho, não no dado', () => {
  assert.equal(encurtar('PLATAFORMA DE INGRESSOS'), 'PLATAFORMA DE ING…');
  assert.equal(encurtar('kiteasy'), 'kiteasy');
  assert.equal(encurtar('  espaço  '), 'espaço');
});

// --- layout ---------------------------------------------------------------

const GRAFO = montarGrafo([
  projeto('a', { technologies: ['Python'] }),
  projeto('b', { technologies: ['Python'] }),
  projeto('c'),
]);

function posicoesEstaveis() {
  const layout = criarLayout(GRAFO.nos, GRAFO.arestas);
  layout.estabilizar();
  return layout.posicoes();
}

test('a posição inicial depende só do id', () => {
  assert.deepEqual(posicaoInicial('p:a'), posicaoInicial('p:a'));
  assert.notDeepEqual(posicaoInicial('p:a'), posicaoInicial('p:b'));
});

test('o mesmo grafo estabiliza sempre no mesmo lugar', () => {
  const primeira = posicoesEstaveis();
  const segunda = posicoesEstaveis();

  for (const [id, ponto] of primeira) {
    assert.ok(Math.abs(ponto.x - segunda.get(id).x) < 1e-9, `${id} em x`);
    assert.ok(Math.abs(ponto.y - segunda.get(id).y) < 1e-9, `${id} em y`);
  }
});

test('a simulação para sozinha', () => {
  const layout = criarLayout(GRAFO.nos, GRAFO.arestas);
  const voltas = layout.estabilizar(400);

  assert.ok(voltas < 400, `estabilizou em ${voltas} passos`);
  assert.equal(layout.passo(), false);
});

test('o núcleo fica no centro', () => {
  const posicoes = posicoesEstaveis();

  assert.deepEqual(posicoes.get('core'), { x: 0, y: 0 });
});

test('nenhuma coordenada vira NaN', () => {
  for (const [id, ponto] of posicoesEstaveis()) {
    assert.ok(Number.isFinite(ponto.x), `${id} em x`);
    assert.ok(Number.isFinite(ponto.y), `${id} em y`);
  }
});

test('dois nós exatamente sobrepostos se separam sem sortear nada', () => {
  const nos = [
    { id: 'core', fixo: true },
    { id: 'x' },
    { id: 'y' },
  ];
  const layout = criarLayout(nos, []);
  layout.fixar('x', 10, 10);
  layout.fixar('y', 10, 10);
  layout.soltar('x');
  layout.soltar('y');
  layout.reaquecer(1);
  layout.estabilizar();

  const x = layout.posicao('x');
  const y = layout.posicao('y');

  assert.ok(Number.isFinite(x.x) && Number.isFinite(y.x));
  assert.ok(Math.hypot(x.x - y.x, x.y - y.y) > 1, 'saíram de cima um do outro');
});

test('nó arrastado fica onde foi solto', () => {
  const layout = criarLayout(GRAFO.nos, GRAFO.arestas);
  layout.fixar('p:a', 400, -120);
  layout.estabilizar();

  assert.deepEqual(layout.posicao('p:a'), { x: 400, y: -120 });
});

test('aresta apontando para nó inexistente não quebra a simulação', () => {
  const layout = criarLayout(
    [{ id: 'core', fixo: true }, { id: 'p:a' }],
    [{ id: 'x', de: 'p:a', para: 'p:fantasma', kind: 'core' }]
  );

  assert.doesNotThrow(() => layout.estabilizar());
  assert.ok(Number.isFinite(layout.posicao('p:a').x));
});
