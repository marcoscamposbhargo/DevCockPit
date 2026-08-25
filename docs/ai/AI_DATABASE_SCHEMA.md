# Modelo de dados do Cockpit AI

> **Status: proposta.** Complementa `docs/05-data-model.md`.

Cinco tabelas novas e três colunas em uma existente. Todas as migrações são
aditivas: nenhuma tabela atual perde coluna, nenhum contrato de rota muda.

## Diagrama

```
project ──┬── ai_session ──── ai_message
          │
          ├── ai_memory
          │
          └── ai_task

activity_log  (+ actor, agent, reason)

ai_usage_day  (global, sem FK)
```

## `ai_session` — uma sessão de trabalho

```sql
CREATE TABLE ai_session (
  id            TEXT PRIMARY KEY,          -- s_ab12cd34
  project_id    TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  started_at    DATETIME NOT NULL,
  ended_at      DATETIME,                  -- NULL = em andamento
  objective     TEXT,                      -- confirmado pelo usuário
  summary       TEXT,                      -- montado de fatos no encerramento
  next_steps    TEXT,
  facts         TEXT,                      -- JSON: commits, arquivos, ações
  provider      TEXT,                      -- qual provedor atendeu
  tokens_in     INTEGER NOT NULL DEFAULT 0,
  tokens_out    INTEGER NOT NULL DEFAULT 0,
  cost_estimate REAL NOT NULL DEFAULT 0
);
CREATE INDEX ix_ai_session_project ON ai_session(project_id, started_at);
```

`facts` guarda o que foi **observado** durante a sessão: `git diff --stat` no
começo e no fim, ids de `activity_log`, quedas de serviço. É o que permite o
resumo ser montado de fato, e não redigido do nada.

Uma sessão aberta por projeto, no máximo. Abrir a segunda encerra a primeira —
sessão esquecida aberta por três dias mede nada.

## `ai_message` — o diálogo e o que ele custou

```sql
CREATE TABLE ai_message (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL REFERENCES ai_session(id) ON DELETE CASCADE,
  role          TEXT NOT NULL,             -- user | assistant | tool
  specialist    TEXT,                      -- perfil que respondeu
  content       TEXT NOT NULL,
  context_summary TEXT,                    -- que camadas entraram, não o conteúdo
  tokens_in     INTEGER,
  tokens_out    INTEGER,
  duration_ms   INTEGER,
  created_at    DATETIME NOT NULL
);
CREATE INDEX ix_ai_message_session ON ai_message(session_id, id);
```

`context_summary` e não o contexto inteiro: guardar tudo dobraria o banco e
duplicaria código de projeto dentro do SQLite do painel.

## `ai_memory` — a memória, num lugar só

```sql
CREATE TABLE ai_memory (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   TEXT REFERENCES project(id) ON DELETE CASCADE,  -- NULL = global
  kind         TEXT NOT NULL,   -- context|architecture|decision|bug|debt|
                                -- discovery|next_step|preference|pattern|command
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  source       TEXT NOT NULL,   -- observed | human | ai_suggested
  confirmed_at DATETIME,        -- NULL em sugestão não confirmada
  session_id   TEXT REFERENCES ai_session(id) ON DELETE SET NULL,
  relevance    INTEGER NOT NULL DEFAULT 0,  -- quantas vezes entrou em contexto
  created_at   DATETIME NOT NULL,
  updated_at   DATETIME NOT NULL
);
CREATE INDEX ix_ai_memory_project_kind ON ai_memory(project_id, kind);
```

`project_id` nulo é a **memória global do desenvolvedor** — mesma tabela,
mesmo formato, sem projeto. Duas tabelas idênticas com nomes diferentes seriam
duas migrações e dois repositórios para o mesmo comportamento.

`source` é o campo que impede memória virar ficção:
`observed` (o painel mediu), `human` (o usuário escreveu ou confirmou),
`ai_suggested` (o modelo propôs e ninguém confirmou ainda). A interface mostra
os três de forma diferente.

## `ai_task` — o que falta fazer

```sql
CREATE TABLE ai_task (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  detail       TEXT,
  status       TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN|DOING|DONE|DROPPED
  priority     INTEGER NOT NULL DEFAULT 2,     -- 1 alta, 2 média, 3 baixa
  source       TEXT NOT NULL,                  -- human | ai_suggested
  session_id   TEXT REFERENCES ai_session(id) ON DELETE SET NULL,
  created_at   DATETIME NOT NULL,
  done_at      DATETIME
);
CREATE INDEX ix_ai_task_project_status ON ai_task(project_id, status, priority);
```

Esta é a peça que **hoje não existe no produto** e sem a qual "próxima tarefa"
não tem de onde sair. Deliberadamente mínima: sem sprint, sem estimativa, sem
responsável — é um painel de um desenvolvedor só, e um Jira embutido seria a
forma mais rápida de ninguém usar.

## `ai_usage_day` — gasto por dia

```sql
CREATE TABLE ai_usage_day (
  day          TEXT PRIMARY KEY,    -- 2026-08-24 (local)
  tokens_in    INTEGER NOT NULL DEFAULT 0,
  tokens_out   INTEGER NOT NULL DEFAULT 0,
  cost_estimate REAL NOT NULL DEFAULT 0,
  calls        INTEGER NOT NULL DEFAULT 0
);
```

Serve ao teto diário e à tela de custo. Uma linha por dia é barato e responde
"quanto gastei esta semana?" sem varrer mensagens.

## Alterações em tabela existente

```sql
ALTER TABLE activity_log ADD COLUMN actor  TEXT NOT NULL DEFAULT 'user';
ALTER TABLE activity_log ADD COLUMN agent  TEXT;      -- perfil, quando actor='ai'
ALTER TABLE activity_log ADD COLUMN reason TEXT;      -- por que a IA propôs
```

Com isso, "o que o agente fez ontem?" é filtro na tela de Atividade que já
existe. `DEFAULT 'user'` mantém todo o histórico atual válido.

## Configuração nova (`Settings`)

```
DEVCOCKPIT_AI_ENABLED                bool, padrão false
DEVCOCKPIT_AI_PROVIDER               anthropic | openai | local | none
DEVCOCKPIT_AI_MODEL                  string
DEVCOCKPIT_AI_API_KEY                nunca gravada em banco (D-A5)
DEVCOCKPIT_AI_MAX_CONTEXT_TOKENS     12000
DEVCOCKPIT_AI_MAX_OUTPUT_TOKENS      2000
DEVCOCKPIT_AI_DAILY_TOKEN_BUDGET     200000
DEVCOCKPIT_AI_MAX_TOOL_CALLS         8
DEVCOCKPIT_AI_SESSION_RETENTION_DAYS 180
```

E uma coluna em `project`:

```sql
ALTER TABLE project ADD COLUMN ai_enabled BOOLEAN NOT NULL DEFAULT 1;
```

Projeto com `ai_enabled = 0` nunca tem conteúdo enviado a provedor nenhum
(defesa D-A1).

## Migrações

Uma migração por fase, na ordem do plano de implementação:

| Revisão | Conteúdo | Fase |
|---------|----------|------|
| `006_ai_session` | `ai_session`, `ai_message`, colunas de `activity_log` | 1 |
| `007_ai_memory` | `ai_memory`, `project.ai_enabled` | 1 |
| `008_ai_task` | `ai_task` | 2 |
| `009_ai_usage` | `ai_usage_day` | 2 |

Todas aditivas, todas reversíveis, no mesmo Alembic de hoje.
