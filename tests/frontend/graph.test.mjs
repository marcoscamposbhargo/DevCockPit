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
const { interpretar, pareceOrdem } = await import(
  new URL('../../frontend/js/lib/graph/intent.js', import.meta.url).href
);
const { posicionarRotulos } = await import(
  new URL('../../frontend/js/lib/graph/labels.js', import.meta.url).href
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

  assert.deepEqual(posicoes.get('core'), { x: 0, y: 0, z: 0 });
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

  assert.deepEqual(layout.posicao('p:a'), { x: 400, y: -120, z: 0 });
});

test('aresta apontando para nó inexistente não quebra a simulação', () => {
  const layout = criarLayout(
    [{ id: 'core', fixo: true }, { id: 'p:a' }],
    [{ id: 'x', de: 'p:a', para: 'p:fantasma', kind: 'core' }]
  );

  assert.doesNotThrow(() => layout.estabilizar());
  assert.ok(Number.isFinite(layout.posicao('p:a').x));
});

// --- filtro de visão ------------------------------------------------------
//
// A regra decide sozinha o que é destaque, e **se recusa** a decidir o resto:
// verbo de ação vai para o orquestrador do servidor, pergunta vai para a IA.

const FROTA = [
  projeto('alpha', { technologies: ['Python', 'docker', 'docker-compose'], app_running: true }),
  projeto('beta', { technologies: ['node', 'docker'], is_pinned: true }),
  projeto('gama', { technologies: ['node'], ai_enabled: false }),
];

test('filtra por tecnologia, e destaca o nó dela junto', () => {
  const r = interpretar('mostre os projetos em python', FROTA);

  assert.equal(r.total, 1);
  assert.ok(r.ids.has('p:alpha'));
  assert.ok(r.ids.has('t:python'));
  assert.ok(!r.ids.has('p:beta'));
});

test('verbo de ação nunca vira filtro', () => {
  // "sobe o alpha" tem nome de projeto e casaria por nome. Se virasse
  // destaque, a tela mostraria um nó em vez de propor a ação — o oposto do
  // pedido. Isto é do orquestrador do servidor.
  assert.equal(interpretar('sobe o alpha', FROTA), null);
  assert.equal(interpretar('abre o beta no vscode', FROTA), null);
});

test('pergunta de verdade nunca vira filtro', () => {
  assert.equal(interpretar('por que o python do alpha está lento?', FROTA), null);
  assert.equal(interpretar('como faço deploy de node?', FROTA), null);
});

test('filtra por estado medido, não por status declarado', () => {
  assert.equal(interpretar('o que está no ar', FROTA).total, 1);
  assert.equal(interpretar('projetos parados', FROTA).total, 2);
  assert.equal(interpretar('fixados', FROTA).total, 1);
});

test('critérios se somam', () => {
  const r = interpretar('quais projetos em node estão parados', FROTA);

  assert.equal(r.total, 2);
  assert.ok(r.rotulo.includes('node'));
  assert.ok(r.rotulo.includes('parados'));
});

test('o nome mais longo ganha do que está contido nele', () => {
  const r = interpretar('quem usa docker-compose', FROTA);

  assert.equal(r.rotulo, 'docker-compose');
  assert.equal(r.total, 1);
});

test('frase sem critério nenhum devolve null, e não um filtro aproximado', () => {
  assert.equal(interpretar('onde paramos ontem?', FROTA), null);
  assert.equal(interpretar('', FROTA), null);
});

test('dá para ver quem está fora do Cockpit AI', () => {
  const r = interpretar('quais estão fora da ia', FROTA);

  assert.equal(r.total, 1);
  assert.ok(r.ids.has('p:gama'));
});

test('verbo destrutivo vai para o servidor, para voltar como recusa', () => {
  // Nenhum destes existe no registro fechado — e é por isso que eles precisam
  // ser mandados para lá. A resposta certa para "apaga o banco" é "não faço
  // isso", não um modelo divagando sobre como apagar um banco.
  assert.equal(pareceOrdem('apaga o banco do devcockpit'), true);
  assert.equal(pareceOrdem('deleta o projeto alpha'), true);
  assert.equal(pareceOrdem('publica em produção'), true);
});

test('só frase que soa como ordem paga o pedágio da proposta', () => {
  // Pedir proposta custa 0,2 s quando a regra do servidor decide, e de 15 a
  // 40 s quando cai no modelo local. Pergunta não deveria pagar isso.
  assert.equal(pareceOrdem('sobe o kiteasy'), true);
  assert.equal(pareceOrdem('abre o smartdash no vscode'), true);
  assert.equal(pareceOrdem('onde paramos ontem?'), false);
  assert.equal(pareceOrdem('o que esse projeto faz?'), false);
});

// --- rótulos sem colisão --------------------------------------------------

function rotulo(id, x, y, largura, extras = {}) {
  return { id, x, y, largura, altura: 12, raio: 19, prioridade: 19, ...extras };
}

test('rótulo que cabe embaixo fica embaixo', () => {
  const posicoes = posicionarRotulos([rotulo('a', 0, 0, 60)]);

  assert.equal(posicoes.get('a').anchor, 'middle');
  assert.ok(posicoes.get('a').dy > 0, 'abaixo do nó');
  assert.equal(posicoes.get('a').oculto, false);
});

test('rótulo que colidiria embaixo procura outro lado', () => {
  // Dois nós empilhados na vertical: o de baixo ocupa o lugar do rótulo do de
  // cima, então um dos dois precisa sair do padrão.
  const posicoes = posicionarRotulos([
    rotulo('cima', 0, 0, 120),
    rotulo('baixo', 0, 48, 120),
  ]);

  const lados = [posicoes.get('cima'), posicoes.get('baixo')].map((p) => p.anchor);
  assert.ok(lados.some((lado) => lado !== 'middle'), `saiu do padrão: ${lados}`);
});

test('quem tem prioridade maior fica com o lugar bom', () => {
  // Lado a lado, com nomes largos: os dois rótulos disputam a mesma faixa
  // embaixo. Quem tem prioridade escolhe primeiro; o outro se vira.
  const posicoes = posicionarRotulos([
    rotulo('pequeno', 120, 0, 200, { prioridade: 1, raio: 11 }),
    rotulo('grande', 0, 0, 200, { prioridade: 26 }),
  ]);

  assert.equal(posicoes.get('grande').anchor, 'middle');
  assert.ok(posicoes.get('grande').dy > 0, 'ficou embaixo, que é o lugar bom');
  assert.notEqual(posicoes.get('pequeno').anchor, 'middle');
});

test('sem lugar nenhum, o rótulo some em vez de atropelar o vizinho', () => {
  // Quatro nós cercando um: nenhum dos quatro lados do rótulo do meio sobra.
  const cerco = [
    rotulo('meio', 0, 0, 300),
    rotulo('n', 0, -40, 300),
    rotulo('s', 0, 40, 300),
    rotulo('l', 60, 0, 300),
    rotulo('o', -60, 0, 300),
  ];

  const posicoes = posicionarRotulos(cerco);

  assert.ok([...posicoes.values()].some((p) => p.oculto), 'alguém ficou escondido');
});

test('nó sem rótulo entra como obstáculo, e não recebe posição', () => {
  // É o caso do núcleo: nada para acomodar, mas um buraco grande no meio.
  const posicoes = posicionarRotulos([
    { id: 'nucleo', x: 0, y: 0, raio: 87, largura: 0, altura: 0, prioridade: 99 },
    rotulo('vizinho', 0, 60, 100),
  ]);

  assert.equal(posicoes.has('nucleo'), false, 'o núcleo não recebe rótulo');
  // Cercado pelo núcleo por todos os lados, o vizinho não tem para onde ir: o
  // rótulo some, e volta no hover. Melhor que ilegível por cima do núcleo.
  assert.equal(posicoes.get('vizinho').oculto, true);
});

test('o arranjo não depende da ordem em que os nós chegam', () => {
  const entrada = [rotulo('a', 0, 0, 120), rotulo('b', 0, 44, 120), rotulo('c', 90, 20, 120)];
  const direto = posicionarRotulos(entrada);
  const invertido = posicionarRotulos([...entrada].reverse());

  for (const [id, escolha] of direto) {
    assert.deepEqual(invertido.get(id), escolha, `${id} mudou de lugar`);
  }
});

test('em três dimensões os nós saem do plano, e o resultado segue determinístico', () => {
  const emTres = () => {
    const l = criarLayout(GRAFO.nos, GRAFO.arestas, { dimensoes: 3 });
    l.estabilizar();
    return l.posicoes();
  };

  const primeira = emTres();
  const segunda = emTres();

  const fora = [...primeira].filter(([id, p]) => id !== 'core' && Math.abs(p.z) > 1);
  assert.ok(fora.length > 0, 'alguém saiu do plano z=0');

  for (const [id, ponto] of primeira) {
    assert.ok(Number.isFinite(ponto.z), `${id} com z inválido`);
    assert.ok(Math.abs(ponto.z - segunda.get(id).z) < 1e-9, `${id} mudou de profundidade`);
  }
});

test('em duas dimensões nada sai do plano', () => {
  const layout = criarLayout(GRAFO.nos, GRAFO.arestas);
  layout.estabilizar();

  for (const [, ponto] of layout.posicoes()) assert.equal(ponto.z, 0);
});
