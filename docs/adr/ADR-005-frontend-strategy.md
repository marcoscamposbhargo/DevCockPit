# ADR-005 — Frontend sem framework e sem etapa de build

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O prompt pede HTML, CSS e JavaScript, evitando frameworks inicialmente, com
foco em simplicidade, baixo acoplamento e aprendizado.

A interface real do MVP tem 8 telas, atualização periódica de dados, streams
SSE de log e de progresso de job, e uma tabela densa de containers. Não é
trivial, mas também não tem formulários complexos nem estado compartilhado
profundo — a maior parte é renderizar JSON vindo da API.

## Decisão

Frontend em **ES modules servidos direto pelo FastAPI, sem etapa de build, sem
dependência externa e sem framework**.

Estrutura:

| Peça | Responsabilidade |
|------|------------------|
| `main.js` | inicializa e monta o shell |
| `router.js` | roteamento por hash, sobrevive a recarregar |
| `lib/api.js` | `fetch` com cabeçalho de cliente e tradução de erro de domínio |
| `lib/store.js` | estado observável mínimo, sem reatividade mágica |
| `lib/dom.js` | criação de elemento por função, sem template string de HTML |
| `lib/format.js` | tempo relativo, bytes, uptime |
| `pages/*.js` | uma página por arquivo, exportando `render(container, params)` |

CSS em quatro arquivos: `tokens.css`, `base.css`, `components.css`,
`layout.css`. Todas as cores como custom properties (`11-ui-ux-spec.md`).

Regra rígida: **`innerHTML` nunca recebe dado vindo da API**. Nome de branch,
mensagem de commit, path e log de container são conteúdo não confiável — XSS
aqui é real, e a página tem acesso à API que executa comandos.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **React / Vue / Svelte** | traria bundler, `node_modules` e etapa de build para uma UI de 8 telas; contraria o pedido do prompt e o objetivo de aprendizado. Ironia relevante: a ferramenta existe para simplificar ambiente de dev, e começaria adicionando uma toolchain |
| **Alpine.js ou htmx via CDN** | CDN é dependência de rede numa ferramenta que precisa funcionar offline; e htmx moveria a renderização para o servidor, misturando responsabilidade de template com a API |
| **Web Components** | encapsulamento é bom, mas o custo de boilerplate e as pegadinhas de estilo em Shadow DOM não se pagam nesta escala |
| **Renderização server-side com Jinja** | perderia a API limpa que também serve a testes de contrato e a um eventual cliente diferente |

## Consequências

Positivas:
- editar arquivo e recarregar: sem build, sem watcher, sem cache de bundler
- zero dependência de frontend para auditar ou atualizar
- API permanece o único contrato, testável de forma independente
- alinhado ao objetivo de estudo: o que acontece na tela é visível no código

Negativas:
- atualização de DOM é manual; listas grandes exigem cuidado para não recriar
  tudo a cada refresh. Mitigação: renderizar por chave e substituir só a linha
  alterada
- sem sistema de tipos no frontend; erro de nome de campo só aparece em runtime.
  Mitigação: `lib/api.js` centraliza o acesso e normaliza a resposta
- sem componentes reativos, repetição é um risco. Mitigação: `lib/dom.js` e
  componentes como função pura de renderização

## Gatilhos para revisar esta decisão

Esta decisão deve ser reaberta se ocorrer qualquer um destes:

1. o frontend passar de ~3000 linhas
2. surgir formulário com validação cruzada complexa
3. aparecer necessidade de estado compartilhado entre mais de três telas
4. o tempo de renderização com 50 projetos ficar perceptível

Nenhum é esperado dentro do MVP.
