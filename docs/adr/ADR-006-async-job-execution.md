# ADR-006 — Execução assíncrona por jobs para operações longas

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O prompt (item 22) especifica endpoints como `POST /projects/{id}/docker/start`
no modelo síncrono de requisição e resposta. Isso não sobrevive ao contato com
a realidade:

| Operação | Duração observada |
|----------|-------------------|
| `docker compose up -d` com build | 30 s a 5 min |
| `docker compose up -d` com imagem em cache | 5 a 30 s |
| `docker compose down` | 5 a 20 s |
| varredura de disco em profundidade 3 | 10 a 120 s |
| `docker compose` no Windows, só a inicialização | 2 a 5 s |

Manter isso síncrono produz três problemas simultâneos: timeout do cliente,
requisição pendurada segurando worker, e ausência total de feedback — o usuário
clica em "Subir" e olha para uma tela parada por dois minutos, sem saber se
está funcionando.

É a lacuna mais séria da especificação original, e ela bloqueia o Módulo 5
inteiro.

## Decisão

Toda operação com duração potencialmente maior que 2 segundos vira **job
assíncrono**.

```
POST /api/projects/{id}/docker/up      -> 202 { "job_id": "j_8f21" }
GET  /api/jobs/j_8f21                  -> { status, output, exit_code }
GET  /api/jobs/j_8f21/stream           -> SSE do progresso
POST /api/jobs/j_8f21/cancel           -> cancela
```

Estados: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `TIMEOUT`, `CANCELLED`.

Características do `JobManager`:

- fila em memória, executando via `asyncio` com processo filho não bloqueante
- saída acumulada consultável **durante** a execução, não só ao final
- timeout por categoria de comando, herdado do `CommandSpec` (ADR-003)
- **exclusão mútua por chave** (`project_id` + tipo de operação): segundo
  pedido concorrente devolve `409 OPERATION_IN_PROGRESS` sem executar nada
  (FR-057)
- resultado final gravado em `activity_log`, que é persistente

Operações síncronas continuam síncronas: leitura de Git, `docker compose ps`,
detecção de stack, abrir VS Code. São rápidas e cacheáveis, e transformá-las em
job só adicionaria latência e complexidade na UI.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Manter síncrono com timeout alto** | segura worker, estoura no cliente, e não dá feedback de progresso. Não resolve nenhum dos três problemas |
| **Celery / RQ** | exigiria Redis ou broker: uma dependência de infraestrutura numa ferramenta local, pelo mesmo motivo que o ADR-002 recusou PostgreSQL no MVP |
| **`BackgroundTasks` do FastAPI** | dispara e esquece: sem estado consultável, sem saída incremental, sem cancelamento, sem exclusão mútua. Não atende FR-091 a FR-094 |
| **Só WebSocket, sem polling** | mais eficiente, porém uma dependência única frágil: proxy e antivírus locais no Windows interferem em conexões persistentes. SSE com fallback para polling é mais robusto |
| **Persistir estado do job no banco** | daria sobrevivência a restart, mas com custo de escrita a cada linha de saída. O resultado final já é persistido na auditoria; o processo em si morre com o servidor de qualquer forma |

## Consequências

Positivas:
- UI responsiva com progresso real: o console de job mostra a saída enquanto
  o Compose trabalha
- cancelamento possível
- exclusão mútua elimina a classe de bug de dois `up` simultâneos no mesmo
  projeto
- nenhuma dependência de infraestrutura nova

Negativas:
- a UI precisa lidar com estado assíncrono: mais complexidade no frontend, em
  `JobConsole`
- estado de job é volátil: reiniciar o servidor durante um `compose up` perde o
  acompanhamento, embora o comando em si já esteja com o Docker. Aceito e
  documentado como D-07
- SSE exige atenção com buffering e keep-alive

## Notas de implementação

- o processo filho é lido de forma não bloqueante; nada de `communicate()`
  síncrono dentro do event loop
- ao expirar o timeout, encerrar a **árvore** de processos, não só o filho
  direto — no Windows isso exige job object ou grupo de processo, e tem teste
  dedicado
- limite de tamanho da saída acumulada em memória (padrão 2 MB por job), com
  truncamento pelo início e marcação explícita
- jobs concluídos são mantidos em memória por tempo limitado (padrão 1 hora) e
  então descartados; a auditoria permanece
