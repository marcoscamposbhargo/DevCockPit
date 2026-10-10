# 06 — Especificação da API

Base: `http://127.0.0.1:8765/api`
Formato: JSON. Toda data em ISO 8601 UTC.

Este documento é **especificação**, não implementação. Nenhum endpoint está
implementado na Fase 0.

## Convenções

- `GET` é sempre leitura, idempotente, cacheável.
- Operação longa devolve `202 Accepted` com `job_id`. Nunca bloqueia.
- Requisição que altera estado exige o cabeçalho `X-DevCockpit-Client: web`
  (NFR-006).
- Erro segue formato único:

```json
{
  "error": {
    "code": "PATH_NOT_ALLOWED",
    "message": "O diretório não está em um root permitido.",
    "correlation_id": "c7f2a1e0"
  }
}
```

### Códigos de erro de domínio

| `code` | HTTP | Significado |
|--------|------|-------------|
| `VALIDATION_ERROR` | 422 | payload inválido |
| `PROJECT_NOT_FOUND` | 404 | id inexistente |
| `PROJECT_ALREADY_EXISTS` | 409 | path já cadastrado |
| `PATH_NOT_FOUND` | 400 | diretório não existe |
| `PATH_NOT_ALLOWED` | 403 | fora dos roots permitidos |
| `PROJECT_DIR_MISSING` | 409 | projeto cadastrado sem diretório no disco |
| `NOT_A_GIT_REPO` | 409 | operação Git em diretório sem repo |
| `DOCKER_UNAVAILABLE` | 503 | daemon não responde |
| `NO_COMPOSE_FILE` | 409 | projeto sem arquivo Compose |
| `OPERATION_IN_PROGRESS` | 409 | já existe job para a mesma chave (FR-057) |
| `TOOL_NOT_FOUND` | 503 | `git`, `docker` ou `code` fora do PATH |
| `ACTION_NOT_ALLOWED` | 403 | ação fora da allowlist — registra `DENIED` |
| `COMMAND_TIMEOUT` | 504 | comando excedeu o timeout |

## Projetos

### `GET /api/projects`
Query: `status`, `tech`, `has_docker`, `pinned`, `q`, `limit`, `offset`.

```json
{
  "items": [{
    "id": "dashboard-contabil",
    "name": "Dashboard Contábil",
    "path": "C:/Users/User/Projetos/dashboard-contabil",
    "status": "RUNNING",
    "is_pinned": true,
    "technologies": ["python", "fastapi", "postgresql", "docker"],
    "git": { "is_repo": true, "current_branch": "main", "dirty_count": 3 },
    "docker": { "enabled": true, "running_containers": 3 },
    "services_online": 2,
    "services_total": 3,
    "last_accessed_at": "2026-08-21T18:04:11Z"
  }],
  "total": 27
}
```

### `POST /api/projects`

```json
{
  "path": "C:/Users/User/Projetos/dashboard-contabil",
  "name": "Dashboard Contábil",
  "run_detection": true
}
```

`201` com o projeto criado. `name` ausente vira o nome da pasta.
Erros: `PATH_NOT_FOUND`, `PATH_NOT_ALLOWED`, `PROJECT_ALREADY_EXISTS`.

### `GET /api/projects/{id}`
Projeto completo: tecnologias, serviços, git, docker, health mais recente.
Atualiza `last_accessed_at`.

### `PATCH /api/projects/{id}`
Campos editáveis: `name`, `description`, `is_pinned`, `detection_locked`,
`docker.compose_file`, `docker.enabled`.
`path` **não** é editável — mudar o diretório é remover e cadastrar de novo,
para preservar a unicidade e a auditoria.

### `DELETE /api/projects/{id}`
`204`. Remove só o registro. Nunca toca em arquivo do disco.

### `POST /api/projects/{id}/detect`
Reexecuta a detecção (FR-025). Respeita `detection_locked`. Síncrono
(leitura de marcadores é rápida). Devolve o diff do que mudou.

## Descoberta

### `POST /api/discovery/scan`

```json
{ "root": "C:/Users/User/Desktop", "max_depth": 3 }
```

`202 {"job_id": "j_89d7a5e3", "action": "discovery.scan", "status": "PENDING"}`.

A raiz é validada **antes** de enfileirar: `PATH_NOT_ALLOWED` volta na hora,
com 403, e nenhum job é criado. Erro de allowlist escondido dentro de um job
que falha depois seria péssima experiência.

Duas varreduras simultâneas: a segunda recebe `409 OPERATION_IN_PROGRESS`.

### `GET /api/discovery/candidates?root=...`

Resultado da última varredura concluída daquela raiz. A chave é o path
resolvido, então caixa diferente ou barra final não mudam o resultado.

```json
{
  "items": [{
    "path": "C:/Users/User/Desktop/Projetos/zapbot",
    "suggested_name": "zapbot",
    "technologies": ["python", "fastapi", "docker"],
    "is_git_repo": true,
    "already_registered": false
  }]
}
```

### `POST /api/discovery/import`
`{"paths": ["...", "..."]}` → cadastra em lote (FR-010).

## Git — somente leitura

| Endpoint | Retorna |
|----------|---------|
| `GET /api/projects/{id}/git/status` | branch, contagens, arquivos alterados (limitado), ahead/behind |
| `GET /api/projects/{id}/git/commits?limit=20` | histórico recente |
| `GET /api/projects/{id}/git/branches` | branches locais |
| `GET /api/projects/{id}/git/remotes` | remotes e URLs |

```json
{
  "is_repo": true,
  "repo_root": "C:/Users/User/Desktop/Projetos/dashboard-contabil",
  "inside_other_repo": false,
  "current_branch": "main",
  "detached": false,
  "ahead": 2, "behind": 0,
  "counts": { "modified": 3, "added": 1, "deleted": 0, "staged": 0, "untracked": 4 },
  "files": [{ "path": "app/main.py", "change": "modified", "staged": false }],
  "files_truncated": true,
  "last_commit": {
    "sha": "a60ec19",
    "author": "Marcos",
    "date": "2026-08-21T14:02:00Z",
    "subject": "feat: novo módulo de indicadores"
  },
  "checked_at": "2026-08-21T18:10:02Z"
}
```

`is_repo` é `true` apenas quando o diretório é a **raiz** do repositório.
Quando ele está dentro de um repositório cuja raiz é outra, a resposta traz
`is_repo: false`, `inside_other_repo: true` e `repo_root` com a raiz — e nenhum
`git status` chega a ser executado. O motivo está no ADR-008.

Não existe endpoint de escrita Git no MVP. Isso é decisão de segurança
(FR-038), não omissão.

## Docker

### `GET /api/projects/{id}/docker/status`

```json
{
  "available": true,
  "compose_file": "docker-compose.yml",
  "detail": null,
  "running_count": 1,
  "declared_services": ["backend", "db"],
  "containers": [{
    "name": "dashboard-contabil-backend-1",
    "service": "backend",
    "state": "running",
    "health": "healthy",
    "image": "dashboard-contabil-backend",
    "status": "Up 3 hours (healthy)",
    "exit_code": 0,
    "ports": [{ "host_port": 8000, "container_port": 8000, "protocol": "tcp" }]
  }]
}
```

`status` é o texto do Docker, não segundos: "Up 3 hours" é formato humano que
varia por locale, e convertê-lo seria inventar precisão (D-30).

`declared_services` são os serviços do arquivo Compose. A UI usa essa lista
para oferecer ação por serviço — e é contra ela que a API valida qualquer nome
recebido do cliente.

Daemon fora do ar: `200` com `available: false` e `detail`, **não** erro
(NFR-060). `503 DOCKER_UNAVAILABLE` só nas rotas de ação.

### Ações — todas assíncronas

| Endpoint | Comando |
|----------|---------|
| `POST /api/projects/{id}/docker/up` | `docker compose up -d` |
| `POST /api/projects/{id}/docker/down` | `docker compose down` |
| `POST /api/projects/{id}/docker/start` | `docker compose start` |
| `POST /api/projects/{id}/docker/stop` | `docker compose stop` |
| `POST /api/projects/{id}/docker/restart` | `docker compose restart` |

`202 {"job_id": "..."}`. Segundo pedido concorrente na mesma chave:
`409 OPERATION_IN_PROGRESS`.

Body opcional: `{"services": ["backend"]}` — apenas nomes de serviço que
existam no Compose do projeto. Nome desconhecido é `422`, jamais repassado ao
comando.

### Logs

- `GET /api/projects/{id}/docker/logs?service=backend&tail=200` → últimas
  linhas, JSON.
- `GET /api/projects/{id}/docker/logs/stream?service=backend` → SSE
  (`text/event-stream`), eventos `log` e `end` (FR-055).

## Serviços e health

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/projects/{id}/services` | serviços do projeto com último estado |
| `PUT /api/projects/{id}/services` | substitui a lista de serviços |
| `POST /api/projects/{id}/services/check` | força reverificação (FR-063) |
| `GET /api/services/ports` | mapa porta → projeto/serviço, com conflitos |

```json
{
  "items": [{
    "key": "backend", "label": "Backend",
    "url": "http://localhost:8000", "port": 8000,
    "state": "ONLINE", "latency_ms": 12,
    "checked_at": "2026-08-21T18:12:00Z"
  }]
}
```

`GET /api/services/ports` devolve duas leituras da mesma coisa:

```json
{
  "items": [{ "port": 8000, "projects": ["Dashdate", "DevCockpit"], "conflict": true }],
  "bindings": [{
    "port": 8000, "project_id": "dashdate", "project_name": "Dashdate",
    "service_key": "backend", "service_label": "Backend",
    "host": "localhost", "url": "http://localhost:8000", "conflict": true
  }],
  "conflicts": 1
}
```

`items` responde "esta porta está em conflito?". `bindings` diz **quem** ocupa
cada uma, com o id do projeto e a chave do serviço — sem isso a tela de portas
teria que buscar cada projeto só para descobrir de quem é a porta antes de
poder trocá-la. `conflict` conta por serviço, não por nome de projeto (D-56).

Trocar a porta é `PUT /api/projects/{id}/services` com a lista **inteira**: não
há PATCH de serviço solto, e a substituição em bloco é o que mantém a lista
consistente com o manifesto.

## Ações de sistema

| Endpoint | Ação |
|----------|------|
| `POST /api/projects/{id}/open/vscode` | abre no VS Code |
| `POST /api/projects/{id}/open/folder` | abre no explorador |
| `POST /api/projects/{id}/open/terminal` | abre terminal no diretório |
| `POST /api/projects/{id}/open/browser` | abre URL de um serviço |

`open/browser` recebe `{"service_key": "frontend"}` — **a chave do serviço,
nunca a URL**. A URL é resolvida no backend a partir do registro. Aceitar URL
do cliente reabriria a porta que o modelo de segurança fecha.

Resposta `200 {"opened": true, "action": "system.vscode"}`.
`code` fora do PATH: `503 TOOL_NOT_FOUND` com instrução de instalação.

## Jobs

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/jobs/{job_id}?after=N` | estado + saída; `after` devolve só as linhas depois do índice N |
| `GET /api/jobs?project_id=...` | jobs recentes |
| `POST /api/jobs/{job_id}/cancel` | cancela (FR-094) |
| `GET /api/jobs/{job_id}/stream` | SSE do progresso |

`after` é o que torna o polling barato: o cliente guarda `line_count` e pede
apenas o incremento, em vez de rebaixar a saída inteira a cada tick.

O stream SSE emite dois tipos de evento e um keep-alive:

```
event: log
data: {"lines": ["Varrendo C:/Users/User/Desktop…"], "revision": 1}

event: end
data: {"status": "SUCCESS", "exit_code": 0, "duration_ms": 179, "message": "36 candidato(s)."}

: keep-alive
```

O cliente cai para polling se o stream não abrir ou cair no meio — antivírus e
proxy locais no Windows fecham conexão persistente sem aviso. Como o polling
usa `after`, a troca de transporte não duplica nem perde linha.

```json
{
  "id": "j_8f21",
  "project_id": "dashboard-contabil",
  "action": "docker.up",
  "status": "RUNNING",
  "started_at": "2026-08-21T18:15:00Z",
  "finished_at": null,
  "exit_code": null,
  "output": "Container backend Created\nContainer db Starting\n"
}
```

## Cockpit AI — conversa

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/ai/status` | se dá para conversar, o gasto do dia e os modelos que a tela pode fixar |
| `POST /api/ai/ask` | pergunta avulsa, sem contexto de projeto (SSE) |
| `POST /api/projects/{id}/chat` | pergunta com o contexto do projeto (SSE) |

Corpo das duas perguntas:

```json
{ "question": "o que faz git stash?", "modelo": "claude-principal", "agent": null }
```

`modelo` é o **id lógico** de um modelo de `configs/ai.yml`, nunca o nome no
fornecedor (P-06). Vazio, o router escolhe pela complexidade. Id que o registro
não conhece cai no automático, sem erro. Pergunta classificada como privada vai
só para modelo local, mesmo com um modelo de nuvem fixado (REQ-07 vem antes do
REQ-08). `model` (`"default"`/`"alt"`) continua aceito: escolhe entre os dois
modelos do `.env`, e só vale quando não há registro.

`GET /api/ai/status` devolve em `modelos` só os que têm provider habilitado
**e** chave no ambiente — oferecer um que falharia na primeira tentativa por
falta de chave é pior que não oferecer:

```json
"modelos": [
  { "id": "claude-principal", "model": "claude-opus-5-5", "provider": "anthropic", "local": false }
]
```

O stream emite:

```
event: chunk
data: {"text": "Guarda numa pilha "}

event: meta
data: {"modelo": "claude-principal", "model": "claude-opus-5-5", "provider": "anthropic"}

event: end
data: {}
```

`meta` vem **depois** do texto: com fallback, quem respondeu só se sabe quando
a cadeia termina, e pode não ser o modelo pedido. Falha vira
`event: error` com `{"code", "message"}`, e aí não há `meta` nem `end`.

## Dashboard

### `GET /api/dashboard`

```json
{
  "totals": {
    "projects": 27, "running": 3, "stopped": 22,
    "with_docker": 14, "containers_running": 7,
    "with_git_changes": 9, "missing": 1
  },
  "pending_changes": [
    { "project_id": "kiteasy", "name": "KitEasy", "branch": "main", "dirty_count": 5 }
  ],
  "active_services": [
    { "project_id": "zapbot", "label": "Backend", "url": "http://localhost:8080", "state": "ONLINE" }
  ],
  "recent_projects": [
    { "id": "smartdash", "name": "SmartDash", "last_accessed_at": "2026-08-21T17:40:00Z" }
  ],
  "port_conflicts": [
    { "port": 8000, "projects": ["dashdate", "marketlab"] }
  ],
  "generated_at": "2026-08-21T18:16:00Z",
  "from_cache": true
}
```

Sempre de cache. `from_cache` é explícito para a UI poder mostrar a idade do
dado em vez de fingir tempo real.

## Atividade

`GET /api/activity?project_id=&action=&status=&limit=50` → log de auditoria
paginado (FR-102).

## Health da própria aplicação

`GET /api/health` → `{"status": "ok", "version": "0.1.0", "tools": {"git": true, "docker": true, "code": true}}`

Usado pela UI para desabilitar preventivamente ações cujas ferramentas não
existem, em vez de deixar o usuário clicar e falhar.
