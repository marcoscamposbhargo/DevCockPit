// O que o dashboard escolhe mostrar, e o que ele afirma ao mostrar.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { instalarDom } from './dom.mjs';

instalarDom();

const { portasRelevantes } = await import(
  new URL('../../frontend/js/pages/dashboard.js', import.meta.url).href
);
const { stackedColumns, hourStrip } = await import(
  new URL('../../frontend/js/lib/charts.js', import.meta.url).href
);

function porta(numero, { conflict = false } = {}) {
  return { port: numero, projects: ['x'], conflict };
}

test('o dashboard mostra no máximo sete portas', () => {
  const portas = Array.from({ length: 24 }, (_, i) => porta(3000 + i));

  assert.equal(portasRelevantes(portas, new Map()).length, 7);
});

test('conflito vem primeiro, depois o que está no ar', () => {
  const portas = [porta(3000), porta(3001), porta(3002, { conflict: true }), porta(3003)];
  const noAr = new Map([
    [3003, { forte: true, texto: 'no ar' }],
    [3001, { forte: false, texto: 'ocupada' }],
  ]);

  const ordem = portasRelevantes(portas, noAr).map((item) => item.port);

  assert.deepEqual(ordem, [3002, 3003, 3001, 3000]);
});

test('nada é omitido quando cabe tudo', () => {
  const portas = [porta(3000), porta(3001)];

  assert.equal(portasRelevantes(portas, new Map()).length, 2);
});

// --- gráficos -------------------------------------------------------------

test('a faixa de horas tem uma célula por hora do dia', () => {
  const faixa = hourStrip(Array.from({ length: 24 }, (_, i) => i));

  assert.equal(faixa.children.length, 24);
});

test('coluna de dia vazio continua na grade', () => {
  const colunas = [
    { label: '01/08', total: 0, partes: [{ kind: 'success', valor: 0, rotulo: 'sucesso' }] },
    { label: '02/08', total: 4, partes: [{ kind: 'success', valor: 4, rotulo: 'sucesso' }] },
  ];

  const grafico = stackedColumns(colunas);
  const plot = grafico.findByClass('cols__plot')[0];

  assert.equal(plot.children.length, 2, 'dia parado não pode sumir do eixo');
});
