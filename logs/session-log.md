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
