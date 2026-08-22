# DevCockpit — Log de Sessões

Registro cronológico do trabalho no projeto, para retomar contexto rapidamente.

---

## Resumo executivo

**O que é:** central local que inventaria os projetos de desenvolvimento da
máquina e expõe Git, Docker, serviços e portas numa interface só, em
`127.0.0.1:8765`.

**Estado:** MVP completo em 2026-08-21. Fases 0 a 4, 131 pontos, 285 testes,
cobertura 92%. Repositório próprio, commit inicial `fc464fe`.

| Fase | Entrega | Testes |
|------|---------|--------|
| 0 | 14 docs, 8 ADRs, 44 histórias, modelo de segurança | — |
| 1 | CRUD de projetos, CommandRunner, guards, frontend base | 74 |
| 2 | Detecção de stack, Git somente leitura, varredura de diretório | 151 |
| 3a | JobManager: saída incremental, timeout, kill de árvore | 190 |
| 3b | Docker Compose: status, ações via job, logs | 242 |
| 4 | Health check, poller, ações de SO, dashboard em 168 ms | 285 |

**Decisão que organiza tudo:** a camada HTTP nunca conhece o sistema
operacional, e o sistema operacional nunca é alcançado sem passar pelo
`CommandRunner`. O cliente envia identificador de ação, nunca comando.

### Os quatro bugs que valeram a pena

Todos encontrados por teste, não por acaso:

1. **Repositório pai vazando** (ADR-008) — `git rev-parse` sobe a árvore, e
   como existe um repositório em `C:/Users/User`, os 36 projetos do Desktop
   exibiriam a mesma branch e os mesmos milhares de arquivos sujos. Seria o
   fim da confiança na ferramenta.
2. **Teste subindo container de verdade** — o runner síncrono estava dublado,
   mas jobs usam o assíncrono. O teste passava; os containers apareciam no
   `docker ps` depois.
3. **Truncamento que não truncava** — o corte da saída rodava só na primeira
   ultrapassagem do limite. Um job com saída contínua comeria memória.
4. **Poller quebrando em silêncio** — SQLite devolve datetime sem timezone;
   o `TypeError` caía no `except` que protege o poller. Health check nunca
   funcionaria, sem nenhum erro visível.

### Onde retomar

`PROJECT_STATUS.md` está em modo **EM USO**, com uma seção "Anotações de uso"
no topo. O backlog agora vem do que incomodar no dia a dia.

Pendente de verificação manual (abre janela na área de trabalho): botões
VS Code, Pasta, Terminal e Abrir serviço; e o comportamento com o Docker
Desktop desligado.

---

## 2026-08-21 — Sessão 1: Fase 0 (Discovery, Specs e Docs)

**Ponto de partida:** apenas o arquivo
`PROMPT — DESENVOLVIMENTO DO PROJETO DEVCOCKPIT.md` na pasta. Nenhum código,
nenhuma estrutura.

**Objetivo:** executar a Fase 0 pedida no item 32 do prompt — análise,
especificação, arquitetura e documentação, sem código de produção.

### Análise crítica do prompt

Seis lacunas estruturais identificadas antes de escrever qualquer documento:

1. **Comandos longos não cabem em request/response.** Os endpoints Docker do
   item 22 estouram timeout. Resolvido com modelo de job assíncrono (ADR-006).
2. **Windows ignorado.** O prompt usa sintaxe POSIX; a máquina alvo é Win 11.
   Resolvido com `OSAdapter` por plataforma (ADR-007).
3. **Health check síncrono travaria o dashboard.** N projetos × M serviços de
   requisições HTTP por carga de tela. Resolvido com poller em background e
   cache com TTL.
4. **Faltava descoberta automática de projetos.** Só havia cadastro manual.
   Adicionado como FR-009 a FR-011 — é o maior ganho de DX para quem tem
   dezenas de projetos espalhados.
5. **Logs de container são stream.** Exigem SSE; HTTP JSON não atende.
6. **Camadas sobrepostas.** `ProjectService` + `repositories` + `integrations`
   sem fronteira; `SystemService` e `ProcessService` duplicados. Reorganizado
   com `adapters/`, `runner/`, `jobs/`, `detection/`.

Inconsistências menores: item 12 vetava `/execute-command` mas não definia bind
address nem validação de path (CSRF via browser é vetor real em ferramenta
local); item 7 deixava o formato de config em aberto; faltava decidir Git CLI
vs biblioteca.

### Entregue

- 14 documentos em `docs/` (00 a 13)
- 7 ADRs em `docs/adr/`
- 62 requisitos funcionais com ID, 8 categorias de não funcionais
- Modelo de dados com 6 entidades e definição do que **não** persistir
- Modelo de segurança com 8 ameaças, 9 defesas e 12 testes bloqueantes
- Backlog: 10 épicos, 43 histórias, 128 pontos
- Roadmap: 7 fases, cada uma com critério de saída verificável
- Estrutura de diretórios, `README.md`, `.gitignore`, `.env.example`,
  `configs/roots.example.yml`, `configs/defaults.yml`, `PROJECT_STATUS.md`

### Decisões principais

| Decisão | Onde |
|---------|------|
| FastAPI + Pydantic v2 | ADR-001 |
| SQLite com migrações desde a v0.1.0 | ADR-002 |
| CommandRunner com allowlist de ações e sem shell | ADR-003 |
| SQLite fonte de verdade + `devcockpit.yml` opcional | ADR-004 |
| Frontend sem framework e sem build | ADR-005 |
| Jobs assíncronos para operações longas | ADR-006 |
| `OSAdapter` com Windows como plataforma primária | ADR-007 |

Decisão de segurança central: o cliente envia **identificador de ação**, nunca
comando. A tradução para argv é tabela fixa no código, executada sem shell, com
timeout obrigatório e path validado contra allowlist de roots.

### Pendências para a próxima sessão

- [ ] Revisão dos documentos pelo usuário
- [ ] Definir os diretórios de `configs/roots.yml` (Q-01)
- [ ] Decidir se o diretório ganha `.git` próprio
- [ ] Iniciar Fase 1 pela `US-001` (bootstrap)

**Estado ao fim da sessão:** Fase 0 concluída. Zero linha de código de
produção, conforme o item 32 do prompt.

---

## 2026-08-21 — Sessão 1 (continuação): ajustes de risco + Fase 1

### Ajustes pedidos após a revisão de riscos

Dois problemas identificados na análise de riscos e corrigidos antes de
codificar:

1. **Lacuna real no modelo de segurança: faltava validar o cabeçalho `Host`.**
   A defesa D5 checava `Origin` "quando presente", o que deixa a porta aberta
   para DNS rebinding — o atacante aponta o próprio domínio para `127.0.0.1` e
   o browser passa a tratar as requisições como same-origin, enviando o
   cabeçalho customizado sem preflight. Adicionadas a ameaça T9, a defesa D10
   (validar `Host` contra `localhost`/`127.0.0.1`/`[::1]` em **todas** as
   requisições, inclusive `GET` e SSE) e a exigência de `Origin` presente nas
   requisições de escrita. Dois testes novos, totalizando 14 obrigatórios.

2. **Fase 3 dividida em 3a e 3b.** A versão original juntava subprocess
   assíncrono, encerramento de árvore de processos no Windows, SSE e parse de
   saída do Compose. Falhando, não se saberia de qual dos quatro veio. Agora
   3a valida a máquina de jobs com comandos triviais (`scripts/job_probe.py`,
   US-043) e só depois 3b encosta no Docker.

### Fase 1 implementada e verificada

Backend:

- `core/`: `config.py` (bind loopback validado no próprio validador do
  Pydantic), `paths.py` (98% de cobertura — a linha restante é o ramo POSIX,
  inalcançável no Windows), `errors.py`, `logging.py` (JSON + redação de
  segredo), `cache.py` (TTL com relógio injetável)
- `runner/`: `CommandSpec` com timeout obrigatório, `SubprocessCommandRunner`
  sem shell, allowlist de ações com validadores tipados, `FakeCommandRunner`
- `models/`, `repositories/`, `services/`, `api/routes/`, migração 001
- middlewares `HostGuard`, `OriginGuard` e `CorrelationId`

Frontend, sem framework e sem build: shell com sidebar, roteador por hash,
`lib/api.js`, `lib/dom.js` (sem `innerHTML` com dado da API), `lib/ui.js`,
e as telas Dashboard, Projects, detalhe do projeto, Activity e Settings.

Verificação executada com o servidor real em `127.0.0.1:8765`:

| Verificação | Resultado |
|-------------|-----------|
| 3 projetos reais cadastrados | DevCockpit, ZapBot, SmartDash |
| path duplicado | 409 `PROJECT_ALREADY_EXISTS` |
| `C:/Windows/System32` (fora do root) | 403 `PATH_NOT_ALLOWED` |
| `POST` sem `X-DevCockpit-Client` | 403 |
| `GET` com `Host: evil.example` | 403 |
| `Origin` externa | 403 |
| bind `0.0.0.0` | startup recusado |
| `DELETE` de projeto | 204, pasta intacta no disco |
| migração rodada duas vezes | idempotente |

Suíte: 74 testes passando, 1 pulado (symlink exige privilégio no Windows),
cobertura total de 94%. `ruff check` limpo.

### Detalhe que vale lembrar

O teste `test_nenhum_shell_true_no_codigo` falhou na primeira execução porque
a **docstring** do `command_runner.py` mencionava a atribuição literal. A
correção foi reescrever o texto, não afrouxar o teste: uma varredura de
código-fonte com exceção para comentário é uma varredura que um dia deixa
passar o caso real.

### Pendências para a próxima sessão

- [ ] Confirmar `configs/roots.yml` (hoje: `Desktop` e `Documents`)
- [ ] Decidir se a pasta ganha `.git` próprio
- [ ] Conferir no browser se recarregar mantém a tela (último item do
      checklist manual da Fase 1)
- [ ] Iniciar Fase 2 pela `US-020` (registry de detecção)

**Estado ao fim da sessão:** Fase 1 fechada, 36 de 131 pontos do MVP.

---

## 2026-08-21 — Sessão 1 (continuação): Fase 2 — Detecção e Git

### Bug encontrado por teste — o mais importante da sessão

Um teste de contrato falhou apontando `is_repo: true` para um diretório
temporário sem nenhum `.git`. Investigando: `git rev-parse
--is-inside-work-tree` **sobe a árvore de diretórios**, e esta máquina tem um
repositório em `C:/Users/User` — o perfil inteiro sob controle de versão.

Confirmado em projeto real:

```
$ cd C:/Users/User/Desktop/Projetos/ZAPBOT
$ git rev-parse --show-toplevel
C:/Users/User
```

Sem correção, **todos os 31 projetos do Desktop exibiriam a branch e os
milhares de arquivos sujos do repositório pai** — o mesmo estado errado em
todos. O dashboard de "alterações pendentes", uma das telas centrais do MVP,
viraria ruído. É exatamente o risco que eu havia classificado como o mais
perigoso do projeto: dado errado exibido com confiança.

Correção (ADR-008): a pergunta certa não é "estou dentro de um repositório?"
e sim "a raiz do repositório é este diretório?". `locate_repo` usa
`--show-toplevel` e compara com o diretório do projeto. Três estados honestos:
repositório próprio, dentro de outro (com `repo_root` informado, e nenhum
`git status` executado), ou sem repositório algum.

### Entregue

- `app/detection/`: registry + 12 detectores (Python, Node, Vite, Next, Docker,
  Compose, Maven, Gradle, Go, Rust, HTML estático como fallback)
- extração de portas do arquivo Compose e do `vite.config.*`
- `app/adapters/git/`: adapter com `--porcelain=v2` e `--format` com separador
  ``/``, mais parsers puros
- `GitService` com cache TTL; `DiscoveryService` com varredura limitada
- `DetectionService` com regra "edição manual vence sempre"
- rotas: `/git/status|commits|branches|remotes`, `/detect`,
  `/discovery/scan|import`; migração 002
- frontend: aba Git na página do projeto, tela de descoberta com seleção e
  importação em lote, banner de projeto com diretório ausente

### Verificação com dados reais

| Verificação | Resultado |
|-------------|-----------|
| varredura do Desktop, profundidade 2 | 31 candidatos, 56 diretórios, **0,19 s** |
| stack detectada | confere com a realidade (Dashdate FastAPI+Docker, AI Procedures Next.js, ZapCRM Flask+Docker) |
| portas do Compose | Dashdate: 8000 e 8123 — as portas reais do projeto |
| importação em lote | 2 importados, 1 recusado (`PROJECT_ALREADY_EXISTS`) |
| Git em repo próprio | Dashdate: branch `main`, 4 não rastreados, commits reais |
| Git no DevCockpit (sem `.git` próprio) | `is_repo: false`, `inside_other_repo: true`, `repo_root: C:/Users/User` |

151 testes passando, cobertura 92%, `ruff check` limpo.

### Decisão de sequenciamento

A varredura era prevista como job assíncrono, mas o `JobManager` só chega na
Fase 3a. Implementada síncrona **e limitada** (profundidade, lista de
ignorados, teto de candidatos), o que satisfaz NFR-011 — que proíbe varredura
*ilimitada*. Medição de 0,19 s confirma que não há problema prático. Vira job
na 3a, e aí o contrato muda de 200 para 202. Registrado como D-23.

### Pendências para a próxima sessão

- [ ] Conferir a aba Git no browser
- [ ] Decidir se a pasta ganha `.git` próprio — agora com motivo extra: o
      DevCockpit se reporta como "sem repositório próprio"
- [ ] Iniciar Fase 3a pela `US-043` (harness `scripts/job_probe.py`)

**Estado ao fim da sessão:** Fase 2 fechada, 68 de 131 pontos do MVP.

---

## 2026-08-21 — Sessão 1 (continuação): Fase 3a — Máquina de jobs

Fase deliberadamente sem Docker (D-22): validar a execução assíncrona com um
processo previsível antes de somar a variabilidade do Compose.

### Entregue

- `scripts/job_probe.py` — processo de teste com linhas atrasadas, código de
  saída configurável, modo que **ignora sinal de término** e criação de filhos
- `AsyncCommandRunner` — saída linha a linha sem bloquear o event loop
- `app/runner/process.py` — encerramento de árvore (`taskkill /T /F` no
  Windows, `killpg` em POSIX), isolado onde `subprocess` é permitido
- `JobManager` — estados, saída incremental, timeout, exclusão mútua por chave,
  cancelamento, teto de saída com truncamento pelo começo, retenção
- rotas `/api/jobs`: consulta com `after`, listagem, cancelamento, SSE com
  keep-alive
- `JobConsole` na UI: saída ao vivo, autoscroll pausável, indicação do
  transporte (stream ou polling)
- varredura migrada de síncrona para job, cumprindo a promessa de D-23

### Três bugs meus, achados por teste

1. **Truncamento não truncava.** O corte da saída rodava só na primeira
   ultrapassagem do limite, protegido por `if not self.output_truncated`.
   Depois disso a lista crescia sem teto — o limite de 2 MB era decorativo.
   Um job que produz saída sem parar comeria memória até derrubar o servidor.

2. **`asyncio.create_task` sem event loop.** A rota de scan era `def`, e rota
   síncrona no FastAPI roda em threadpool, onde não há loop. Corrigido tornando
   a rota `async def`, e o `JobManager` agora falha com mensagem explícita
   ("a rota que enfileira job precisa ser `async def`") em vez do enigmático
   "no running event loop".

3. **Purga com retenção zero não purgava.** A comparação era `>`, e o relógio
   do Windows tem granularidade grossa o bastante para o intervalo dar
   exatamente zero. Virou `>=`.

Os quatro testes de varredura da Fase 2 também quebraram — corretamente: o
contrato mudou de 200 síncrono para 202 com job. Atualizados para o fluxo novo.

### Verificação

Com processo real (`job_probe.py`):

| Verificação | Resultado |
|-------------|-----------|
| saída incremental | aparece durante a execução, cresce até o fim |
| cancelamento | encerra em menos de 2 s |
| `--ignore-term` | morre mesmo recusando o sinal |
| filhos | morrem junto com o pai |
| **20 execuções seguidas** | **zero processo órfão** |
| chaves diferentes | 2 jobs de ~1 s terminam em menos de 2 s (paralelo real) |

Ao vivo, no servidor: varredura do Desktop em profundidade 3 devolveu **202**,
concluiu em **179 ms** com 36 candidatos em 120 diretórios; o SSE emitiu `log`
e `end`; a segunda varredura simultânea recebeu **409 OPERATION_IN_PROGRESS**.

190 testes passando (187 rápidos + 3 lentos), cobertura 92%, `ruff` limpo.

### Detalhe operacional que custou tempo

O `uvicorn --reload` deixa um processo filho cuja linha de comando não contém
`uvicorn app.main:app`, então o filtro que eu usava para parar o servidor não o
alcançava. O servidor novo falhava ao subir com `WinError 10048` e o antigo
continuava respondendo — dando a impressão de que o código não havia mudado.
Para parar de verdade, filtrar também por `multiprocessing*spawn_main`.

### Pendências para a próxima sessão

- [ ] Conferir o console de job no browser (tela Descobrir projetos)
- [ ] Conferir a aba Git no browser
- [ ] Decidir se a pasta ganha `.git` próprio
- [ ] Iniciar Fase 3b pela `US-050` (DockerAdapter)

**Estado ao fim da sessão:** Fase 3a fechada, 81 de 131 pontos do MVP.

---

## 2026-08-21 — Sessão 1 (continuação): Fase 3b — Docker

Fase curta porque a máquina de jobs já estava pronta e testada — que era
exatamente a razão de ter dividido a Fase 3.

### Entregue

- `DockerAdapter` com `compose ps --all --format json`, aceitando **array** e
  **JSON-por-linha** (o Compose v5.3.1 desta máquina usa por linha) e ignorando
  linhas de aviso intercaladas
- portas lidas de `Publishers`, que é estruturado, com IPv4/IPv6 deduplicados —
  bem melhor que parsear a string `Ports`
- `DockerService`: status cacheado, ações sempre via job, validação de nome de
  serviço contra o Compose do projeto
- migração 003 (`docker_config`), rotas de status/ações/logs
- aba Docker na UI reaproveitando o `JobConsole` da 3a

### O incidente da sessão: teste subiu container de verdade

Um teste de API que enfileirava `docker compose up` **criou containers reais**
na máquina — o projeto Compose `stack`, com `postgres:16` e `python:3.12`.

Causa: o `CommandRunner` síncrono estava dublado, mas jobs usam o
`AsyncCommandRunner`, que continuava real. O teste "passou"; o efeito colateral
só apareceu quando fui conferir o `docker ps`.

Limpeza feita na hora (`docker compose -p stack down`, sem `-v`), e duas
defesas adicionadas:

1. `conftest.py` dubla `job_manager.runner` no client padrão;
2. fixture `autouse` que **bloqueia** `AsyncCommandRunner.run` em teste não
   marcado como integração, falhando com mensagem explícita.

Registrado em `docs/10-testing-strategy.md` como anti-padrão nomeado. É o tipo
de erro que passa despercebido justamente porque o teste fica verde.

### Correção de UX vinda da verificação real

Toda a saída do `compose up` aparecia prefixada com `[stderr]`, porque o
Compose escreve progresso nesse canal. Um `up` bem-sucedido parecia cheio de
erro. Removida a distinção na saída do job (D-28): o que separa sucesso de
falha é o código de saída, que já vira status e mensagem.

### Verificação com Docker real (29.7.2, Compose v5.3.1)

| Verificação | Resultado |
|-------------|-----------|
| leitura do ZapCRM real | 1 container, porta 5000, health `unhealthy`, serviço `zap-crm` |
| logs reais | devolvidos com `tail` configurável |
| `compose up` em projeto descartável | **573 ms**, saída incremental, container criado |
| `compose down` | container e rede removidos |
| dois `down` simultâneos | segundo recebeu `409 OPERATION_IN_PROGRESS` |
| serviço inexistente | 422 com lista de disponíveis, nada executado |
| `prune`, `rm`, `kill`, `exec` | 422 — conjunto de verbos é fechado |
| projeto sem Compose | 200 com explicação, não erro |

Ambiente devolvido ao estado original: container, rede e pasta descartáveis
removidos, registro do projeto de teste apagado.

242 testes passando, cobertura 93%, `ruff` limpo.

### Pendências para a próxima sessão

- [ ] Conferir a aba Docker no browser
- [ ] Conferir o comportamento com o Docker Desktop **desligado**
- [ ] Decidir Q-02: o poller de health verifica todos os projetos ou só os
      fixados e recentes? (bloqueia a Fase 4)
- [ ] Decidir se a pasta ganha `.git` próprio
- [ ] Iniciar Fase 4 pela `US-060` (cadastro de serviços)

**Estado ao fim da sessão:** Fase 3b fechada, 97 de 131 pontos do MVP.

---

## 2026-08-21 — Sessão 1 (final): Fase 4 — MVP completo

### Decisão tomada por conta própria (Q-02)

A pergunta em aberto era se o poller de health verifica todos os projetos ou
só alguns. Segui com **fixados + acessados nos últimos N dias**
(`DEVCOCKPIT_HEALTH_HISTORY_DAYS`, padrão 7). Com 36 projetos, verificar todos
a cada 30 s custa caro e não serve: a maioria está parada há semanas. Qualquer
projeto continua verificável sob demanda. Registrado como D-32 — é um valor de
`.env`, fácil de mudar.

### Entregue

- `HealthService` com check HTTP e TCP concorrentes, timeout de 2 s, estados
  `ONLINE`/`OFFLINE`/`STARTING`/`ERROR`/`STALE`/`UNKNOWN`
- `HealthPoller` em background; falha de ciclo é contida
- `OSAdapter` para Windows, macOS e Linux — VS Code, pasta e terminal, com
  fallback de `wt.exe` para PowerShell e detecção de emulador no Linux
- `SystemActionService`: abrir URL por `service_key`, nunca por URL do cliente
- `DashboardService` agregando de cache, sem tocar disco, Git ou Docker
- migração 004 (`health_snapshot`), rotas de serviços, portas, ações, dashboard
- frontend: dashboard novo, aba Services, barra de ações que desabilita o que
  não dá para fazer, com o motivo no tooltip

### O bug mais interessante: falha silenciosa por timezone

O poller quebrava em **todo ciclo** e ninguém veria: o SQLite não guarda
timezone, então `last_accessed_at` voltava do banco como datetime ingênuo, e
comparar com `utcnow()` levantava `TypeError`. A exceção caía direto no
`except` que existe justamente para o poller não derrubar o servidor.

Resultado: health check nunca funcionaria, sem nenhum erro visível.

A correção foi na raiz — um `TypeDecorator` que garante UTC ciente na entrada e
na saída (D-33) — em vez de espalhar `if dt.tzinfo is None` por toda
comparação. Um teste de poller contra o banco real pegou isso.

### Verificação ao vivo

| Verificação | Resultado |
|-------------|-----------|
| `GET /api/dashboard` | **168 ms** (exigência: menos de 500 ms) |
| segunda chamada | `from_cache: true` |
| poller sozinho | achou ZAPBOT Database (5433) e Dashdate (8123), `ONLINE` |
| verificação sob demanda | distinguiu `ONLINE`, `OFFLINE` e `ERROR` |
| porta 8000 do Dashdate | `ERROR` por tempo esgotado, reportado honestamente |
| `GET /api/health` | git, docker e code disponíveis |
| `open/browser` com chave inválida | 422 com a lista de chaves válidas |
| payload com `url` em vez de `service_key` | 422 (D-13) |

285 testes passando, cobertura 92%, `ruff` limpo.

### O que ficou de fora, e por quê

`US-090` e `US-091` (importar e exportar `devcockpit.yml`) não entraram. São
conveniência: nenhum dos 12 casos de uso do PRD depende deles, e o ADR-004 já
previa que o sistema funciona inteiro sem manifesto.

### Estado final

**MVP completo: 131 de 131 pontos.** Fases 0 a 4 fechadas.

### Pendências para você

- [ ] Checklist manual da Fase 4 no browser: VS Code, Pasta, Terminal e Abrir
      serviço abrem janela na sua área de trabalho, então deixei para você
- [ ] Conferir a aba Docker com o Docker Desktop desligado
- [ ] Decidir o próximo passo com base no uso real

### Encerramento

Repositório próprio criado e primeiro commit feito (`fc464fe`, 182 arquivos).
`.env`, `configs/roots.yml`, `data/`, `.venv` e logs de servidor ficam fora do
versionamento; só `logs/session-log.md` é versionado, pela convenção de manter
o histórico de sessão junto do projeto.

Detalhe que fecha o ciclo: com `.git` próprio, o DevCockpit agora enxerga a si
mesmo como repositório — `is_repo: true`, branch `main`, `inside_other_repo:
false`. Antes do ADR-008 ele teria reportado a branch e os milhares de
arquivos sujos do repositório de `C:/Users/User`.

`PROJECT_STATUS.md` passou para o modo **EM USO**, com uma seção de anotações
de uso no topo. A partir daqui o backlog vem do que incomodar no dia a dia.

---

## Sessão 2026-08-21 (noite) — pontas soltas fechadas

**Pedido:** "falta algo pra melhorar?", seguido de "vamos finalizar o projeto e
melhorá-lo".

### O que entrou

**1. `lifespan` no lugar de `@app.on_event`** (commit `15847ab`)

O FastAPI deprecou o decorador e a suíte emitia 385 warnings por isso. O poller
de health e o encerramento do `JobManager` passaram para um contextmanager
passado ao construtor do `FastAPI`. Comportamento idêntico, incluindo cancelar
job em andamento no encerramento (D-07). Sobrou 1 warning, de terceiro:
`starlette.testclient` pedindo `httpx2`.

**2. Manifesto `devcockpit.yml` — US-090 e US-091** (commit `4b262bf`)

Quatro rotas em `app/api/routes/manifest.py`, com a lógica em
`app/services/manifest_service.py`:

| Rota | Efeito |
|------|--------|
| `GET /manifest` | estado, avisos e diff campo a campo |
| `GET /manifest/preview` | o YAML que a exportação escreveria |
| `POST /manifest/import` | aplica ao banco, upsert por chave de serviço |
| `POST /manifest/export` | escreve o arquivo, exige `confirm: true` |

A assimetria que organiza o módulo: **ler degrada, importar não**. Ler acontece
em toda carga da tela do projeto, então YAML quebrado, versão desconhecida e
campo estranho devolvem `200` com aviso. Importar é ação explícita do usuário,
então manifesto inválido recusa com `422` — aplicar metade seria pior.

As duas defesas que justificam o cuidado, ambas verificadas ao vivo: URL do
manifesto restrita a `localhost` (senão um repo clonado apontaria o health
check para host arbitrário) e `compose_file` que escape do diretório recusado
com `PATH_NOT_ALLOWED`.

**3. Tema claro**

Só tokens mudam — nenhum componente conhecia cor literal, exceto um `#fff` que
virou `--fg-on-accent`. Três estados: Sistema, Escuro, Claro. A preferência
mora no `localStorage` (D-41) e é aplicada por um script inline no `<head>`,
antes do primeiro paint, senão a tela pisca escura antes de virar clara.

### Verificação ao vivo

Servidor em porta separada (8799), banco temporário e projeto descartável no
Desktop, tudo removido no fim:

- cadastro importou o manifesto sozinho — nome, descrição e serviço `api`
- divergência apareceu em 4 campos, sem alterar nada
- exportar sem `confirm` devolveu `422` e não tocou no arquivo
- importar e exportar em seguida deixou o projeto `in_sync`
- `compose_file: ../../fora/...` → `403 PATH_NOT_ALLOWED`
- `health: http://evil.example.com/ping` invalidou o manifesto, com aviso
- YAML quebrado → `200` com aviso, projeto intacto

### Números

301 testes passando (19 novos), 1 pulado, cobertura 92%, `ruff check` limpo.
Decisões `D-37` a `D-41` registradas em `docs/12-decisions.md`.

### Pendências para você

- [ ] Conferir no browser: aba Manifest (prévia, avisos, diff), confirmação do
      botão Exportar, e o botão Tema alternando os três estados
- [ ] Conferir a aba Docker com o Docker Desktop desligado
- [ ] Usar por uma semana: o backlog daqui em diante sai do uso real

---

## Sessão 2026-08-21 (noite, parte 2) — rodada de browser

**Pedido:** "ajuste" → conferir no browser em vez de deixar o checklist manual.

Chromium headless dirigindo `127.0.0.1:8765` com o código novo. Antes de
começar foi preciso reiniciar o servidor: havia dois processos uvicorn sem
`--reload`, ambos servindo o código anterior ao manifesto.

### Quatro defeitos encontrados e corrigidos (commit `4ba9551`)

**1. Dois `null` na aba Manifest.** `container.replaceChildren(...)` não filtra
filhos nulos como o `mount` faz — os blocos opcionais (avisos e diff) viravam
o texto literal "null" na tela. Achado que nenhum teste de API pegaria: o
backend estava certo.

**2. Cabeçalho desatualizado depois de importar.** O painel redesenhava só a
aba, mas nome e descrição vivem no cabeçalho da página. Importar renomeava o
projeto e a tela continuava mostrando o nome antigo. Agora dispara
`hashchange`, que é o que o router escuta.

**3. Dashboard mostrando "0 Rodando" com quatro serviços online na mesma
tela.** A contagem vinha da coluna `status`, que descreve o registro e nunca
chega a `RUNNING` sozinha. Passou a vir do health observado (D-42). Agora: 3
rodando, 3 parados, 6 projetos.

**4. Check TCP dando OFFLINE para serviço que está no ar.** O mais sério dos
quatro. No Windows `localhost` resolve `::1` antes de `127.0.0.1`; um serviço
que só ouve em IPv4 fazia a tentativa IPv6 pendurar até estourar o timeout de
2 s. Resolvido com `happy_eyeballs_delay=0.25` (D-43). O teste novo falha sem
o fix — foi exatamente assim que o bug apareceu.

Vale notar: o "porta 8000 do Dashdate: tempo esgotado, reportado como ERROR"
registrado como comportamento correto no critério de saída da Fase 4 era, em
parte, este bug.

### Pedido no meio do caminho

"Liberar as tools para abrir no projeto" — os botões estavam habilitados nos
seis projetos, mas só na aba Overview. VS Code, Pasta e Terminal agora também
aparecem no card da lista de Projects (D-44), com os botões extraídos para
função compartilhada entre as duas telas.

### Conferido e funcionando

Aba Manifest (prévia, avisos, diff, importar, exportar com confirmação), tema
nos três estados com persistência e sincronia entre topbar e Settings, abas
Git/Docker/Services sem erro de console, "Verificar agora" trazendo ONLINE com
latência real, e as telas legíveis em claro e escuro.

302 testes, cobertura 92%, ruff limpo.

### Continua com você

- [ ] clicar em VS Code / Pasta / Terminal (abre janela na sua área de trabalho,
      então não cliquei)
- [ ] conferir a aba Docker com o Docker Desktop desligado

---

## Sessão 2026-08-21 (noite, parte 3) — o botão bloqueado

**Relato:** "ainda tá com o bloqueio no link de abertura do VS Code". Perguntado
o que aparecia na tela, a resposta foi decisiva: "só o sinal de bloqueado".
Não era erro de API — era o cursor `not-allowed` de um botão desabilitado.

### O bug

`tools()` em `frontend/js/lib/actions.js` memoizava a promessa do
`GET /api/health` **inclusive quando ela falhava**:

```js
toolsPromise = api.health().then(h => h.tools).catch(() => ({git:false, docker:false, code:false}));
```

A página aberta consultou o health no exato momento em que o uvicorn estava
sendo reiniciado (duas vezes, para carregar o código novo do manifesto). O
`catch` gravou "nenhuma ferramenta existe" e esse resultado valeu pelo resto da
sessão: VS Code, Pasta e Terminal desabilitados em todas as telas, sem erro
visível — o clique nem chegava a acontecer, então não havia o que mostrar.

Por isso a auditoria não tinha rastro: nenhum `FAILED`, nenhum `request denied`
no log do servidor, e a chamada direta por `curl` devolvia `200`. O defeito
estava inteiramente no navegador.

### A correção (D-45, commit `ba02014`)

- só o sucesso entra em cache; no `catch` a promessa é descartada e a consulta
  seguinte pergunta de novo;
- o indicador do rodapé revalida a cada 60 s e invalida o cache junto, o que
  também cobre o PATH mudando com a tela aberta (instalar o VS Code, subir o
  Docker Desktop).

### Como foi provado

No próprio browser, com o módulo recarregado: com o servidor derrubado,
`code=false`; assim que ele volta, a consulta seguinte devolve `code=true` sem
F5. Antes do fix ficava `false` para sempre.

Um detalhe do processo: as duas primeiras tentativas de prova deram falso
negativo porque um stub de `window.fetch` de um teste anterior ficou preso na
página — `goto` para a mesma URL com hash não recarrega. Só com
`?limpo=1` na URL o `fetch` voltou a ser nativo e o teste ficou honesto.

### Lição que vale além deste projeto

Cachear resultado de falha em memória é armadilha: o estado transitório vira
permanente, e o sintoma aparece longe da causa. Cachear só o sucesso custa uma
linha.

### Continua com você

- [ ] Ctrl+F5 na aba aberta (ela ainda tem o JS antigo, e é o próprio bug que
      a mantém bloqueada)
- [ ] clicar em VS Code / Pasta / Terminal, que abrem janela na sua área de
      trabalho
- [ ] conferir a aba Docker com o Docker Desktop desligado

---

## Encerramento da sessão de 2026-08-21

Pedido de melhorar o frontend levantado e **adiado para a próxima sessão**, por
decisão do usuário. As quatro frentes ficaram registradas em
`PROJECT_STATUS.md`, na seção "Próximo" (item B2), com o raciocínio de cada
uma — é por ali que a próxima sessão começa.

### O que esta sessão entregou

| Commit | Entrega |
|--------|---------|
| `15847ab` | `@app.on_event` → `lifespan` (385 warnings a menos) |
| `4b262bf` | Manifesto `devcockpit.yml`: importar, exportar, comparar + tema claro |
| `79bc054` | Log da sessão de pontas soltas |
| `4ba9551` | Quatro defeitos achados no browser + ferramentas no card |
| `5244d34` | Log da rodada de browser |
| `ba02014` | Botão bloqueado para sempre após falha de rede |
| `4854c46` | D-45 no registro de decisões |
| `680380a` | Log do bug do botão bloqueado |

302 testes passando, 1 pulado, cobertura 92%, `ruff check` limpo. Decisões
`D-37` a `D-45` registradas.

Cinco defeitos reais corrigidos, todos encontrados **abrindo o produto**, não
lendo o código: dois `null` renderados, cabeçalho desatualizado após importar,
"0 rodando" com quatro serviços online, check TCP falhando em `localhost`
IPv4-only, e o cache de ferramentas guardando a falha.

### Estado ao encerrar

Servidor no ar em `127.0.0.1:8765` com o código atual. Nenhum arquivo de teste
deixado para trás. Repositório limpo.

### Primeira coisa ao voltar

Ctrl+F5 na aba do DevCockpit, se ela ficou aberta desde antes do fix.

---

## Sessão 2026-08-22 — frontend, e três defeitos que não deixavam rastro

Sessão de manhã. Começou pelo que ficou pendente da noite anterior (o item B2,
"melhorar o frontend") e acabou revelando que três dos quatro problemas do dia
não estavam no código que eu ia mexer.

### O botão do VS Code (D-46, commit `c75565d`)

**Relato:** "o único botão que não tá funcionando é do VS Code."

A auditoria dizia o contrário. Toda execução, sem exceção:

```json
{"action": "system.vscode", "exit_code": 0, "duration_ms": 1236, "status": "SUCCESS",
 "argv": ["...\\bin\\code.CMD", "C:\\Users\\User\\Desktop\\...\\DEVCOCKPIT"]}
```

E o VS Code estava no ar, com vinte processos. Perguntei o que aparecia na
tela: **nada**. Nem janela, nem piscar na barra de tarefas.

Era isso mesmo. `code <path>` reaproveita a janela já aberta e devolve 0 sem
mostrá-la, porque o Windows recusa `SetForegroundWindow` vindo de um processo
que não tem o foco — e o uvicorn não tem, o browser tem. A pasta era aberta de
verdade, atrás do navegador.

O backend sempre esteve correto. O que faltava era pedir o foco.

`app/adapters/system/focus.py` acha a janela do editor pelo título e a traz
para frente anexando a fila de entrada da thread que está em primeiro plano —
o contorno documentado dessa restrição. Casa **pelo nome da pasta**, nunca a
primeira janela do editor: com vários projetos abertos, focar o errado é pior
que não focar. Roda em thread daemon e engole qualquer falha, porque a ação já
deu certo e o foco é cortesia.

Descoberta desconfortável no caminho: **não havia teste nenhum** cobrindo a
rota `open/vscode` nem o `SystemActionService`. Foi por aí que o buraco passou.
Somados cinco, incluindo a ordem executar-depois-focar.

### O upper do frontend (D-47, D-48, commit `1cc9949`)

Pedido: "melhorar o layout, melhorar a experiência do usuário, organizar os
cards". As quatro frentes do item B2 foram atacadas de uma vez.

**Card do projeto.** Mostrava o caminho em três linhas e cinco botões — nada
sobre o projeto. Agora responde "o que está de pé?" antes de qualquer clique:
`2/2 online`, `Docker`, `main · 4`. Os sinais vêm do cache do dashboard, que já
agrega isso sem tocar disco; listar projetos continua sem disparar `git status`
nem verificação de rede (NFR-010). O único campo novo no backend é
`services_total`, que sai do banco — o numerador vem do cache.

O caminho virou uma linha com o resto no tooltip, e as duas fileiras de botões
viraram uma: "Abrir" era um segundo caminho para onde o título do card já
levava.

**Busca.** Havia duas caixas na mesma tela, a 100 px uma da outra, e nada dizia
qual valia. Ficou uma só, a da topbar, filtrando ao vivo. A barra da página
ficou com o que texto não expressa — fixados, com serviço online, com Docker,
com alteração — cada recorte com sua contagem.

**Dashboard.** Metade da tela vazia virou o mapa de portas, que responde a
pergunta de todo dia ("quem está ocupando a 8000?") com o conflito marcado na
própria linha, e os blocos viraram painéis nomeados com contagem no cabeçalho.

**Camada visual.** Um defeito real apareceu na leitura dos tokens: o
`--bg-elevated` servia a dois papéis, e no tema claro os dois davam branco —
badge branco sobre card branco desaparecia. Separado em `--bg-subtle` (recuo
dentro do painel) e `--bg-elevated` (o que flutua). Além disso: pesos, alturas
de linha e elevação viraram token; seleção, cursor, barra de rolagem e anel de
foco deixaram de vir com o padrão do sistema operacional; números em coluna
ficaram tabulares; os glifos Unicode viraram um conjunto SVG desenhado, de
traço único.

Dois bugs de CSS encontrados **olhando o resultado renderizado**, não o código:
a barra colorida do toast e do alerta usava `grid-row: 1 / -1`, que resolve
contra a grade explícita e por isso prendia o ícone à primeira linha,
desalinhando o texto; e a barra lateral responsiva ficava cortada porque os
itens quebravam em duas linhas.

### O servidor que "quebrava" (D-49, D-50)

**Relato:** "por que tá quebrando o processo?"

O log mostrava saída limpa, sem traceback:

```
INFO:     Shutting down
INFO:     Application shutdown complete.
INFO:     Finished server process [1852]
```

Não estava quebrando: estava sendo desligado. Eu subia o uvicorn como processo
filho da minha própria chamada de ferramenta, então toda interrupção do meu
turno o levava junto. Aconteceu três vezes, sempre logo depois de uma
interrupção.

`scripts/serve.ps1` sobe o servidor solto do terminal, é idempotente, sabe
dizer status e reinicia. Acha o processo **pela porta**, não pelo arquivo de
PID, senão um servidor subido à mão por fora do script escapa da checagem e
duas instâncias brigam pela mesma porta. Distingue "no ar" de "travado":
processo vivo que não responde é pior que processo morto.

`--reload` ficou desligado por padrão. Ele já deixou de aplicar uma mudança de
schema nesta mesma sessão — o `WatchFiles` anunciou o recarregamento, e o
`/openapi.json` continuou servindo o schema antigo. Servidor que mente sobre
ter recarregado custa mais caro que reiniciar na mão.

O script não rodou de primeira: erro de sintaxe apontando para o fecha-chaves
de uma função inteira. Sem BOM, o Windows PowerShell 5.1 lê `.ps1` na codepage
ANSI; o travessão em UTF-8 termina no byte `0x94`, que em cp1252 é aspa curva
de fechamento, e o parser encerra a string no meio do código. Gravado com BOM,
passou.

### A alteração que não aparecia (D-51, commit `8b32cea`)

**Relato:** "não vi modificação no layout."

Esse foi o terceiro do dia com o mesmo formato: o servidor estava certo, o
sintoma estava no cliente, e não havia rastro em log nenhum dos dois lados.
Verifiquei com `curl` (arquivo novo sendo entregue) e com um Chrome de perfil
limpo, que renderizou a tela nova.

Nenhuma resposta do frontend trazia `Cache-Control`. Sem esse cabeçalho o
navegador aplica cache heurístico: estima sozinho por quanto tempo o CSS e o JS
valem e **não pergunta ao servidor** nesse intervalo. O ETag estava lá desde
sempre, mas ninguém chegava a usá-lo.

`no-cache` não é "não guarde", é "guarde, mas confirme antes de usar". Medido:
revalidação devolve 304 com zero byte. O `index.html` levou o mesmo cabeçalho
por um motivo próprio — se ele vier do cache, referências novas a arquivos
novos nunca chegam a ser pedidas.

### Como o frontend foi verificado

Sem Playwright na máquina, usei o Chrome instalado em `--headless=new` com
`--screenshot` e `--virtual-time-budget`, e **li as imagens**. Cada rodada
achou defeito que a leitura do código não acharia: cards de alturas diferentes
na mesma linha, o select de stack quebrando para uma linha própria, a barra
lateral cortada, o alerta desalinhado.

O tema claro exigiu um contorno: a preferência mora no `localStorage` e o
headless não tem como recebê-la de fora. Forcei o padrão em `theme.js` só para
os dois screenshots e restaurei com `git checkout` logo depois.

### Números

313 testes passando, 1 pulado. `ruff check` limpo. Detector de design da skill
`impeccable` sem apontamento. 23 arquivos, +2170/−261.

| Commit | Entrega |
|--------|---------|
| `c75565d` | Botão VS Code abria o projeto atrás do browser (D-46) |
| `1cc9949` | Cards com sinais, dashboard denso, servidor solto (D-47 a D-50) |
| `8b32cea` | Frontend servido com `no-cache` (D-51) |

### A lição do dia

Três dos quatro problemas relatados tinham o servidor inocente e o log mudo.
Em todos, o que resolveu foi a mesma pergunta: **o que exatamente aparece na
sua tela?** "Nada acontece" e "não mudou" descrevem a percepção, não o defeito
— e o defeito estava, respectivamente, no gerenciador de janelas do Windows e
no cache do navegador. Nenhum dos dois aparece em `logs/devcockpit.log`.

### Continua com você

- [ ] `Ctrl+Shift+R` na aba aberta e conferir o layout novo
- [ ] clicar em VS Code e confirmar que a janela agora vem para frente
- [ ] dizer o que ainda incomoda visualmente — o polimento que sobra é o que
      só se decide olhando
- [ ] conferir a aba Docker com o Docker Desktop desligado (pendente desde 21)
