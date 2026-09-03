// Tela de consumo de IA (T-13, REQ-12).
//
// A regra que este arquivo prova é P-02: nenhum indicador sem dado pode
// aparecer como zero. Banco vazio devolve `medido: false` da rota, e a tela
// mostra o motivo, não uma tabela de zeros. Com dados, cada indicador
// anulável (custo, price_date, latência, local×cloud) é testado isolado,
// porque a rota permite qualquer combinação: dado no todo e `null` numa
// parte só.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { FakeNode, instalarDom } from './dom.mjs';

instalarDom();

const { usageBody, renderAiUsage } = await import(
  new URL('../../frontend/js/pages/ai-usage.js', import.meta.url).href
);

/** Indicadores completos, como a rota devolve com dados no período. */
function indicadoresCompletos(extra = {}) {
  return {
    chamadas: 42,
    perguntas: 30,
    tokens_in: 12000,
    tokens_out: 8000,
    chamadas_local: 10,
    tokens_local: 4000,
    chamadas_cloud: 32,
    tokens_cloud: 16000,
    custo_estimado: 0.1234,
    price_date: '2026-08-20',
    chamadas_sem_custo: 0,
    latencia_media_ms: 842.5,
    falhas: 2,
    fallbacks: 1,
    ...extra,
  };
}

function usageOut(extra = {}) {
  return {
    since: '2026-08-27T00:00:00Z',
    until: '2026-09-03T00:00:00Z',
    days: 7,
    medido: true,
    motivo: null,
    indicadores: indicadoresCompletos(),
    ...extra,
  };
}

// --- P-02: banco vazio, período sem execução ------------------------------

test('medido: false mostra o motivo da rota, nunca uma tabela de zeros', () => {
  const resposta = {
    since: '2026-08-27T00:00:00Z',
    until: '2026-09-03T00:00:00Z',
    days: 7,
    medido: false,
    motivo: 'Nenhuma execução de IA registrada nos últimos 7 dias. Os indicadores aparecem depois da primeira pergunta respondida.',
    indicadores: {
      chamadas: null,
      perguntas: null,
      tokens_in: null,
      tokens_out: null,
      chamadas_local: null,
      tokens_local: null,
      chamadas_cloud: null,
      tokens_cloud: null,
      custo_estimado: null,
      price_date: null,
      chamadas_sem_custo: null,
      latencia_media_ms: null,
      falhas: null,
      fallbacks: null,
    },
  };

  const texto = usageBody(resposta).textContent;

  assert.ok(texto.includes('Nenhuma execução de IA registrada'));
  assert.ok(!/\b0\b/.test(texto), 'nenhum zero pode aparecer com o período inteiro não medido');
});

test('registro inativo (sem configs/ai.yml) mostra o motivo específico', () => {
  const resposta = {
    since: '2026-08-27T00:00:00Z',
    until: '2026-09-03T00:00:00Z',
    days: 7,
    medido: false,
    motivo:
      'A IA não tem registro utilizável (configs/ai.yml): nenhuma execução pode ser ' +
      'registrada até um provider estar declarado e habilitado.',
    indicadores: {},
  };

  const texto = usageBody(resposta).textContent;

  assert.ok(texto.includes('configs/ai.yml'));
});

// --- com dados: os campos da rota aparecem --------------------------------

test('com dados, chamadas, perguntas e tokens aparecem', () => {
  const texto = usageBody(usageOut()).textContent;

  assert.ok(texto.includes('42'), 'chamadas');
  assert.ok(texto.includes('30'), 'perguntas');
  assert.ok(texto.includes('12000'), 'tokens de entrada');
  assert.ok(texto.includes('8000'), 'tokens de saída');
});

test('local × nuvem aparece quando o registro classifica os dois lados', () => {
  const texto = usageBody(usageOut()).textContent;

  assert.ok(texto.includes('10'), 'chamadas locais');
  assert.ok(texto.includes('32'), 'chamadas em nuvem');
});

test('sem classificação local×nuvem, a seção diz não medido em vez de mostrar zero', () => {
  const dados = usageOut({
    indicadores: indicadoresCompletos({ chamadas_local: null, chamadas_cloud: null }),
  });

  const texto = usageBody(dados).textContent;

  assert.ok(texto.includes('não medido'));
});

// --- P-02: custo sempre com a data da tabela de preço ---------------------

test('custo aparece com a data da tabela de preço ao lado', () => {
  const texto = usageBody(usageOut()).textContent;

  assert.ok(texto.includes('0.1234') || texto.includes('0,1234'), 'valor do custo');
  assert.ok(texto.includes('2026-08-20'), 'a data do preço precisa estar junto do custo');
});

test('custo nulo (nenhum modelo com preço no período) vira não medido, não US$ 0', () => {
  const dados = usageOut({
    indicadores: indicadoresCompletos({ custo_estimado: null, price_date: null }),
  });

  const texto = usageBody(dados).textContent;

  assert.ok(texto.includes('não medido'));
  assert.ok(!texto.includes('US$ 0'), 'custo não calculado não é custo zero');
});

test('chamadas_sem_custo > 0 aparece como aviso visível perto do custo total', () => {
  const dados = usageOut({
    indicadores: indicadoresCompletos({ chamadas_sem_custo: 5 }),
  });

  const bloco = usageBody(dados);
  const texto = bloco.textContent;

  assert.ok(texto.includes('5'), 'a contagem de chamadas sem custo aparece');
  assert.ok(texto.toLowerCase().includes('parcial'), 'o total precisa ser rotulado como parcial');
});

test('chamadas_sem_custo igual a zero não gera aviso de parcial', () => {
  const dados = usageOut({ indicadores: indicadoresCompletos({ chamadas_sem_custo: 0 }) });

  const texto = usageBody(dados).textContent.toLowerCase();

  assert.ok(!texto.includes('parcial'));
});

// --- P-02: latência, falhas e fallbacks anuláveis isoladamente ------------

test('latência nula vira não medido, nunca 0 ms', () => {
  const dados = usageOut({ indicadores: indicadoresCompletos({ latencia_media_ms: null }) });

  const texto = usageBody(dados).textContent;

  assert.ok(texto.includes('não medido'));
  assert.ok(!texto.includes('0 ms'));
});

test('latência zero medida de verdade continua sendo zero', () => {
  const dados = usageOut({ indicadores: indicadoresCompletos({ latencia_media_ms: 0 }) });

  const texto = usageBody(dados).textContent;

  assert.ok(texto.includes('0 ms'));
});

test('falhas nulo não aparece como zero', () => {
  const dados = usageOut({ indicadores: indicadoresCompletos({ falhas: null }) });

  const texto = usageBody(dados).textContent;

  assert.ok(texto.includes('não medido'));
});

test('fallbacks é rotulado como "pergunta com mais de uma tentativa", não tentativa extra', () => {
  const texto = usageBody(usageOut()).textContent;

  assert.ok(texto.includes('Fallbacks'));
  // O título/hint precisa carregar a definição correta em algum nó da árvore.
  const node = usageBody(usageOut());
  const achados = [...node.walk()].map((n) => n.attrs.title).filter(Boolean);
  assert.ok(
    achados.some((t) => t.includes('mais de uma tentativa')),
    'a definição de fallback precisa estar explícita, não é "tentativa extra"'
  );
});

// --- a tela inteira: banco vazio nunca mostra zero falso -------------------

function instalarFetch(rotas) {
  globalThis.fetch = async (url) => {
    const caminho = String(url.pathname ?? url);
    if (!(caminho in rotas)) throw new Error(`rota não prevista no teste: ${caminho}`);
    return { ok: true, status: 200, json: async () => rotas[caminho] };
  };
}

test('a tela abre com banco vazio sem mostrar nenhum zero falso', async () => {
  instalarFetch({
    '/api/ai/usage': {
      since: '2026-08-27T00:00:00Z',
      until: '2026-09-03T00:00:00Z',
      days: 7,
      medido: false,
      motivo: 'Nenhuma execução de IA registrada nos últimos 7 dias. Os indicadores aparecem depois da primeira pergunta respondida.',
      indicadores: {},
    },
  });
  const container = new FakeNode('div');

  await renderAiUsage(container);

  const texto = container.textContent;
  assert.ok(texto.includes('Consumo de IA'));
  assert.ok(texto.includes('Nenhuma execução de IA registrada'));
  assert.ok(!/\b0\b/.test(texto), 'banco vazio não pode produzir nenhum zero na tela');
});

test('a tela abre com dados e mostra os campos da rota', async () => {
  instalarFetch({ '/api/ai/usage': usageOut() });
  const container = new FakeNode('div');

  await renderAiUsage(container);

  const texto = container.textContent;
  assert.ok(texto.includes('42'), 'chamadas');
  assert.ok(texto.includes('2026-08-20'), 'data do preço');
  assert.ok(texto.includes('Fallbacks'));
});

test('rota fora do ar vira mensagem de erro, não tela quebrada', async () => {
  globalThis.fetch = async () => {
    throw new Error('recusado');
  };
  const container = new FakeNode('div');

  await renderAiUsage(container);

  assert.ok(container.textContent.includes('Consumo de IA'));
});
