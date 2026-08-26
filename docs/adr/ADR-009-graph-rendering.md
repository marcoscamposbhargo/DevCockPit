# ADR-009 — Grafo do HyperBrain em SVG, sem biblioteca

- **Status:** Aceito
- **Data:** 2026-08-25
- **Fase:** HyperBrain, MVP 1
- **Origem:** proposta técnica em `docs/ai/HYPERBRAIN.md`

## Contexto

O HyperBrain desenha o ecossistema de projetos como grafo: núcleo, projetos e
as tecnologias que ligam projetos, com zoom, deslocamento, arraste, foco e
painel contextual.

Grafo interativo é exatamente o tipo de tela para a qual existe biblioteca
pronta — React Flow, Cytoscape.js, Sigma.js, D3, e a rota do WebGL com
Three.js. A pergunta não era se elas resolvem, e sim se o que elas resolvem é
um problema que este projeto tem.

Duas restrições já estavam postas:

- o ADR-005 fixa frontend em ES modules servidos direto pelo FastAPI, **sem
  build, sem `node_modules`, sem dependência**;
- o painel roda empacotado como executável e precisa funcionar offline, o que
  elimina CDN.

Faltava o dado do meio: **quantos nós**. Com os 19 projetos cadastrados nesta
máquina, o grafo tem 31 nós e 72 arestas. Com o ecossistema expandido nas fases
seguintes (tarefas, sessões, decisões, serviços de um projeto em foco), a
estimativa é de 60 a 200.

## Decisão

**SVG desenhado à mão, com simulação de força própria.** Nenhuma biblioteca,
nenhum WebGL, nenhum canvas.

| Peça | Arquivo |
|------|---------|
| dado do painel → nós e arestas | `frontend/js/lib/graph/adapter.js` |
| simulação de força (sem DOM) | `frontend/js/lib/graph/layout.js` |
| nós e arestas → SVG | `frontend/js/lib/graph/render.js` |
| zoom, deslocamento, arraste, teclado | `frontend/js/lib/graph/interaction.js` |
| núcleo e seus estados | `frontend/js/lib/graph/core.js` |
| estado visual efêmero | `frontend/js/lib/graph/state.js` |

`layout.js` não conhece DOM e `render.js` não conhece `fetch` — é o que permite
testar a simulação no runner do Node, sem navegador e sem dublê.

## O que sustenta a decisão

Custo de um passo da simulação, medido no Chromium, no grafo real e em grafos
sintéticos:

| Nós | ms por passo | Passos até estabilizar |
|-----|--------------|------------------------|
| 31 (real) | 0,011 | 85 |
| 50 | 0,035 | 85 |
| 100 | 0,039 | 85 |
| 200 | 0,156 | 85 |
| 400 | 0,576 | 85 |

O orçamento de um quadro a 60 fps é 16,7 ms. Com 400 nós — o dobro do teto
previsto para as fases seguintes — a simulação usa **3,5% desse orçamento**. A
repulsão é O(n²) e assumida como tal: o quadtree que a tornaria O(n log n)
custaria ~150 linhas para resolver um problema que não existe nesta escala.

Na tela, com o grafo real: estabiliza em **0,96 s**, ~65 quadros no primeiro
segundo, e **zero** quadros pedidos depois de estabilizar — a simulação encerra
o laço em vez de girar em vazio.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **React Flow** | exige React, bundler e `node_modules`. Contraria o ADR-005 inteiro, para uma tela |
| **Cytoscape.js, Sigma.js, D3** | por npm, trazem build; por CDN, quebram o uso offline do executável |
| **Three.js / WebGL** | passa a se justificar por volta de 2000 nós. Aqui o pico previsto é 200, e a medição acima mostra folga de duas ordens de grandeza |
| **`d3-force` vendorizado local** | tecnicamente legítimo e sem build. Recusado por proporção: ~30 KB e uma dependência a auditar e atualizar para substituir 130 linhas que o projeto entende inteiras |
| **Canvas 2D** | perderia o que o SVG dá de graça: cores vindas das variáveis do CSS (o mesmo motivo registrado em `charts.js`), foco de teclado por elemento e `aria-label` por nó. Num canvas, acessibilidade e tema viram trabalho manual |

## Consequências

Positivas:
- zero dependência nova; o painel segue auditável e offline
- trocar de tema não redesenha nada: as cores saem de `tokens.css`
- cada nó é um elemento real — `Tab` alcança, leitor de tela anuncia
- `layout.js` é testável sem navegador; 14 testes cobrem determinismo,
  convergência, nó preso e aresta órfã

Negativas:
- a simulação é nossa: comportamento estranho é bug nosso, não issue de
  terceiro. Mitigação: os parâmetros estão nomeados e comentados no topo do
  arquivo, e a suíte prova convergência
- sem rótulo com desvio de colisão. Mitigação parcial: repulsão proporcional ao
  peso do nó e corte de rótulo longo em 18 caracteres, com o nome inteiro no
  `aria-label` e no painel lateral
- acima de ~1000 nós esta escolha deixa de servir

## Gatilhos para revisar

1. o grafo passar de 1000 nós na tela
2. a simulação aparecer em medição de CPU acima de 5% depois de estabilizar
3. surgir necessidade de rótulo sem sobreposição garantida (algoritmo de
   colisão de verdade)
4. o layout precisar de algo que a força simples não dá — hierarquia, camadas,
   agrupamento por cluster
