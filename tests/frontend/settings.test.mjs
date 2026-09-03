// A seção "AI Providers" em Configurações: o estado que ela exibe, e a chave
// que ela não exibe (REQ-14, P-02, P-05).
//
// A varredura de chave acontece sobre a árvore renderizada — texto, atributo e
// `data-*` —, que é o que vira o HTML servido. Como o painel monta a tela no
// cliente, varrer o `.js` estático não provaria nada: o que precisa estar
// limpo é o que a página produz com a resposta da rota na mão.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { FakeNode, instalarDom } from './dom.mjs';

instalarDom();

const { providersSection, renderSettings } = await import(
  new URL('../../frontend/js/pages/settings.js', import.meta.url).href
);

//: A mesma chave plantada na suíte de integração das rotas. Se um pedaço dela
//: aparecer na tela, a varredura abaixo falha.
const CHAVE_DE_TESTE = 'sk-plantada-para-nunca-vazar-123456';
const CHAVE_ENV = 'DEVCOCKPIT_AI_KEY_TESTE';

function provider(extra = {}) {
  return {
    id: 'no-ar',
    type: 'cloud',
    enabled: true,
    base_url: 'http://127.0.0.1:9',
    api_key_env: CHAVE_ENV,
    estado: 'conectado',
    motivo: null,
    modelos: ['modelo-de-imitacao'],
    ...extra,
  };
}

/** O registro como a rota devolve, com os quatro estados. */
function registroCompleto() {
  return {
    ativo: true,
    erro: null,
    items: [
      provider(),
      provider({
        id: 'fora-do-ar',
        estado: 'indisponivel',
        motivo: 'Não respondeu em até 2,5s (ConnectError).',
      }),
      provider({
        id: 'sem-chave',
        estado: 'nao_configurado',
        api_key_env: 'DEVCOCKPIT_AI_KEY_QUE_NINGUEM_DEFINIU',
        motivo: null,
      }),
      provider({
        id: 'dormindo',
        type: 'local',
        enabled: false,
        api_key_env: '',
        estado: 'desligado',
        motivo: 'Desligado em configs/ai.yml (`enabled: false`).',
        modelos: [],
      }),
    ],
  };
}

/** Tudo que o nó rendeu: texto, valor de atributo e `data-*`.
 *
 * Atributo entra de propósito — `title` e `data-*` chegam ao HTML igual ao
 * texto, e um vazamento por ali seria tão vazamento quanto o outro.
 */
function tudoQueApareceu(no) {
  const pedacos = [];
  for (const filho of no.walk()) {
    if (filho.text) pedacos.push(filho.text);
    pedacos.push(...Object.values(filho.attrs));
    pedacos.push(...Object.values(filho.dataset));
  }
  return pedacos.join(' | ');
}

// --- os quatro estados ----------------------------------------------------

test('o estado exibido é o estado que o registro declarou', () => {
  const secao = providersSection(registroCompleto(), null);

  const exibidos = secao.findByClass('status-badge').map((no) => no.dataset.estado);

  assert.deepEqual(exibidos, ['conectado', 'indisponivel', 'nao_configurado', 'desligado']);
});

test('cada estado aparece por extenso, com acento e sem código', () => {
  const texto = providersSection(registroCompleto(), null).textContent;

  for (const rotulo of ['conectado', 'indisponível', 'não configurado', 'desligado']) {
    assert.ok(texto.includes(rotulo), `faltou o rótulo "${rotulo}"`);
  }
  assert.ok(!texto.includes('nao_configurado'), 'o código do estado não é rótulo de tela');
});

test('provider desligado continua na lista', () => {
  // Sumir com ele faria a tela fingir que nunca foi declarado — e quem
  // desligou no arquivo precisa ver que foi isso que aconteceu.
  const texto = providersSection(registroCompleto(), null).textContent;

  assert.ok(texto.includes('dormindo'));
  assert.ok(texto.includes('enabled: false'));
});

test('indisponível mostra o motivo que a rota deu', () => {
  const texto = providersSection(registroCompleto(), null).textContent;

  assert.ok(texto.includes('ConnectError'), 'indisponível sem motivo não explica nada');
});

test('não configurado diz qual variável falta, mesmo sem motivo na rota', () => {
  const registro = { ativo: true, items: [registroCompleto().items[2]] };

  const texto = providersSection(registro, null).textContent;

  assert.ok(texto.includes('DEVCOCKPIT_AI_KEY_QUE_NINGUEM_DEFINIU'));
  assert.ok(texto.includes('.env'), 'dizer o que falta sem dizer onde mexer não resolve');
});

// --- P-02: latência --------------------------------------------------------

test('quem não respondeu não tem latência: "não medido", nunca 0 ms', () => {
  const registro = { ativo: true, items: [provider({ estado: 'indisponivel' })] };
  const saude = { items: [{ id: 'no-ar', disponivel: false, latencia_ms: null }] };

  const texto = providersSection(registro, saude).textContent;

  assert.ok(texto.includes('não medido'));
  assert.ok(!texto.includes('0 ms'), 'zero inventado é pior que a ausência do número');
});

test('sem a rota de saúde, a latência fica não medida em vez de sumir', () => {
  const texto = providersSection({ ativo: true, items: [provider()] }, null).textContent;

  assert.ok(texto.includes('não medido'));
});

test('zero medido de verdade continua sendo zero', () => {
  // Provider local na mesma máquina responde em menos de 1 ms. Tratar isso
  // como ausência de medida seria o erro simétrico do P-02.
  const registro = { ativo: true, items: [provider({ id: 'ollama', type: 'local' })] };
  const saude = { items: [{ id: 'ollama', disponivel: true, latencia_ms: 0 }] };

  const texto = providersSection(registro, saude).textContent;

  assert.ok(texto.includes('0 ms'));
  assert.ok(!texto.includes('não medido'));
});

// --- P-05: a chave não aparece --------------------------------------------

test('a tela mostra o nome da variável e nada do valor', () => {
  const secao = providersSection(registroCompleto(), null);

  const tudo = tudoQueApareceu(secao);

  assert.ok(tudo.includes(CHAVE_ENV), 'o nome da variável é o que diz onde mexer');
  assert.ok(!tudo.includes(CHAVE_DE_TESTE));
});

test('chave vazada pela rota não é repassada para a tela', () => {
  // Adversarial: a rota atual não devolve isso, mas se um dia devolver, a tela
  // não pode ser o segundo furo. Só campo declarado é renderizado — nada aqui
  // despeja o objeto do provider.
  const registro = {
    ativo: true,
    items: [
      provider({
        api_key: CHAVE_DE_TESTE,
        token: CHAVE_DE_TESTE,
        api_key_masked: `${CHAVE_DE_TESTE.slice(0, 8)}…${CHAVE_DE_TESTE.slice(-4)}`,
      }),
    ],
  };

  const tudo = tudoQueApareceu(providersSection(registro, null));

  for (const pedaco of [
    CHAVE_DE_TESTE,
    CHAVE_DE_TESTE.slice(0, 8),
    CHAVE_DE_TESTE.slice(-8),
    CHAVE_DE_TESTE.slice(10, 22),
  ]) {
    assert.ok(!tudo.includes(pedaco), `a tela mostrou um pedaço da chave: ${pedaco}`);
  }
});

// --- registro ausente e rota fora do ar -----------------------------------

test('sem registro no disco, a seção diz o que fazer em vez de ficar vazia', () => {
  const texto = providersSection({ ativo: false, erro: null, items: [] }, null).textContent;

  assert.ok(texto.includes('configs/ai.yml'));
  assert.ok(texto.includes('sem IA'), 'o painel funciona sem IA, e a tela precisa dizer isso');
});

test('erro de carga do arquivo aparece nomeando o arquivo', () => {
  const registro = { ativo: false, erro: 'linha 4: mapping esperado', items: [] };

  const texto = providersSection(registro, null).textContent;

  assert.ok(texto.includes('configs/ai.yml'));
  assert.ok(texto.includes('linha 4'));
});

test('rota fora do ar vira estado exibido, não seção quebrada', () => {
  const texto = providersSection({ falha: 'Não foi possível falar com o servidor.' }, null)
    .textContent;

  assert.ok(texto.includes('Não foi possível falar com o servidor.'));
});

// --- a tela inteira --------------------------------------------------------

/** `fetch` de mentira, roteando por caminho. Sem rede e sem dependência. */
function instalarFetch(rotas) {
  globalThis.fetch = async (url) => {
    const caminho = String(url.pathname ?? url);
    if (!(caminho in rotas)) throw new Error(`rota não prevista no teste: ${caminho}`);
    return { ok: true, status: 200, json: async () => rotas[caminho] };
  };
}

test('Configurações abre com a seção de providers e sem nenhum rastro da chave', async () => {
  instalarFetch({
    '/api/health': {
      version: '0.0-teste',
      allowed_roots: ['C:/projetos'],
      tools: { git: true, docker: false, code: true },
    },
    '/api/servers': { items: [] },
    '/api/ai/providers': registroCompleto(),
    '/api/ai/health': {
      checked_at: '2026-09-03T10:00:00Z',
      timeout_s: 2.5,
      items: [
        { id: 'no-ar', type: 'cloud', disponivel: true, latencia_ms: 142, modelos: [] },
        { id: 'fora-do-ar', type: 'cloud', disponivel: false, latencia_ms: null, modelos: [] },
      ],
    },
  });
  const container = new FakeNode('div');

  await renderSettings(container);

  const tudo = tudoQueApareceu(container);
  assert.ok(tudo.includes('AI Providers'), 'a seção precisa estar na tela montada');
  assert.ok(tudo.includes('142 ms'), 'a latência medida aparece medida');
  assert.ok(!tudo.includes(CHAVE_DE_TESTE), 'a chave não pode chegar ao HTML da tela');
});

test('IA fora do ar não derruba o resto de Configurações', async () => {
  instalarFetch({
    '/api/health': {
      version: '0.0-teste',
      allowed_roots: ['C:/projetos'],
      tools: { git: true, docker: false, code: true },
    },
    '/api/servers': { items: [] },
  });
  const container = new FakeNode('div');

  await renderSettings(container);

  const texto = container.textContent;
  assert.ok(texto.includes('Diretórios permitidos'), 'o resto da tela continua de pé');
  assert.ok(texto.includes('AI Providers'));
});
