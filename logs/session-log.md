# DevCockpit — Log de Sessões

Registro cronológico do trabalho no projeto, para retomar contexto rapidamente.

---

## Resumo executivo

**O que é:** central local que inventaria os projetos de desenvolvimento da
máquina e expõe Git, Docker, serviços e portas numa interface só, em
`127.0.0.1:8765`.

**Estado:** MVP completo em 2026-08-21 (fases 0 a 4, 131 pontos, 285 testes,
cobertura 92%). Em uso desde então, com o backlog vindo do que incomoda no dia
a dia: sessão 5 mexeu no frontend, sessão 6 varreu bugs e trouxe descoberta de
porta, o botão de ligar sem terminal e a orquestração Docker → aplicação, e a
sessão 7 fez o painel deixar de só informar para passar a operar.
**426 testes** hoje, cobertura 90%.

**O que a ferramenta faz, em três frases:** um clique sobe o ambiente em
container, espera as dependências responderem e sobe a aplicação nativa com hot
reload; desligar para só a aplicação e deixa o ambiente de pé. A saída de cada
servidor tem tela própria, ao vivo e depois da queda. O dashboard mostra o que
a máquina está aguentando e qual projeto está custando — com o nome do projeto,
que é o que o Gerenciador de Tarefas não sabe dizer.

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

O trabalho das sessões 6 e 7 está na branch `varredura/bugs-e-organizacao`,
**21 commits, fora da `main`**. Entrar ou não é decisão pendente, e é o primeiro
item de "Continua com você" no fim do log.

A dívida conhecida está listada lá também: `git_service` com 47% de cobertura,
duas tabelas com migração que nada lê nem escreve, e zero teste de frontend
contra 4600 linhas de Python a 90% — sendo que os últimos defeitos foram todos
de frontend.

Pendente de verificação manual (abre janela na área de trabalho): o botão
VS Code trazendo a janela para frente; e o comportamento da aba Docker com o
Docker Desktop desligado. O resto da interface foi exercitado no browser real
ao final da sessão 6 — doze testes, nenhum erro de console.

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

- [x] `Ctrl+Shift+R` na aba aberta e conferir o layout novo — **confirmado**:
      o layout novo apareceu assim que o cache foi ignorado, o que fecha o
      diagnóstico do D-51 no browser real e não só no headless
- [ ] clicar em VS Code e confirmar que a janela agora vem para frente
- [ ] dizer o que ainda incomoda visualmente — o polimento que sobra é o que
      só se decide olhando
- [ ] conferir a aba Docker com o Docker Desktop desligado (pendente desde 21)

---

## 2026-08-22 — Sessão 6: Varredura de bugs, descoberta de porta e ligar sem terminal

**Pedido de partida:** "vamos dar uma varredura pra achar bugs e organizar toda
a parte do sistema". Ao longo da sessão o pedido cresceu com o que foi
aparecendo na tela: o ZAPBOT que não desligava, a barra de ativos que só
fechava, projeto novo que parecia não ser escaneado, e o ponto central — não
precisar abrir o terminal para subir cada projeto.

### A varredura

Leitura de `app/`, `frontend/` e `tests/` inteiros. Oito defeitos reais, todos
com teste de regressão em `tests/unit/test_regressoes_varredura.py`.

**1. URL de serviço aceitava destino externo.** `validate_local_http_url` achava
o host cortando a string no primeiro `:`. Em `http://localhost:3000@evil.com/`,
`localhost:3000` é *userinfo* e o host real é `evil.com`: a URL passava, virava
`health_url` de um serviço e o poller passava a bater num host externo a cada
ciclo. O host agora sai de `urlparse`. De brinde, `http://[::1]:8080` passou a
ser aceito — o parser antigo rejeitava IPv6 com porta.

**2. Console de job congelava depois do primeiro truncamento.** `revision`
conta tudo que já saiu e nunca retrocede; `lines` encolhe a cada corte. O
código fatiava `lines[after:]` com um índice absoluto, então a partir do
primeiro truncamento o SSE entregava listas vazias para sempre. `Job` ganhou
`dropped` e `lines_since`, e o marcador de truncamento saiu da lista — linha
sintética no meio dos dados desalinha qualquer cursor.

**3. Terminal abria e era morto pelo timeout.** Terminal, editor e explorador
rodavam com `capture_output` e timeout de 10 s. `powershell -NoExit` e
`alacritty` só terminam quando o usuário fecha a janela: o timeout matava a
janela recém-aberta, e o pipe de captura impedia console próprio. `CommandSpec`
ganhou `detached`, e o runner dispara sem esperar. Vale para as três
plataformas.

**4. `serve.ps1` morria antes de subir o uvicorn.** O alembic escreve as linhas
`INFO` dele em stderr mesmo quando dá certo. Com `ErrorActionPreference` em
`Stop`, o PowerShell 5.1 empacota cada linha num ErrorRecord e o script termina
ali — sem mensagem que apontasse para migração. O sintoma era "o servidor não
sobe". Quem decide agora é o código de saída.

**5. Serviço desligado aparecia como erro.** `_check_http` mapeava qualquer
timeout para ERROR. No Windows, tentar uma porta sem ninguém escutando pendura
até o timeout em vez de recusar na hora, então o caso mais banal que existe —
o serviço não foi ligado — chegava na tela como "erro". Vermelho que aparece
sempre para de significar alguma coisa. `httpx` separa os dois casos e o código
não usava a distinção: `ConnectTimeout` é não ter conectado (OFFLINE), qualquer
outro timeout é ter conectado e não ter respondido (ERROR).

Mais três de menor porte: `compose_file` do manifesto era gravado e nunca lido;
`FORBIDDEN_FLAGS` estava declarado e nunca conferido, então a barreira contra
`down -v` no registro era só documentação; e o ramo de timeout do check TCP era
código morto, porque desde o Python 3.10 `TimeoutError` é subclasse de
`OSError` e o `except` vinha depois.

### Descoberta de porta

O painel só sabia o que alguém tinha digitado no cadastro. Quando o número
ficava velho — e fica, porque ninguém volta no painel depois de mudar a porta no
`.env` — o projeto aparecia parado com o servidor no ar. O caso desta máquina: o
próprio DevCockpit estava cadastrado em 3003 e rodando em 8765.

`app/adapters/system/ports.py` enumera as portas em escuta e, para cada uma, o
processo que a abriu. `app/services/port_discovery_service.py` atribui cada
porta a um projeto, nesta ordem: diretório de trabalho do processo dentro do
projeto, caminho do projeto na linha de comando, runtime de container (marcado,
não atribuído), e sem dono. A comparação de path é por componente, não por
texto — `/dev/app-antigo` não pode casar com `/dev/app`, o mesmo bug que
`app/core/paths.py` existe para não ter.

**Por que `psutil` e não `netstat`.** A pergunta não é "que portas estão
abertas" e sim "de quem é o processo que abriu". Só o diretório de trabalho
responde isso. Medido: `psutil` faz a varredura inteira em ~5 ms;
`Get-NetTCPConnection` mais `Get-Process` levava ~1,4 s e ainda assim não dava o
`cwd`.

A tela de Ports ganhou o aviso de divergência com um botão que adota a porta
observada, a marca "no ar" nas portas que realmente respondem, e a lista
recolhida das portas de terceiros — que é a resposta para o `up` que falha com
*address already in use*.

Três limites deliberados: descoberta não corrige declaração sozinha; projeto sem
nada escutando não vira divergência (silêncio é o estado esperado de projeto
parado, e alerta que aparece para todo mundo não alerta ninguém); e varredura
recusada por privilégio marca `observation_available: false`, para a tela dizer
"não consegui olhar" em vez de "nada escutando".

### Ligar sem abrir terminal

O pedido central da sessão. Até aqui "ligar" só existia para projeto com
Compose; projeto de `npm run dev` ou `uvicorn` — a maioria — exigia abrir um
terminal e digitar o comando toda vez.

**O que muda no ADR-003.** Não muda: nenhum valor vindo do cliente HTTP entra em
argv; o cliente manda o id do projeto e nada mais. Muda: o argv deixa de ser
exclusivamente literal no código e passa a poder vir do bloco `run:` do
`devcockpit.yml` ou da detecção sobre `package.json` e `pyproject.toml` —
sempre arquivos dentro de um root permitido.

É aceitável porque quem escreve esses arquivos já executa o que quiser na
máquina por caminhos mais curtos: `scripts` do `package.json` roda em `npm
install`, hook do Git roda em `git commit`. A superfície que o modelo de
segurança fecha é a remota (D1, D5, D10), e essa continua inteira.

Ainda assim há guarda, porque comando lido de arquivo erra sem ser malicioso:
string no lugar de lista é recusada, `cwd` que escapa do projeto é recusado, e
os fragmentos destrutivos que o registro fixo já recusava também — o `run:`
copiado de outro projeto trazendo um `down -v` apagaria o volume do banco no
primeiro clique.

**Por que não é job.** Job é "faça isto e termine": timeout, cancelamento no
encerramento da aplicação, descarte por retenção. As três coisas matam um `npm
run dev`. O processo nasce ao lado do `JobManager`, sem timeout, em grupo
próprio, com o PID no banco. Sobreviver ao painel só não vira órfão porque a
descoberta de porta existe: na volta, o processo é reencontrado pelo PID gravado
e confirmado pela porta em escuta.

### Os dois detalhes que só apareceram rodando

Nenhum dos dois é visível na leitura do código, e os dois custaram uma volta
inteira de teste no browser real.

`npm` no Windows é `npm.CMD`. Sem shell, `CreateProcess` recebe "npm", não acha
arquivo com esse nome exato e devolve "o sistema não pode encontrar o arquivo
especificado" — com o npm instalado. Falta a extensão, que só o `PATHEXT`
conhece. `shutil.which` resolve, e era a mesma solução que
`WindowsOSAdapter.open_in_editor` já usava para o `code`.

`DETACHED_PROCESS` custava o log. O `.CMD` roda por dentro do `cmd.exe`, que sem
console nenhum alocava um por conta própria e mandava a saída para lá: o
servidor subia certo e o log aparecia vazio, que é a pior combinação possível
para depurar uma queda. `CREATE_NO_WINDOW` esconde a janela sem quebrar o
redirecionamento e também não amarra o filho ao nosso tempo de vida.

### Os três relatos de tela, e o que cada um era de verdade

**"O ZAPBOT não desliga."** Desligava: os seis containers paravam. O que não
parava era a porta 5433, e a porta 5433 não é do container — é de um Postgres
nativo rodando na máquina. O verificador batia nela, achava resposta, e trinta
segundos depois devolvia o botão para "Ligado". A causa de fundo era o botão
declarar o estado a partir do código de saída do comando; parar container não é
o mesmo que a porta ficar livre. Agora a tela reverifica depois da ação e, se
os containers pararam mas a porta continua atendendo, diz isso em vez de fingir.

**"A barra de Ativos só fecha."** O toggle sempre funcionou. O botão da topbar
era um ícone sem rótulo: fechar é óbvio, o X mora dentro da própria barra;
reabrir dependia de adivinhar que aquele ícone era o caminho de volta. Virou
chave rotulada com nome, contagem de quantos estão no ar e estado marcado, mais
Ctrl+Alt+B. A contagem sobrevive à barra fechada, o que dá ao botão utilidade
mesmo para quem prefere trabalhar sem a barra aberta.

**"Projeto novo não é escaneado."** Não reproduziu: criei um projeto pela API e
a detecção rodou e persistiu. O `smartdash` estava mesmo sem stack, mas era
registro antigo — rodar a detecção nele preencheu tudo na hora. O que a
investigação achou foi a fragilidade que produziria exatamente esse sintoma: o
registry só continha `OSError`, e detector lê arquivo de projeto alheio, que vem
torto de dez jeitos com exceção de tipo próprio cada um. A que escapasse
derrubava o cadastro do projeto junto. A varredura do fallback não tinha
proteção nenhuma. Endurecido, e card sem stack passou a oferecer "Detectar
stack" num clique.

### Números

395 testes passando, 1 pulado. `ruff check` limpo. 44 arquivos,
+3476 e −127 linhas. Dependência nova: `psutil`.

| Commit | Entrega |
|--------|---------|
| `877ad5f` | Seis defeitos da varredura, com regressão para cada um |
| `74fd474` | Serviço desligado lia como erro; `serve.ps1` abortava na migração |
| `d7b80c6` | Descoberta de porta e o aviso de declarado contra observado |
| `84ab027` | Chave rotulada da barra de ativos; desligar confirmado por verificação |
| `a290e31` | Servidor de desenvolvimento pelo painel, sem terminal |

### A lição do dia

Três dos oito defeitos eram **código morto que parecia proteção**: o ramo de
timeout do TCP, a lista `FORBIDDEN_FLAGS` e o `compose_file` do manifesto. Os
três liam como se o cuidado estivesse tomado — havia constante, havia `except`,
havia coluna no banco — e nenhum dos três era executado alguma vez. Documentação
que mente é ruim; código que mente é pior, porque ninguém revisa duas vezes uma
guarda que já está lá.

O antídoto que funcionou foi banal: procurar por nome cada constante e cada
ramo, e conferir se alguém os alcança. `FORBIDDEN_FLAGS` aparecia uma vez no
repositório inteiro — na própria definição.

### Continuação: a orquestração Docker + app

A decisão que a seção anterior deixou aberta foi respondida no meio da sessão:
**o Docker abre os ambientes, o sistema pega os ambientes já construídos e
continua o processo.** Banco e fila em container; a aplicação nativa, com hot
reload, falando com eles.

**Quem é aplicação e quem é ambiente.** O bloco `run:` do manifesto decide.
Havendo `run:`, a aplicação é o comando dele e o Compose inteiro vira ambiente.
Não havendo, a aplicação é o próprio Compose.

Declaração explícita compõe; inferência não. O ZAPBOT tem `api`, `nginx` e
`worker` dentro do Compose: inferir "além dos containers, roda também o `npm run
dev`" subiria a aplicação duas vezes na mesma porta. Escrever quatro linhas no
manifesto é barato; desfazer um duplo start não é.

**A ordem, e a espera.** `compose up -d` primeiro, sempre — é idempotente, então
com tudo de pé retorna rápido e não mexe em nada. Depois a espera, depois a
aplicação. A ordem inversa quebra: aplicação antes do banco morre no primeiro
`connect`.

Esperar tempo fixo seria chute — um Postgres com banco vazio abre em dois
segundos, com trinta giga em vinte. Espera-se as portas dos serviços declarados
**que não são a aplicação**, com teto de 30 s. A porta do próprio app fica fora
por definição: ele ainda não subiu, e incluí-la estouraria o teto em toda
subida. Passado o teto, a aplicação sobe assim mesmo com aviso: travar o clique
para sempre é pior que deixá-la reclamar, que é o que ela faria no terminal.

**A assimetria do desligar.** "Desligar" para a aplicação; os containers ficam.
Banco e fila são caros de subir e não mudam entre uma execução e outra do
backend — derrubá-los a cada parada trocaria um ciclo de dois segundos por um de
trinta. Shift+clique derruba tudo, e o chip do Docker no card também. Quando o
projeto não tem aplicação separada, "Desligar" para o Compose, senão o botão não
faria nada.

**O chip do Docker existe por causa disso.** Com o botão falando só da
aplicação, parar o app deixaria o painel dizendo "Desligado" com o Postgres
atendendo na porta — a mesma confusão que o caso do ZAPBOT expôs. Pelo mesmo
motivo `ProjectSummary.app_running` é `None`, e não `false`, quando o projeto não
tem aplicação separada: `false` diria "parado" com a stack inteira no ar.

### O que o smartdash ensinou, rodando

Três defeitos que a leitura do código não pegaria, um a cada tentativa:

1. **Interpretador.** `plan_from_python` emitia `python` puro, que é o do PATH e
   tem as dependências de outra pessoa. Deu `ModuleNotFoundError: No module
   named 'duckdb'` — de uma biblioteca instalada, só que no `.venv` do projeto.
   Agora o `.venv` local é procurado primeiro.
2. **Caminho relativo de programa.** `CreateProcess` resolve caminho relativo
   contra o diretório do processo que **chama**, não contra o `cwd` do filho, e
   `.venv/Scripts/python.exe` no manifesto apontava para o lugar errado.
3. **Já estar no ar virava falha.** `up` com a aplicação rodando levantava
   `ServerAlreadyRunning` e marcava o job inteiro de vermelho — incluindo a
   etapa do Compose que tinha dado certo. Subir é idempotente por decisão.

Depois disso a sequência inteira funcionou:

    Subindo os containers (docker-compose.yml)…
     Container smartdash-db-1 Healthy
     Container smartdash-backend-1 Started
    Containers no ar.
    Esperando as dependências responderem: Database…
      Database respondeu.
    Dependências prontas.
    Aplicação no ar: .venv/Scripts/python.exe -m uvicorn backend.app.main:app --reload …

### Rede de proteção nova nos testes

Escrever `test_environment.py` subiu um `node` de verdade num diretório
temporário do pytest — e ele **sobreviveria ao pytest**, que é o que o
`CREATE_NEW_PROCESS_GROUP` garante de propósito. O `conftest` já barrava execução
real em job; o servidor de desenvolvimento não passa pelo `JobManager` e escapava
da rede. Agora `start_background` também é barrado fora de teste `integration`.

### A bateria no browser, e os três defeitos que ela achou

Doze testes: ligar e desligar pelo botão, o "Abrir", o chip do Docker nos dois
estados, o trilho por clique e por Ctrl+Alt+B, as seis telas, e o "Detectar
stack" num projeto sem nada reconhecível e depois com `package.json`. Nenhum erro
de console.

**A sugestão de porta podia criar o conflito que ela existe para apontar.**
`_mismatches` sugeria a mesma porta observada para todos os serviços divergentes
do projeto. Com o SmartDash declarando 3004 e 3005 e uma só porta sua no ar, a
tela oferecia "Usar 8000" nas duas linhas — inclusive na do banco. Agora uma
porta observada só pode ser sugerida a um serviço, e com ambiguidade a
divergência aparece sem sugestão, com um botão "Corrigir". Dizer "está errado"
sem chutar o certo é honesto; chutar errado custa uma porta trocada à toa.

**Porta de container não era atribuída a projeto nenhum.** O `cwd` do Docker
aponta para a instalação dele, então nenhuma regra de atribuição casava. O banco
do SmartDash aparecia como "sem dono" e o serviço declarado virava divergência —
alarme falso justamente na configuração que o painel recomenda. Sobra o número:
se um único projeto declara aquela porta, foi o Compose dele que a publicou.
Declarada por dois, ninguém é atribuído.

**O card sabia ligar e não sabia abrir.** Depois de ligar, a próxima coisa que se
quer é ver, e "Abrir" só existia na página do projeto. O card ganhou o botão, com
a **chave** do serviço e nunca a URL — quem abre é o backend, e aceitar URL do
cliente reabriria o vetor que a decisão D-13 fecha.

### Um susto que não era bug

Durante a verificação, um `python.exe` com o caminho do interpretador global
aparecia segurando a porta 8000, e por um momento pareceu processo órfão dos
testes anteriores. Não era: o pid era filho do processo do `.venv`, e no Windows
o `python.exe` de um ambiente virtual é um redirecionamento para o base — as
dependências do venv estavam lá, tanto que o `duckdb` importou. Árvore só,
saudável.

Vale registrar porque o caminho no `cmdline` de um processo em venv no Windows
**não** identifica o ambiente que ele está usando, e concluir o contrário custou
uma investigação.

### Números finais da sessão

413 testes passando, 1 pulado. `ruff check` limpo. 50 arquivos, +5067 e −146
linhas. Dependência nova: `psutil`.

| Commit | Entrega |
|--------|---------|
| `877ad5f` | Seis defeitos da varredura, com regressão para cada um |
| `74fd474` | Serviço desligado lia como erro; `serve.ps1` abortava na migração |
| `d7b80c6` | Descoberta de porta e o aviso de declarado contra observado |
| `84ab027` | Chave rotulada da barra de ativos; desligar confirmado por verificação |
| `a290e31` | Servidor de desenvolvimento pelo painel, sem terminal |
| `72d8895` | Orquestração: um clique sobe ambiente e app, na ordem |
| `0e6d8df` | Sugestão de porta criava conflito; card ganhou "Abrir" |

### A segunda lição do dia

A primeira foi sobre código morto que parece proteção. A segunda é sobre onde os
defeitos moram: dos onze problemas desta sessão, **seis só apareceram rodando** —
`npm.CMD` e `PATHEXT`, `DETACHED_PROCESS` engolindo o log, caminho relativo
resolvido contra o diretório errado, interpretador do venv, sugestão de porta
duplicada, card sem botão de abrir. Nenhum deles é visível lendo o código, e
quatro deles o teste unitário também não pegaria, porque o defeito estava na
fronteira com o sistema operacional ou no que a tela oferece.

O que os pegou foi sempre a mesma coisa: subir o servidor de verdade, clicar no
browser de verdade, e olhar o que aconteceu.

---

## 2026-08-22 — Sessão 7: o painel deixa de só informar e passa a operar

Continuação direta da sessão 6, no mesmo dia. A pergunta que abriu foi "o que
podemos melhorar?", e a resposta veio de olhar o estado real em vez de opinar:
cobertura em 90%, 420 testes, e três buracos que o uso já tinha mostrado.

### O console que faltava

O painel sabia subir `npm run dev` e `uvicorn` desde a sessão 6, e a saída ia
para arquivo — mas **nenhuma tela mostrava esse arquivo**. Quando um servidor não
subia, o painel dizia "desligado" e a razão (`ModuleNotFoundError: No module
named 'duckdb'`, em texto claro, no disco) não tinha caminho até os olhos de
ninguém. Aconteceu de verdade, e a resposta exigiu um `curl`.

A aba Server mostra três coisas, nesta ordem de importância: o **comando antes
do clique**, com de onde ele veio ("declarado no devcockpit.yml", "deduzido do
package.json"); a **saída**, ao vivo e também depois da queda; e os controles,
que são consequência das duas primeiras. Vem antes de Docker na barra de abas
porque é a aba do dia a dia.

**Por que polling e não stream.** O backend lê o fim do arquivo sob demanda.
Fazer SSE custaria acompanhar o arquivo no servidor, e o ganho seria o atraso
cair de um segundo para zero — num texto que se lê em dezenas de segundos.

O visor substitui o texto em vez de anexar: a fonte é "as últimas N linhas", não
"o que mudou". Deduzir o delta comparando textos erraria em toda linha repetida,
e log de servidor repete muito. Só toca no DOM quando o texto mudou — senão cada
volta do relógio destruiria a seleção de quem estivesse copiando uma linha de
erro.

Junto vieram **Reiniciar** (o gesto mais repetido de um dia de backend, que
custava dois cliques e uma espera) e a **rotação do log** (o arquivo era aberto
em append e nunca truncado; a leitura já lê só o fim, então ninguém percebia —
o disco percebia).

### Cinco defeitos achados olhando a tela

Nenhum deles apareceria lendo o código.

**A sugestão de porta podia criar o conflito que ela existe para apontar.**
`_mismatches` sugeria a mesma porta observada para todos os serviços divergentes
do projeto: com o SmartDash declarando 3004 e 3005 e uma só porta sua no ar, a
tela oferecia "Usar 8000" nas duas linhas — inclusive na do banco. Aceitar as
duas colocaria backend e Database na mesma porta. Agora uma porta observada só
pode ser sugerida a um serviço, e com ambiguidade a divergência aparece **sem**
sugestão, com um botão "Corrigir". Dizer "está errado" sem chutar o certo é
honesto; chutar errado custa uma porta trocada à toa.

**Aplicação parada virava "porta errada".** A regra dizia: se o projeto tem
alguma porta escutando, todo serviço fora dela está com o número errado. Isso
ficou falso assim que porta de container passou a ser atribuída ao projeto — um
projeto com o banco em container e a aplicação desligada acusava o backend, que
só estava parado. Metade dos projetos está assim em qualquer momento do dia.
Agora só há divergência quando alguma porta do projeto escuta **sem que serviço
declarado nenhum a explique**.

**Porta de container não era atribuída a ninguém.** O `cwd` do Docker aponta
para a instalação dele, então nenhuma regra casava. Sobra o número: se um único
projeto declara aquela porta, foi o Compose dele que a publicou.

**"Port is already allocated" não dizia por quem.** A falha mais comum do
`compose up` e a mais inútil como o Docker a entrega. O painel agora nomeia o
culpado, usando o que a descoberta de porta já sabia.

**O card sabia ligar e não sabia abrir.** Depois de ligar, a próxima coisa que
se quer é ver, e "Abrir" só existia na página do projeto.

E o botão "Abrir" que eu acabara de adicionar **quebrou o rodapé do card**:
itens demais para uma fileira, o `flex-wrap` quebrava onde dava e o carimbo de
tempo ficava órfão no meio. Viraram duas fileiras de propósito — estado em cima,
ferramentas embaixo. De quebra, `.card__actions` mantinha `align-items: center`
de quando era uma linha só; virando coluna, aquilo passou a centralizar as
fileiras inteiras.

### O trilho abria o serviço com a chave vazia

`service_key: Field required`, num botão perfeitamente clicável. O trilho manda
a **chave** do serviço — contrato da rota, nunca a URL (decisão D-13) —, mas o
dashboard, que alimenta o trilho, devolvia `label`, `url`, `port` e não a chave.
Ia `undefined`.

Rótulo não serve no lugar: é texto para humano e pode repetir entre serviços do
mesmo projeto.

### Remover projeto deixava o servidor órfão

O processo sobrevive ao painel de propósito, e a linha em `dev_server` é o único
lugar onde o PID existe. Apagar o projeto apagava esse PID: sobrava um `uvicorn`
segurando a porta, alcançável só pelo Gerenciador de Tarefas, e sem caminho de
volta porque o projeto já tinha sumido da tela.

Falha em encerrar **não** trava a remoção: travar por um processo teimoso
deixaria o usuário com um projeto que ele não consegue tirar da tela — trocar um
problema por um pior.

### As três telas revisadas

**Activity era um muro.** Cento e sessenta e cinco linhas em ordem cronológica,
sem filtro, com `system.browser` repetindo dezenas de vezes e as falhas perdidas
no meio. A API aceitava `project_id`, `action` e `status` desde sempre — a tela é
que não perguntava. Ganhou filtros com "Só problemas" em primeiro lugar (é o
motivo número um de abrir a tela), agrupamento por dia, e falha com faixa na
borda. A ação virou português, com o nome técnico no tooltip.

**Settings não mostrava o que estava rodando.** Saber isso exigia abrir projeto
por projeto — e, no fim do dia, lembrar quais foram. Como o processo sobrevive a
um reinício do painel, esquecer um significa deixá-lo de pé até alguém notar.

**Dashboard respondia "quantos" e nunca "quais".** "2 Parados" era informação sem
saída. Agora cada número leva à lista já recortada; zero não vira link, porque
link para lista vazia é promessa quebrada. E o painel "Alterações pendentes: 0 —
nenhuma alteração conhecida" saiu da tela: o cache de Git só enche quando alguém
abre a aba Git, então ele ficava permanentemente ocupando um quarto da tela para
dizer "não sei".

### O dashboard deixa de ser só leitura

O gesto da manhã — "ligar o que vou usar hoje" — obrigava a sair da tela, ir a
Projects e procurar na grade. Um painel de operação sem operação é um relatório.
"Retomar trabalho" lista os que **não** estão no ar, com a chave de ligar na
frente.

### Gráficos, e o que a máquina deixa medir

Quatro medidores — processador, memória, disco, temperatura — e duas linhas de
três minutos. Um número responde "agora"; a linha responde "e antes?". Oitenta
por cento de memória constante há uma hora é rotina; subindo há cinco minutos é
aviso.

A tabela por servidor é o que só este painel sabe responder: o Gerenciador de
Tarefas mostra dezoito `node.exe` sem dono, e aqui cada árvore tem projeto,
porque foi o painel que a subiu. A medição soma a árvore inteira — `npm run dev`
é um `cmd.exe` que gasta zero e um `node` que gasta tudo, e medir só o pai
mostraria 0% num servidor fritando a máquina.

**Sobre a temperatura, com honestidade.** `MSAcpi_ThermalZoneTemperature`
responde "Acesso negado" sem privilégio administrativo, e o painel não pede
privilégio para nada. O que sobra é
`Win32_PerfFormattedData_Counters_ThermalZoneInformation`: a zona térmica ACPI,
que é a placa e não o núcleo. Marca bem menos que um HWMonitor, e chamá-la de
"CPU" seria mentira — o rótulo diz "zona térmica". Máquina sem zona exposta
mostra "—", nunca zero.

Duas cadências, porque os custos diferem por ordens de grandeza: `psutil`
responde processador, memória e disco em milissegundos; a temperatura exige
subir um `powershell.exe`, medido em **341 ms**, e por isso tem cache de trinta
segundos. Misturar faria a leitura barata pagar o preço da cara.

Gráficos em SVG escritos à mão. O painel não tem nenhuma dependência de
frontend, e trazer uma para desenhar uma linha e um arco seria caro. SVG e não
canvas porque as cores vêm do tema: trocar claro para escuro não exige
redesenhar nada.

### O conserto que quebrou o que consertava

O relógio do painel da máquina continuava batendo depois de sair do dashboard,
consultando a máquina a cada três segundos para desenhar num container fora do
DOM. Passou a perguntar ao próprio elemento se ainda está na página.

O conserto quebrou o painel: a primeira leitura acontece **antes** de o elemento
ser montado — quem chama monta a tela depois de pedir o painel —, então ele se
desligava na partida e a tela ficava para sempre em "Lendo o estado da
máquina…". Daí a ressalva de só desligar depois de ter estado montado alguma vez.

Verificado interceptando as requisições: três chamadas em oito segundos no
dashboard, zero em doze segundos fora dele.

### Números

426 testes passando, 1 pulado. `ruff check` limpo. Desde o log da sessão 6:
31 arquivos, +2974 e −130 linhas. Na branch inteira: 65 arquivos, +8162 e −252.

| Commit | Entrega |
|--------|---------|
| `41918fc` | Aplicação parada virava divergência; porta ocupada não dizia por quem |
| `a659df1` | Aba Server, com log ao vivo, Reiniciar e rotação |
| `8f5886b` | Atalhos descobríveis com `?`; portas do dashboard com estado |
| `4da6ebd` | Rodapé do card em duas fileiras, alinhado à esquerda |
| `dd0df42` | Abrir pelo trilho falhava por falta da chave do serviço |
| `794dc51` | Remover projeto deixava o servidor órfão |
| `1e0fc87` | Activity com filtros, por dia, falha em destaque |
| `918bce7` | Capturas de verificação fora do repositório |
| `eeb2e9c` | Settings mostra os servidores no ar |
| `2461e24` | Números do dashboard levam à lista; painel vazio saiu |
| `aa7d923` | Dashboard opera, e mostra o estado da máquina |

### Três correções que precisei fazer no meio do caminho

Vale registrar porque são o tipo de erro que se repete:

1. **Afirmei que havia processo órfão** segurando a porta 8000. Não havia: o pid
   com caminho do Python global era filho do processo do `.venv`, e no Windows o
   `python.exe` de um ambiente virtual é um redirecionamento para o base. O
   `cmdline` de um processo em venv **não** identifica o ambiente que ele usa.
2. **Afirmei que `localhost:8137` no dashboard era texto morto.** Era link com
   `target="_blank"` desde antes.
3. **Commitei capturas de tela** junto com a Activity, por um `git add -A`
   descuidado.

Os três têm a mesma raiz: concluir antes de conferir. Nos três, conferir custava
menos de um minuto.

### A lição do dia

A das sessões anteriores foi sobre onde os defeitos moram. Esta é sobre o que os
esconde: **quase todo defeito desta sessão era a tela sabendo de algo e não
dizendo**. A API aceitava filtros e a Activity não perguntava. A descoberta de
porta sabia quem ocupava a porta e o erro do Compose não usava. O log existia em
disco e nenhuma tela o abria. Os atalhos funcionavam e nada os anunciava. Os
números do dashboard sabiam a resposta e não levavam a ela.

Nenhum desses é bug de lógica. São informação represada por falta de um caminho
— e o custo de abrir cada caminho foi pequeno perto do que ele destrava.

### Continua com você

- [ ] `git_service` está com 47% de cobertura, o menor do projeto — `commits`,
      `branches` e `remotes` não são exercitados
- [ ] duas tabelas com migração que nada escreve nem lê (`HealthSnapshot`,
      `GitRepository`) e duas configurações nunca consultadas
      (`activity_retention_days`, `timeout_scan`). Implementar ou apagar;
      manter é o pior dos três
- [ ] zero teste de frontend, contra 4600 linhas de Python a 90% — e os últimos
      defeitos foram todos de frontend
- [ ] declarar `run:` no `devcockpit.yml` do `zapcrm`
- [ ] a porta declarada do `Dashdate · Backend` é 3002 e ele está no ar em 8123
- [ ] clicar em VS Code e confirmar que a janela vem para frente (pendente
      desde 22)
- [ ] conferir a aba Docker com o Docker Desktop desligado (pendente desde 21)
- [ ] decidir se a branch `varredura/bugs-e-organizacao` entra na `main` — são
      21 commits fora dela

---

## 2026-08-22 — Sessão 8: o painel para de afirmar o que não sabe

Continuação direta da sessão 7. Abriu com "as portas do servidor estão
confusas" e terminou com um projeto que não subia nem desligava funcionando.
Nove commits, 456 testes, cobertura em 88%.

O fio que costura tudo: **o painel afirmava coisas que não tinha como provar.**
Não por lógica errada — por nunca ter distinguido evidência de palpite.

### "no ar" afirmava dono sem prova

A tela dizia `8000 · SmartDash · Backend · no ar`. O uvicorn do SmartDash tinha
morrido, os dois containers dele estavam `exited`, e quem ocupava a 8000 era
`plataformadeingressos-web-1` — container de outro projeto inteiro.

A causa foi uma regra da sessão anterior. Porta publicada por container não casa
por diretório: o `cwd` do Docker aponta para a instalação dele. Para não gerar
alarme falso, a atribuição passou a usar o número — um único projeto declarando
aquela porta seria o dono. Resolveu o alarme falso e criou um pior: **inferência
apresentada como fato.**

A distinção que faltava: `cwd` e `cmdline` **provam**; o número declarado
**infere**. Quem afirma "está no ar" precisa de prova. Quem mostra "ocupada por
alguém" pode se contentar com palpite, porque não afirma dono. Duas marcas, não
uma. Das quatro portas verdes na máquina, só uma tinha prova.

Essa distinção reapareceu três vezes depois, em lugares diferentes. Era o
defeito de fundo da sessão inteira.

### Comando e cadastro discordando da porta

O `devcockpit.yml` do SmartDash mandava `--port 8000`; o serviço estava
cadastrado em 3001. O painel subia em 8000 e verificava 3001 — encontrava
silêncio e dizia "fora do ar" para algo que estava no ar. O log do projeto tinha
a prova a cada tentativa: `Uvicorn running on http://127.0.0.1:8000`.

O sintoma não aponta para a causa. O servidor sobe, o log não acusa erro, os dois
números estão certos cada um no seu arquivo — só não são o mesmo número. E os
planos detectados não caem nisso: `plan_from_python` recebe a porta declarada e a
injeta. Só o `run:` escrito à mão é literal.

`RunPlan.port` lê a porta do argv nas três formas que aparecem na prática e
compara com a porta do serviço que `run.service` declara fornecer. Onde o painel
se cala, de propósito: comando sem porta legível (`npm run dev` decide dentro do
script), manifesto sem `run.service` (não há contra o que comparar), `-p` fora da
lista de bandeiras (em muito comando ele é outra coisa).

### "Sugerir livre" sugeria porta ocupada

O rastro no banco: `db` da PLATAFORMA em 3004, `dashdate` em 3005, `backend` do
Dashdate em 3006. Três sequenciais logo após as declaradas 3000–3003 — a
assinatura de "Sugerir livre" clicado três vezes.

O botão prometia a menor porta livre e entregava a menor que **nenhum projeto do
painel declarava**. Postgres nativo, container de outro projeto: invisível para
ele. Pior que conflito comum, porque conflito comum aparece — este só na falha do
próximo `up`, ou nunca, com o serviço offline para sempre numa porta onde jamais
esteve. Era a "confusão das portas" relatada.

A tela também recarregava só no botão, sendo metade dela estado vivo. Passou a
reler a cada 6 s, calando-se com edição aberta (redesenhar apagaria o número
digitado), aba escondida e tela trocada.

### Importar `app.main` subia a aplicação de produção inteira

`app = create_app()` no corpo do módulo. Um `import app.main` — o que toda a
suíte faz — apontava o logging para `logs/devcockpit.log`, lia os roots reais e
abria o banco de produção.

Isso atrapalhou a própria investigação: procurei a causa da queixa numa lista de
erros que em boa parte era ficção da suíte, com tracebacks encenados no mesmo
formato dos reais. A construção passou para o acesso ao atributo (PEP 562);
`uvicorn app.main:app` não muda, porque o uvicorn faz `getattr`.

### A detecção não contava o que sabia

Duas falhas encadeadas, e a segunda escondia a primeira.

`parse_published_port` lia `"5432:5432"` e desistia de uma porta escrita como
variável. A PLATAFORMA escreve as duas portas assim, então a detecção devolvia
zero serviços para ela sem dizer que não soube ler — indistinguível de um projeto
sem Compose. Agora resolve como o Compose resolve: `.env` primeiro, valor de
reserva depois.

E `_apply_services` pulava serviço já cadastrado — calado. "Edição manual vence
sempre" está certo e continua valendo; faltava o outro lado: **não sobrescrever
não é motivo para não contar**. `port_drift` relata sem aplicar.

A primeira versão dessa checagem acusou os três projetos da máquina de uma vez,
todos com `detected: 8000` — o padrão do uvicorn, não leitura de arquivo nenhum.
`SuggestedService.port_source` separa `"file"` de `"convention"`; só arquivo
contradiz cadastro. Mesmo erro da manhã, cometido de novo em outro lugar.

### "Desligar" decidia pelo plano, não pelo estado

Relatado no Dashdate. `down()` perguntava se o projeto *tem* aplicação separada
e, tendo, parava a aplicação — inclusive quando ela já estava parada. O Dashdate
tem plano de `uvicorn`, o `uvicorn` estava parado, e quem atendia era o
container. O clique parava algo já parado e respondia sucesso.

E o modo Docker era pior: `down()` devolvia a string `"docker"`, **ninguém
executava `compose down`**, e o cliente anunciava "ambiente derrubado". Uma
resposta de sucesso descrevendo algo que não aconteceu é pior que um erro — o
erro pelo menos manda olhar.

Agora decide pelo estado, executa o que decide (job, como o `/up`), e responde
`"nothing"` quando não havia nada — que é diferente de "o botão não funcionou".

### Encerrar processo que o painel não subiu

A tela de Ports já encerrava órfãos. Faltava o vizinho: processo em root
permitido, numa porta que um projeto **declara**, que o painel não subiu. O
"Desligar" do card não alcança esses, porque desligar é encerrar o que o painel
iniciou.

Duas guardas que só apareceram rodando na máquina. **O painel se oferecia para
ser encerrado** — roda em root permitido, na porta que declara, e não foi ele que
se subiu. **Porta efêmera não é serviço** — a primeira execução ofereceu matar um
`node.exe` na 18663 e um `bun.exe` na 58176, ferramentas rodando dentro da pasta.
Estar no diretório não faz de um processo o servidor do projeto.

### "online" dizia que alguém respondeu, nunca quem

Relatado no SmartDash: tentar desligar várias vezes e o card insistir em
"1/2 online". O SmartDash já estava desligado — containers removidos, `uvicorn`
parado. Quem respondia na 5432 era o `ecommerce_postgres`, container de um
projeto nem cadastrado aqui.

A verificação de saúde abre um socket e pergunta "tem alguém aí?". Nunca soube
perguntar "quem?" — e as duas perguntas divergem assim que dois projetos
compartilham um número. Era o mesmo defeito da manhã sobrevivendo na coluna de
estado dos serviços.

O primeiro corte mirou largo demais: porta de container nunca casa por diretório,
então **todo** serviço em Compose virava suspeito. Num fluxo baseado em Docker
isso é ruído puro — um aviso que aparece sempre não avisa nada. Faltava a
pergunta que o Docker responde de graça: existe container **deste projeto**
publicando esta porta? Se existe, é prova.

### O SmartDash, ponta a ponta

O compose dele publicava 5432 (ocupada pelo `ecommerce_postgres`) e 8000
(ocupada pela PLATAFORMA). Dois containers não publicam o mesmo número — por isso
não subiam. Passou a publicar em 5435 e 3001, por variável, com a porta interna
intacta.

Com os containers subindo, apareceu o defeito seguinte, do projeto e não do
painel: `docker/Dockerfile.backend` copiava só `backend/` e `frontend/`, e o
startup roda `alembic upgrade head` lendo `alembic.ini` da raiz e
`database/migrations`. O container morria em `CommandError: Path does not
exist`, e o `compose up` **reportava sucesso** — o container é criado antes de o
processo falhar.

Resultado: **SmartDash · 2/2 online · Ligado**, de um projeto que não subia nem
desligava.

### Erros meus nesta sessão

- suspeitei de vazamento do painel ao ver 17 processos `runserver`; as cadeias
  extras tinham `powershell.exe` como pai — subidas manuais. Corrigido antes de
  virar afirmação;
- `git add -A` levou `Dockerfile`, `docker-compose.yml` e `.dockerignore` do
  usuário para dois commits. Removidos com `--amend` nas duas vezes;
- `ruff format app/services/` reformatou seis arquivos não relacionados que
  entraram num commit de feature;
- o falso positivo do `port_drift` (todos os projetos acusados) e o do
  `unmanaged` (portas efêmeras) foram **o mesmo erro** que eu tinha acabado de
  corrigir, cometido de novo. Só apareceram porque rodei na máquina real.

### A lição do dia

A sessão 7 foi sobre informação represada por falta de caminho. Esta é sobre o
oposto: **informação afirmada sem lastro**. "No ar", "online", "ambiente
derrubado", "nada mudou" — quatro afirmações que a interface fazia sem ter como
sustentar, e cada uma custou ao usuário a confiança na tela seguinte.

O padrão da correção foi sempre o mesmo, e vale guardar: separar o que se
**prova** do que se **infere**, e deixar cada um dizer só o que aguenta. Prova
afirma; inferência sugere; ausência de dado se cala. As três vezes em que errei
foram por esquecer a terceira — transformar "não sei" em acusação.

E o corolário: **um aviso que aparece sempre não avisa nada.** O `port_drift`
acusando os três projetos e o `unmanaged` oferecendo matar ferramentas eram
tecnicamente corretos e praticamente inúteis. Precisão importa tanto quanto
correção.

### Continua com você

- [ ] duas tabelas sem escrita nem leitura (`HealthSnapshot`, `GitRepository`) e
      duas configurações nunca consultadas (`activity_retention_days`,
      `timeout_scan`). A primeira significa log de atividade crescendo sem
      limite. Implementar ou apagar; manter é o pior dos três
- [ ] `git_service` a 47%, o menor do projeto (total em 88%)
- [ ] zero teste de frontend, contra ~5000 linhas de Python testadas — e os
      defeitos de interface continuam sendo a maioria
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` do DevCockpit estão
      untracked na raiz; decidir se entram
- [ ] o SmartDash usa SQLite no `.env` local e sobe um Postgres no Compose que a
      aplicação local ignora — o serviço `db` cadastrado pode ser ruído
- [ ] as três edições no SmartDash (compose, Dockerfile, cadastro) não foram
      commitadas: o projeto vive dentro de um repo maior com 24 arquivos de
      outros projetos modificados
- [ ] a branch `varredura/bugs-e-organizacao` está com 30 commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 — Sessão 9: prioridades revisadas e o painel ganha memória

Duas coisas nesta sessão: reordenar o que estava pendente e atender ao pedido de
gráficos de análise no dashboard. As duas se encontraram num ponto só — a tabela
morta que o backlog mandava "implementar ou apagar" era exatamente a fonte de
dado que o gráfico pedido precisava.

### As prioridades

A ordem passou a ser por dano, não por esforço, e está no topo do
`PROJECT_STATUS.md`: gráficos (P0), retenção (P1), higiene de repositório (P2),
as duas verificações manuais pendentes desde 21/08 (P3), teste de frontend e
`git_service` (P4), o serviço `db` do SmartDash (P5).

### `health_snapshot` deixa de ser schema sem escrita

A tabela existia desde a Fase 4. O poller media a cada 30 s e **jogava fora**. O
painel respondia "agora" e nunca "e antes?".

A política de escrita não é gravar tudo nem gravar só mudança:

* mudança de estado grava sempre — o minuto da queda vale mais que as duas horas
  de pé que vieram antes;
* sem mudança, grava a cada cinco minutos. Sem isso, uma semana estável teria um
  ponto só, e o gráfico não distinguiria "de pé o tempo todo" de "ninguém olhou".

Gravar todo ciclo seriam 2.880 linhas por serviço por dia para repetir a mesma
informação 2.879 vezes.

### Disponibilidade ponderada por tempo, e cobertura declarada junto

Histórico de health é **amostragem**, não registro de fato. Contar amostras
online sobre o total daria a três amostras o mesmo peso de um dia inteiro
medido. O uptime é ponderado pelo tempo que cada amostra cobre, com teto de dez
minutos por amostra: o que passa disso vira buraco de cobertura, não
disponibilidade.

Por isso `coverage_pct` viaja junto do número, e a tela deixa de colorir a barra
quando a cobertura é menor que 5% do período — 0% em vermelho a partir de dez
minutos medidos numa janela de duas semanas acusaria uma queda que ninguém
observou. É a regra da sessão 8 aplicada a um dado novo: prova afirma, amostra
rala sugere, ausência se cala.

### O defeito que só apareceu com dado real

Rodando contra a máquina, as primeiras amostras gravadas traziam
`latency_ms: 2657` em serviços `OFFLINE`. Não era latência do serviço: era o
tempo até o verificador desistir. Entrando na série, a latência "pioraria"
justamente quando o serviço caísse — o gráfico mediria a paciência do
verificador. Agora só amostra `ONLINE` alimenta latência e percentil.

### Retenção, enfim

`activity_retention_days` estava configurado desde a Fase 0 e nunca era lido: o
log de auditoria crescia sem limite num banco que mora na máquina do usuário.
Com o histórico de health passando a escrever, seriam duas tabelas assim. A poda
roda dentro do poller, de hora em hora, com retenção separada por tabela.

`timeout_scan` era a terceira configuração decorativa. Virou teto do job de
varredura: `submit_callable` aceita `timeout_s`, e o job que estoura termina
como `TIMEOUT` liberando a chave — antes ficaria `RUNNING` para sempre,
recusando toda varredura seguinte com 409 até o servidor reiniciar.

### Os gráficos

Cinco painéis no fim do dashboard, carregando por conta própria depois da tela
(o orçamento de 500 ms é do dashboard, não do histórico):

* **Atividade** — colunas empilhadas por dia, divididas por desfecho, com dias
  vazios presentes: omitir dia parado emendaria uma sexta-feira silenciosa na
  segunda seguinte;
* **Disponibilidade** — uptime por serviço, latência ao longo do tempo com os
  buracos preservados, p95;
* **Ações mais executadas** — volume, taxa de erro e p50/p95 de duração. A taxa
  vem ao lado do volume que a sustenta: 100% de erro em uma execução é anedota;
* **Horário de trabalho** — 24 células, uma por hora;
* **Stack dos projetos** — tecnologias por número de projetos.

Sem biblioteca de gráfico, como o resto do painel: SVG e HTML à mão, cores do
tema. `charts.js` ganhou `stackedColumns`, `lineSeries` (escala própria e
`null` que interrompe a linha) e `hourStrip`.

### Verificação

475 testes passando (19 novos), cobertura 89%, `ruff check` limpo. Os gráficos
foram renderizados fora do browser contra a API real, com um DOM mínimo, para
provar que os cinco painéis montam com dado de verdade — não substitui olhar a
tela, mas pega erro de execução antes de você abrir.

### Continua com você

- [ ] **Ctrl+F5** e olhar os gráficos: a aba aberta tem o JS antigo
- [ ] zero teste de frontend continua sendo o maior buraco, e acabou de crescer
      cinco painéis
- [ ] `git_service` a 47%, o menor do projeto
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] as três edições no SmartDash não commitadas
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 — Sessão 10: o DevCockpit vira programa

Pedido: "vamos fazer um executável". Três escolhas definiram o resto — pasta
com `.exe` (não arquivo único), dados ao lado do executável (não em
`%LOCALAPPDATA%`), console visível abrindo o navegador.

### O que o executável precisa fazer que o repositório não precisava

`uvicorn app.main:app` pressupõe repositório clonado, ambiente virtual, `.env`
copiado, `alembic upgrade head` rodado à mão e `configs/roots.yml` editado. Um
programa aberto com dois cliques não tem nada disso. `app/launcher.py` faz cada
um desses passos, nesta ordem: descobre a pasta de dados, semeia a
configuração, migra, escolhe a porta, sobe e abre o navegador.

Dois pontos mereceram cuidado:

* **os recursos e os dados moram em lugares diferentes.** Congelado, o código
  roda de um diretório temporário (`sys._MEIPASS`) que some ao fechar; frontend
  e migrações vivem lá, e banco, log e configuração precisam viver ao lado do
  `.exe`. `PROJECT_ROOT` passou a apontar para os recursos, e o launcher
  entrega os caminhos de dados por variável de ambiente, absolutos, com
  `setdefault` — quem já configurou continua mandando;
* **`roots.yml` não pode ser cópia.** O arquivo do repositório aponta para o
  Desktop de quem desenvolveu. Ele é escrito a partir do perfil de quem está
  executando, e só com as pastas que existem: allowlist para diretório
  inexistente produz erro de varredura em vez de lista vazia honesta.

### O defeito que o teste pegou, e que ninguém veria na primeira tela

A porta 8765 pode estar ocupada, então o launcher pega a próxima livre. Só que
a porta não é apenas onde o servidor escuta: ela entra na lista de origens
aceitas em requisição que altera estado (defesa D5). Subindo em 8801 com as
`Settings` ainda dizendo 8765, a tela carregava perfeitamente e **todo botão
devolvia 403** — o pior jeito de quebrar, porque parece que funciona.

Achado com um POST contra o executável recém-gerado, não lendo código. A
correção é uma linha (`DEVCOCKPIT_PORT` antes de qualquer leitura de settings)
e tem teste que falha sem ela.

### Detalhes que só aparecem rodando

* console do Windows herda codepage 850/1252, e "migrações" saía com
  caracteres trocados. `SetConsoleOutputCP(65001)` mais reconfiguração dos
  fluxos;
* falha na subida fecharia a janela antes de a mensagem ser lida — em erro, e
  só quando há alguém do outro lado, o launcher espera um Enter;
* o build apaga `data/`, `logs/` e `configs/` de dentro de `dist` antes de
  empacotar: um banco esquecido ali viajaria com os projetos da minha máquina
  para quem recebesse a pasta.

### Medições

Pacote de 39,7 MB. Primeira abertura em pasta nova: 3,4 s (inclui migração e a
varredura do antivírus nos arquivos novos). Aberturas seguintes: 1,4 s. Testado
copiando a pasta para fora do repositório e subindo de lá — cadastro de projeto
funcionando, detecção de stack correta, `/api/analytics` respondendo.

483 testes passando (8 novos), `ruff check` limpo.

### Continua com você

- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques e conferir o
      caminho completo: navegador abre sozinho, painel carrega, um botão que
      escreve (fixar projeto, por exemplo) funciona
- [ ] decidir se `dist/` fica fora do Git (está, hoje) ou se as versões viram
      release versionada
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 — Sessão 10, continuação: três ajustes depois de usar

Nada aqui foi planejado; os três vieram de olhar a tela com o que tinha acabado
de ser construído.

### "Falha na requisição (404)" no painel de análise

O arquivo novo estava no disco e a rota existia. O servidor no ar tinha subido
às 23:20 — antes de `/api/analytics` ser escrita — e seguia com o código antigo
em memória. Reiniciar resolveu.

O que ficou do episódio não é a correção, é a mensagem. `Falha na requisição
(404)` mandava procurar no lugar errado: sugere dado ausente, quando o problema
é processo desatualizado. Recarregar a página não resolve, e é a primeira coisa
que qualquer um tenta. O painel agora distingue o 404 e diz o que fazer —
reiniciar o servidor, não recarregar a aba.

Vale como padrão: **erro de rota inexistente num painel novo quase sempre é
servidor velho.** É o modo de falhar mais provável de qualquer feature nova
neste projeto, porque o servidor é de vida longa por decisão (`serve.ps1`).

### Dois painéis saíram do dashboard

A pedido: "Disponibilidade" e "Ações mais executadas". Ficaram três — Atividade,
Horário de trabalho e Stack dos projetos.

Junto foram as funções que só existiam para eles (`disponibilidade`, `acoes`,
o helper `duracao`), o gráfico `lineSeries` de `charts.js` e o CSS `.serie`.
Sobrariam como código morto, e este projeto já tem um item de backlog inteiro
sobre o custo de manter o que ninguém usa.

O que **não** saiu, de propósito: o backend continua calculando `uptime` e
`actions`, e o poller continua gravando `health_snapshot`. Parar a gravação
devolveria a tabela ao estado que a sessão anterior corrigiu — schema sem
escrita — e sem histórico acumulado o painel não teria como voltar.

### O executável estava velho

Empacotado antes da remoção dos painéis. Reempacotado e conferido a partir de
uma cópia fora do repositório: `/api/health`, a página e `/api/analytics`
respondendo 200, e o JS servido pelo `.exe` sem vestígio dos painéis retirados.

A lição é operacional e vale anotar: **o executável não se atualiza sozinho.**
Toda alteração de código exige `scripts/build_exe.ps1` de novo, senão a pasta
`dist` mostra uma versão do painel que não existe mais no repositório.

### Continua com você

- [ ] Ctrl+F5 na aba aberta e conferir os três painéis que sobraram
- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques: navegador abre
      sozinho, painel carrega, um botão que escreve funciona
- [ ] decidir se `dist/` fica fora do Git (está) ou vira release versionada
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 (manhã) — Sessão 11: a porta que o Docker levou

O painel não subia. O log dizia tudo, e nada:

```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8765)
```

Quem estava escutando na 8765 era o `com.docker.backend.exe`. Ele tomou a porta
durante a noite, com o DevCockpit parado — nenhuma configuração mudou de lado
nenhum. Foi o mesmo padrão de sempre neste projeto: a máquina é compartilhada, e
o que estava livre ontem pode não estar hoje.

### O defeito que apareceu enquanto eu contornava

Subi em 8766 para destravar. A tela carregou, e o primeiro POST devolveu **403
`Origin não autorizado`**.

`serve.ps1 -Port` passava a porta ao uvicorn e não às `Settings`. A porta não é
só onde o servidor escuta: ela compõe a lista de origens aceitas em requisição
que altera estado (defesa D5). Subir em 8766 com as `Settings` dizendo 8765
carrega a tela inteira e recusa todo botão.

É **exatamente** o mesmo defeito que o executável teve ontem, corrigido ontem,
no arquivo ao lado. Eu consertei o launcher e não olhei para os dois scripts que
faziam a mesma coisa. Anotado como padrão: quando a correção for "propagar a
porta escolhida", procurar todos os pontos que escolhem porta — hoje são três.

### Ceder em vez de disputar

Decisão sua: fallback automático nos dois scripts. `serve.ps1` e `dev.ps1`
procuram a primeira porta livre a partir da 8765, exportam `DEVCOCKPIT_PORT` e
imprimem qual usaram.

Um efeito colateral precisou de conserto junto: `Get-ServerProcesses` casava por
`--port 8765` na linha de comando. Com fallback, o servidor podendo estar em
8766 faria `-Status` responder PARADO e `-Stop` não parar nada — com o painel de
pé o tempo todo. A busca passou a ignorar a porta, e a porta real é lida da
linha de comando do processo encontrado.

Verificado: `-Status` achou o servidor em 8766 sem receber a porta, `-Stop`
parou, a subida sem argumento caiu sozinha na 8766 avisando, e o POST que antes
dava 403 devolveu 409 `PROJECT_ALREADY_EXISTS` — passou pelo guard.

### Continua com você

- [ ] o painel de hoje está em **http://127.0.0.1:8766** (8765 é do Docker)
- [ ] Ctrl+F5 e conferir os três painéis de análise
- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques
- [ ] decidir se a porta padrão muda de vez (hoje: 8765 com fallback)
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 (manhã, parte 2) — Sessão 12: o painel vira aplicativo

Três pedidos numa linha: atalho no Desktop, porta estável e "uma janela
flutuante, como um sistema interno mesmo". O terceiro mudou o que o executável é.

### Antes de tudo: tirar o programa de dentro de `dist`

Você estava rodando o executável de `dist/DevCockpit`, e o banco com os 36
projetos varridos vivia lá dentro. `build_exe.ps1 -Clean` apaga essa pasta.
Um rebuild teria levado o cadastro inteiro junto, sem aviso.

O programa foi para `%USERPROFILE%\DevCockpit`, e o script ganhou `-Install`:
substitui só o `.exe` e o `_internal/`, nunca `data/`, `logs/` e `configs/`.
Atualizar não pode custar o que o usuário cadastrou.

### Dois painéis, dois bancos

A tela de Ports que você mandou não era do servidor de desenvolvimento: era do
executável, com 36 projetos. O do repositório tinha 3. Consequência direta de
"dados ao lado do executável" — desenho correto, efeito confuso quando os dois
rodam ao mesmo tempo. Ficou um só de pé: o instalado, na 8790.

### Janela nativa

WebView2 via `pywebview`. Sem barra de endereço, sem abas, ícone próprio na
barra de tarefas, título "DevCockpit". Fechar a janela encerra o servidor — um
programa que continua rodando invisível depois de fechado é a receita da segunda
instância brigando pela porta, que é exatamente o problema que passamos a manhã
resolvendo.

O servidor mudou de thread: o laço de mensagens do Windows exige a thread
principal para a janela, então o uvicorn foi para uma secundária, com
`install_signal_handlers` desligado (`signal.signal` só funciona na principal).

### O preço do console, cobrado na hora

Empacotei com `console=False` e o app subiu... sem servidor. Janela abrindo
contra o nada, e **nenhuma mensagem em lugar nenhum**.

Causa: sem console, `sys.stdout` é `None`, e a configuração de log padrão do
uvicorn monta um `StreamHandler` sobre `ext://sys.stdout`. Ela levanta antes de
a porta abrir, a thread morre, e a exceção não tinha para onde ir.

Três correções, e as três são sobre o mesmo tema — não trocar visibilidade por
aparência:

* `log_config=None` quando não há `stdout` (o log da aplicação já vai para
  arquivo, ao lado do executável);
* a thread do servidor guarda a exceção que a matou, em vez de morrer calada;
* `_falhar()` mostra caixa de diálogo do Windows quando não há console, e
  `_dizer()` não escreve em `stdout` inexistente — um `print` solto derrubaria a
  subida por causa da mensagem, não do trabalho.

Eu tinha escrito, ontem, que o console visível era proposital porque "é onde
aparece o motivo quando o servidor não sobe". Trocar isso por uma janela exigia
repor a visibilidade por outro caminho. Custou uma reconstrução para lembrar.

### Ícone

Gerado por código (`scripts/make_icon.py`, Pillow) e não versionado como binário
opaco: arco de gauge nas cores dos tokens do tema, com o ponto verde de "no ar".
Trocar a identidade é trocar duas constantes e rodar de novo.

### Verificado

Atalho no Desktop apontando para `%USERPROFILE%\DevCockpit\DevCockpit.exe
--port 8790`, ícone próprio. Aberto pelo atalho: `health` 200, janela com título
"DevCockpit", 19 processos do WebView2. Fechando a janela: processo encerrado e
porta liberada. 483 testes passando, `ruff` limpo.

### Continua com você

- [ ] abrir pelo atalho e dizer se a janela está no tamanho certo (1360x880)
- [ ] o cadastro do próprio DevCockpit agora aponta para a 8790
- [ ] os 5 "conflitos" de porta da tela Ports são portas padrão declaradas por
      vários projetos; só doem entre projetos que sobem juntos. Decidir se vale
      renumerar (mexe no arquivo de cada projeto, não só no cadastro)
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

## 2026-08-23 (tarde) — Sessão 13: a tela que fugia e as portas sem lastro

### A tela pulando para Ports

Relato: "a página atualiza e vai direto pro módulo de Ports". Bug meu, e do tipo
que a arquitetura convidava.

O `<main id="view">` é o **mesmo elemento** em todas as rotas — só o conteúdo
dele é trocado. A tela Ports protegia seu timer de recarga com
`container.isConnected`, que por isso nunca é falso. O timer sobrevivia à
navegação e, a cada seis segundos, redesenhava Ports por cima da tela aberta.
A assinatura estava no log do painel: 146 chamadas a `/api/services/ports`.

Corrigido no roteador, não na página: `aoSairDaRota()` registra o que precisa
parar, e o roteador limpa antes de renderizar a próxima rota. A página que sabia
o que criar não tinha como saber que a rota mudou; quem sabe é quem troca.

Vale como regra para esta base: **`isConnected` não é sinal de tela ativa quando
o container é reaproveitado.** Qualquer timer, observador ou relógio de página
passa pelo roteador.

### "Dificuldade de abrir o ambiente"

O ambiente estava inteiro no ar. O painel é que olhava para as portas erradas.

No PLATAFORMA DE INGRESSOS: `db` cadastrado em 3010 e `web` em 3019, enquanto o
projeto declara 5434 e 8000 no `docker-compose.yml` e no `.env`. O painel subiu
o Django certo em 3002, e ainda assim mostrava o projeto meio desligado — com o
"Abrir" do web levando a uma porta onde nunca houve nada.

A varredura geral achou o mesmo padrão em mais cinco serviços, todos na faixa
3007–3018 — a assinatura do "Sugerir livre" antigo, corrigido na sessão 6, cujos
números errados continuaram gravados:

```
kiteasy            app        3018 -> 3000
ZapCRM             zap-crm    3015 -> 5000
MonitorHub System  postgres   3013 -> 5433
ZAPBOT             db         3012 -> 5433
Dashboard-contabil dashboard  3007 -> 8000
```

Mais um serviço duplicado: `kiteasy` tinha `app` e `frontend` na mesma 3000, e o
painel contava isso como conflito de porta — tecnicamente certo, praticamente
ruído, porque era o mesmo projeto consigo mesmo.

Depois da correção: zero divergência entre cadastro e arquivo, zero divergência
entre cadastro e o que está escutando, e três conflitos que são reais e
esperados (5000, 5433 e 8000 declarados por dois projetos cada — só doem se os
dois subirem juntos).

### A lição

Um defeito corrigido no código não desfaz o que ele gravou. O "Sugerir livre"
parou de errar em 21/08; os números que ele errou ficaram no banco por dois
dias, e apareceram como "não consigo abrir o ambiente". **Correção de bug de
escrita pede varredura do que já foi escrito.**

### Continua com você

- [ ] abrir o painel e confirmar que a tela não pula mais para Ports
- [ ] os três conflitos restantes (5000, 5433, 8000) são reais: decidir se
      renumera algum, lembrando que isso mexe no arquivo do projeto
- [ ] zero teste de frontend — este bug seria pego por um teste de rota
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

## 2026-08-23 (tarde, parte 2) — Sessão 14: "quem está nessa porta?"

Relato: "subiu 3 projetos ativos sem eu pedir" e "não quer desligar".

Primeiro o que **não** aconteceu: nada subiu. Os processos vivos eram o Django
que você mesmo ligou às 11:43 e os containers da PLATAFORMA, de pé desde as
08:03. O que mudou foi o painel passar a **enxergar** — e a enxergar errado.

Foi a minha varredura de portas que expôs isso. Ao alinhar os cadastros aos
arquivos dos projetos, três serviços passaram a declarar portas que outra coisa
já ocupava: 8000 (container da PLATAFORMA) e 5433 (Postgres nativo). A
verificação de saúde abre um socket e pergunta "tem alguém aí?" — nunca soube
perguntar "quem?". Resultado: MonitorHub, ZAPBOT e Dashboard-contabil apareceram
rodando sem nunca terem subido.

Troquei um sinal errado por outro. O primeiro dizia "desligado" com o projeto de
pé; o segundo dizia "ligado" com o projeto parado. O segundo é pior: leva a
pessoa a tentar desligar o que nunca ligou — e nada acontece, porque não há o
que parar.

### A causa de fundo, e o conserto

A atribuição de porta de container era um palpite: *se um único projeto declara
este número, é dele*. A regra se cala exatamente quando dois projetos declaram a
mesma porta padrão — 8000, 3000, 5432 —, que é o caso comum.

O Compose grava o diretório do projeto em cada container
(`com.docker.compose.project.working_dir`). Perguntar ao Docker troca palpite
por fato:

* `ContainerPortsService` lê `docker ps --format '{{json .}}'` uma vez a cada
  vinte segundos e monta `porta publicada -> diretório do projeto`;
* a descoberta ganhou `matched_by="container-label"`, que conta como **prova**
  — diferente de `container`, que segue sendo dedução pelo número;
* o poller alimenta a descoberta com esse mapa.

E o dashboard deixou de afirmar o que não sabe: cada serviço que responde vem
com `proven` e, quando não há prova, com a explicação de quem está na porta. A
contagem "Rodando" conta só os provados; o card do projeto e o trilho lateral
seguem a mesma regra; a linha da tabela mostra "porta ocupada" no lugar do
selo verde.

Na máquina real, depois do conserto: **1 rodando** em vez de 5, com
"Dashboard-contabil: quem ocupa a porta é wslrelay.exe, do PLATAFORMA DE
INGRESSOS" escrito na tela em vez de um selo verde mentindo.

### O outro "não desliga"

Ligar e desligar mudavam o banco e o processo, mas não o cache do dashboard, que
dura mais que a paciência de quem clicou: o botão respondia sucesso e a tela
seguia dizendo o contrário. Agora `start`, `stop` e `restart` invalidam o cache
do dashboard e o health do projeto.

### A lição

A sessão 8 estabeleceu a regra — prova afirma, inferência sugere, ausência se
cala — e a aplicou na tela de Ports e na de Serviços. O dashboard ficou de fora,
e foi por ali que o mesmo defeito voltou dois dias depois. **Regra aplicada em
três telas de quatro é regra que ainda não existe.**

### Continua com você

- [ ] o painel foi reempacotado e reaberto na 8790; confira o dashboard
- [ ] os projetos com "porta ocupada" continuam listados de propósito: o painel
      não finge que a porta está muda, só para de dizer que é sua
- [ ] zero teste de frontend — a tela que fugia para Ports seria pega por um
      teste de rota
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

## 2026-08-23 (fim de tarde) — Sessão 15: desligar de verdade, e o frontend ganha teste

Você escolheu três frentes e, no meio, cortou uma: o dashboard fica como está.
Sobraram ligar/desligar e teste de frontend.

### O "não desliga" que sobrou

Com o dashboard já corrigido para não inventar projetos no ar, restava o caso
real: **servidor deste projeto iniciado fora do painel**. `servers.status()` só
conhece o que nasceu daqui — a tabela `dev_server` —, então um `npm run dev`
iniciado no terminal deixava o botão sem alvo. Ele respondia sucesso e o
processo seguia atendendo.

`EnvironmentService.down` passou a olhar a última varredura de portas e encerrar
os processos que a descoberta classificou como **não gerenciados deste
projeto**. Quem valida é a descoberta, com a defesa D4 de sempre: só processo
dentro de um root permitido, e só o que ela mesma classificou — o PID não vem do
cliente. O desfecho novo é `stopped: "external"`, e a mensagem diz o que
aconteceu: "parei o servidor que estava rodando fora do painel".

Junto foi outro detalhe que incomodava: com Shift (derrubar tudo), a aplicação
local não parava — só os containers. Agora para as duas coisas.

### Teste de frontend: de zero a existir

Era o maior buraco do projeto: ~5.500 linhas de JavaScript, zero teste, e os
defeitos de interface sendo a maioria dos achados de toda sessão.

A escolha foi manter a doutrina do ADR-005 — o frontend não tem build nem
`node_modules`. Nada de jsdom: `tests/frontend/dom.mjs` é um DOM mínimo escrito
à mão, com o que os módulos realmente usam (`createElement`, `dataset`,
eventos, `append`), mais um relógio falso que conta timers armados. O runner é o
do próprio Node (`node --test`).

Dez testes, cobrindo exatamente o que quebrou hoje:

* o roteador limpa o que a tela deixou de pé ao trocar de rota — o bug do timer
  de Ports redesenhando por cima do Dashboard;
* limpeza roda uma vez só, e uma que falha não impede a próxima tela;
* o dashboard mostra no máximo sete portas, conflito primeiro;
* dia sem atividade continua na grade do gráfico.

`tests/unit/test_frontend_suite.py` roda a suíte de dentro do `pytest`, para o
comando único continuar sendo `pytest -q`. Sem Node instalado ela é **pulada**,
não falha.

Total: 496 testes.

### Continua com você

- [ ] testar o "Desligar" num projeto que você subiu pelo terminal: deve dizer
      que parou o servidor de fora do painel
- [ ] a suíte de frontend cobre roteador e dashboard; Ports, projects e o
      painel de análise ainda não têm teste
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

## 2026-08-25 — Sessão 16: o painel passa a lembrar

Retomamos o prompt do Cockpit AI. A análise e os nove documentos ficaram
prontos na sessão anterior; o que faltava era autorização e a ordem das fases.

### A inversão, aceita

O prompt de visão coloca o agente na Fase 1. A análise do sistema real disse o
contrário, e você aprovou: **a Fase 1 não usa IA nenhuma.**

O motivo é o mesmo princípio que atravessa este projeto. Sem sessão e memória
registradas, o "contexto" que o agente leria sairia de dedução sobre o código —
texto gerado alimentando texto gerado. Com a fundação de pé, a Fase 2 lê fato.

E há um efeito colateral que vale por si: sessão, memória e briefing funcionam
com provedor nenhum configurado. Se a IA se mostrar cara ou ruim, o que ficou
de pé continua útil.

### O que entrou

* **`ai_session`** — abrir marca o estado do Git (branch, sha, arquivos sujos);
  encerrar reúne o que o painel observou e monta o resumo a partir disso;
* **`ai_memory`** — uma tabela com `kind` discriminando e `project_id` nulo
  para a memória global. O campo `source` (`observed` / `human` /
  `ai_suggested`) é o que impede memória virar ficção;
* **Start My Day** — ordena os projetos e **escreve o motivo** de cada posição;
* **`activity_log.actor/agent/reason`** — preparação para a Fase 3, com
  `server_default 'user'` mantendo válido todo o histórico anterior.

### A decisão do corte de commits

O resumo precisa saber quais commits nasceram durante a sessão. O caminho óbvio
seria filtrar por data — e ele erra: relógio de commit vem de rebase, de outra
máquina e de fuso diferente, e traria commit alheio para dentro da sessão. O
corte é pelo **sha** registrado na abertura: lê-se o log até reencontrá-lo.

### Duas correções ao meu próprio plano

1. **`ai_message` não entrou.** O documento previa criá-la já na migração 006,
   mas ela só passa a ser escrita quando o chat existir. Tabela criada antes de
   alguém escrever nela é exatamente o defeito que este projeto corrigiu duas
   vezes (`health_snapshot`, `git_repository`). Fica para a Fase 2.
2. **Um teste pegou um bug meu.** `prune` apagava sugestão velha e a linha
   continuava aparecendo: com `autoflush` desligado nesta sessão, a exclusão
   ficava pendente. Faltava `flush()`.

### Verificado no painel real, não em teste

Abri uma sessão no próprio DEVCOCKPIT: marco em `e1e574a`, 24 arquivos sujos.
Commitei a Fase 1. Encerrei a sessão. O resumo saiu montado sozinho:

> Sessão de 0 min. 1 commit(s), o último: “feat: sessão de trabalho e memória de
> projeto (Cockpit AI, Fase 1)”. 4 arquivo(s) sem commit ao encerrar.

Nenhum modelo configurado. O painel leu o próprio Git e escreveu o que
aconteceu.

Um detalhe do caminho: gravar memória por `curl` dava 400 com acento no corpo —
codificação do meu shell, não do painel. Pelo Python, 201 e texto correto.

516 testes (20 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] usar por um dia: iniciar sessão de manhã, encerrar à noite, e dizer se o
      registro vale o esforço. É o sinal que decide a Fase 2
- [ ] a tela "Meu dia" é a primeira do menu agora; diz se a ordem faz sentido
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem untracked

---

## 2026-08-25 (continuação) — Sessão 17: tarefas, e a camada de gestão fecha

Adiantei `ai_task`, que estava na Fase 3. O motivo é que ela não depende de
provedor nenhum, e sem ela o "Meu dia" só sabia do **próximo passo** escrito na
última sessão: uma linha por projeto, que a sessão seguinte substitui. Tarefa
sobrevive a sessões, e alguém precisa fechá-la.

Com isso a camada de gestão que o prompt de visão pressupunha — e que não
existia no produto — está de pé: projetos, sessões, memória e tarefas.

### As duas decisões

**Descartar não é apagar.** `DROPPED` é estado, não exclusão: guarda que a
ideia foi considerada e recusada. Apagar perderia isso, e a mesma discussão
voltaria daqui a três meses.

**Em curso vem antes de aberta**, mesmo com prioridade menor. Tarefa começada e
largada é o que mais custa lembrar. Depois vem prioridade; depois idade, para o
backlog não virar depósito.

### O painel real corrigiu meu texto

Alimentei as tarefas reais deste projeto e o briefing respondeu:

> DEVCOCKPIT: sessão aberta desde 25/08 00:33; **4 tarefa(s) em curso**; …

Errado: uma estava em curso e quatro abertas. É exatamente a imprecisão que faz
a pessoa parar de acreditar na tela — a mesma família do "no ar" sem prova.
Agora diz "1 em curso de 4 aberta(s)", com teste que falha sem a correção.

### Um susto que virou boa notícia

O briefing acusou sessão aberta às 00:33 que eu não tinha aberto. Antes de
chamar de bug, fui ao banco: às 00:33:31 nasceu a sessão e às 00:33:42 veio um
`server.start`. Era **você**, usando o painel enquanto eu trabalhava. Primeiro
uso real da Fase 1, no mesmo dia em que ela nasceu — e a sessão segue aberta,
que é onde ela deve estar.

526 testes (11 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] encerrar a sessão que você abriu às 00:33, quando parar — o resumo vai
      sair montado dos commits de hoje
- [ ] as quatro tarefas do DEVCOCKPIT estão cadastradas; a de Fase 2 está
      marcada como em curso
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` viraram tarefa em
      vez de item de log — é o lugar certo para eles

---

## 2026-08-25 (noite) — Sessão 18: a Fase 2, e o dia em que o painel deixou de ser local

Esta é a fase que muda a natureza do produto. Até hoje o DevCockpit não fazia
uma requisição de saída; o pior caso de vazamento era alguém com acesso físico
à máquina. A partir daqui, conteúdo de projeto pode ir para um provedor — e por
isso metade do trabalho foi contenção, não funcionalidade.

### As quatro guardas

1. **desligado por padrão**, e ligar é ato fora da interface
   (`DEVCOCKPIT_AI_ENABLED=true` no `.env`): a API não amplia a si mesma;
2. **projeto pode ficar de fora** individualmente;
3. **teto de gasto** por chamada e por dia, com o consumo na tela;
4. **redação antes do envio**: `.env`, `*.key` e credenciais não são lidos —
   nem para serem redigidos depois; segredo em código sai `[REDIGIDO]`.

### Verificação sem chave de API

Não havia chave de provedor nem Ollama nesta máquina. Em vez de entregar código
de rede nunca exercitado, subi **um servidor que imita a API e relata o que
recebeu**, e conversei com ele pelo painel de verdade.

Ele confirmou três coisas que eu não poderia afirmar de outro jeito:

- o contexto chegou com identidade do projeto, memória, sessão em andamento,
  estado e o README rotulado como *dado, não instrução*;
- num projeto com `.env` contendo `OPENAI_API_KEY` e `DB_PASSWORD`, **nada
  disso chegou**;
- um `README.md` com `STRIPE_SECRET_KEY=sk-live-…` chegou **redigido**.

O que **não** foi verificado, e precisa constar: nenhuma chamada à API real de
nenhum provedor. O formato de requisição e a leitura de stream dos três estão
exercitados por HTTP contra o servidor de imitação — isso prova o meu cliente,
não o contrato do fornecedor. Quando você configurar uma chave, a primeira
conversa real ainda é um teste.

### Dois defeitos que só o uso real mostrou

**403 em toda escrita.** Subi o painel de teste na 8795 sem informar a porta às
`Settings`. É o mesmo defeito da porta que já corrigimos duas vezes — desta vez
apareceu em segundos, porque a defesa D5 funciona.

**Tokens dobrados.** O Context Engine lia `README.md` e `readme.md`: no Windows
é o mesmo arquivo, e ele entrava duas vezes. Teste de unidade nenhum pegaria —
foi o provedor de imitação relatando os blocos recebidos que denunciou.

### A regra que atravessou o desenho

O Context Engine **rotula tudo** que entra. Serve a duas coisas ao mesmo tempo:
proveniência para quem lê a resposta, e aviso ao modelo de que conteúdo de
arquivo é dado e não ordem. O painel varre 28 projetos, e nem todo README foi
escrito por você.

572 testes (41 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] a aba **IA** existe em todo projeto e hoje explica como ligar. Para usar:
      `DEVCOCKPIT_AI_ENABLED=true`, provedor, modelo e chave no `.env` ao lado
      do executável — ou `local` com Ollama, e aí nada sai da máquina
- [ ] a primeira conversa com provedor real é verificação, não uso: confira o
      gasto na tela e se o contexto veio certo
- [ ] Fase 3 (especialistas, orquestrador, ações propostas) segue proposta

---

## 2026-08-26 — Sessão 19: subir projeto deixa de depender de sorte

Sua queixa: "dificuldade pra abrir novos projetos e subir os projetos, alguns
terminais está com conflito". Fui ao registro antes de opinar, e o log de
auditoria não tinha **nenhuma** falha — o que já dizia algo: o problema não era
erro, era impedimento silencioso.

### O que a medição mostrou

Sete de dezenove projetos sem forma conhecida de subir. E o mais importante: as
causas eram três, não uma.

Também me enganei no meio do caminho. Primeiro medi `can_start` pelo endpoint
do servidor de desenvolvimento e concluí que sete projetos não subiam; o card
usa a lista, que já considera Compose, e ali eram três. Corrigi antes de virar
afirmação — e a diferença entre os dois números era exatamente Docker.

### As três causas

**Flask num arquivo só.** `app.py` com `from flask import Flask` e sem
`requirements.txt`. A detecção olhava apenas arquivo de dependência, então o
painel se declarava incapaz de subir algo explícito na primeira linha do
arquivo. Import no código é evidência mais forte que uma linha em requirements:
é o uso, não a intenção. Declaração continua vencendo quando existe.

**Monorepo.** `backend/` e `frontend/` sem nada na raiz. O painel agora olha um
nível abaixo — um só, porque dois já seria varredura, e varredura tem tela
própria. Backend antes de frontend: subir o front contra uma API morta produz
tela que carrega e não funciona, que é pior que não subir.

**Site estático.** `index.html` sem build. Precisa de servidor porque `file://`
quebra fetch, módulo ES e rota. `http.server` da biblioteca padrão não instala
nada e não serve para produção — que é exatamente por que serve aqui.

Depois: **zero projetos sem botão de ligar.**

### O conflito de porta

Não havia conflito nenhum no momento em que medi. Ele aparece **na hora de
subir** — e você descobria pelo erro do Compose, no meio da espera, com uma
informação que o verificador já tinha desde o primeiro ciclo.

Agora existe pré-voo: a página do projeto avisa antes do clique, e o botão
recusa oferecendo as três saídas reais — encerrar quem está na porta (só
processo que o painel pode encerrar, dentro de root permitido), trocar a porta,
ou subir mesmo assim. Porta ocupada por processo **do próprio projeto** não é
impedimento: é ele já estar no ar.

### A última milha

Subi um Flask pelo painel para conferir. Ele subiu — e o painel não sabia onde:
o framework escolheu a 5000, nenhum serviço declarava esse número, e sem isso
não há estado nem botão de abrir. A aba Server passa a mostrar a porta que a
descoberta viu com prova de dono e oferece cadastrá-la num clique. Não grava
sozinho: configuração que muda sem ninguém pedir destrói a confiança.

589 testes (17 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] tentar subir os projetos que não subiam — OperaLaby, crossperformance e
      os leves — e dizer o que ainda atrapalha
- [ ] o pré-voo aparece na página do projeto; confira se o texto ajuda
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão

---

## 2026-08-25 — Sessão 20: o painel mentia sobre estar offline, e a IA passou a rodar na sua máquina

Começou olhando os projetos pesados, como você tinha pedido, e terminou em
outro lugar: um defeito no verificador de saúde que corrompia o que o painel
mostrava, e o Cockpit AI saindo do papel para rodar de verdade — local, sem
chave e sem custo.

### O defeito que estava envenenando o painel

O `db:5432` do APP INGRESSO aparecia OFFLINE com o container no ar. Testei o
socket direto: conectava em 0 ms. Então não era o verificador falhando — era o
verificador **mentindo**.

O histórico deu a prova: latências de 3 a 6 segundos registradas num timeout de
2 segundos. Isso é impossível se o `wait_for` estiver cortando. O tempo foi
gasto **na fila**, não na conexão.

Duas causas, ambas medidas:

1. `_check_http` construía um `httpx.AsyncClient` **por verificação**. O
   construtor monta um contexto SSL e, no Windows, isso custa ~225 ms
   **síncronos, em cima do event loop**. Com 18 serviços HTTP num ciclo, o loop
   ficava bloqueado ~5 s e o timeout de 2 s só era atendido bem depois do prazo.
2. `check_many` disparava todas as verificações de uma vez, sem teto.

Agora há um cliente compartilhado e um teto de concorrência. Nas 22 portas
declaradas da sua máquina:

| | estouraram o teto | pior latência |
|---|---|---|
| antes | 16 de 22 | 5983 ms |
| depois | 0 | 2016 ms |

O sintoma para quem usa era o pior possível: **serviço no ar aparecendo
desligado, de forma intermitente, sem nada errado no projeto**. Provavelmente
explica parte da desconfiança que você tinha no painel. D-57 registra.

### O botão do VS Code

Abrir o editor exigia escolher um projeto antes. No começo do dia a ordem é
inversa: liga a máquina, abre o DevCockpit, abre o VS Code — e o editor
restaura a sessão anterior sozinho. Botão na barra superior, sem caminho nenhum
vindo do cliente, que é o que o dispensa de validar root.

### O Cockpit AI saiu do papel

O provedor local existia desde a Fase 2 e **nunca tinha falado com um Ollama de
verdade** — só com servidor de imitação. Falou. Perguntei ao painel sobre o
próprio DEVCOCKPIT e ele respondeu certo, citando as quatro garantias de
segurança do projeto.

Três coisas atrapalhavam:

- **o `.env` era ignorado em silêncio no executável.** `env_file=".env"` é
  relativo ao diretório de trabalho, que num app empacotado é onde quer que o
  atalho tenha sido clicado. "A IA não liga e não diz por quê" é o modo de
  falha que este projeto não aceita;
- **Ollama fechado** dava `[Errno 10061]`. Agora diz o que fazer.
  `ConnectTimeout` entrou junto de `ConnectError` e **antes** de
  `TimeoutException`: no Windows porta fechada pendura em vez de recusar, a
  mesma peculiaridade que o health check já documentava;
- **modelo não baixado** mandava conferir a variável. Agora o painel pergunta ao
  Ollama e lista os instalados na própria mensagem.

### Dois modelos, e a pergunta rápida

Você pediu o Ollama como agente interno de terminal — e o chat da aba IA é o
lugar errado para isso: ele manda memória, sessão, tarefas e README junto. Numa
dúvida de `git reset` isso é pagar o triplo por informação sem relação com a
pergunta.

Nasceu a **pergunta rápida** (`Ctrl+Espaço`, ou o botão de terminal na barra
superior): sem projeto, sem contexto, não persistida — mas o gasto é
contabilizado, porque teto com porta de saída não é teto.

E dois modelos configurados em vez de um, com seletor. O cliente manda
`"default"` ou `"alt"`, nunca o nome de um modelo — mesma doutrina do
`open_service_url` receber a chave do serviço e jamais a URL (D-13).

### Onde eu errei, e a correção

Recomendei o modelo de 3B com base em quatro perguntas de terminal em que ele
acertou 4 de 4. **O teste era fraco demais para a conclusão.** Eram perguntas
que qualquer modelo viu milhares de vezes; os dois acertarem só provava que
ambos decoraram o básico.

Você desconfiou e mandou testar melhor. Quatro perguntas de diagnóstico depois:

| | Fáceis (comando) | Difíceis (causa raiz) |
|---|---|---|
| `qwen2.5-coder:3b` | 4 / 4 | **0 / 4** |
| `qwen2.5-coder:7b` | 4 / 4 | **0 / 4** |

Uma das difíceis era o bug real corrigido nesta sessão — `except OSError` antes
de `except TimeoutError`, que torna o segundo ramo código morto desde o Python
3.10. **Os dois disseram que o código estava correto.**

E o tamanho não corrige o risco: perguntado por que socket TCP pendura no
Windows, o 3b listou palpites e admitiu não saber; o 7b **inventou "delayed
ACK"** com convicção. Errado com convicção é pior que errado com dúvida — o
primeiro você confere, o segundo você acredita.

Você escolheu o 7b como padrão com o dado à vista. Trocado, e o guia registra a
medição ao lado da decisão, para quem revisitar não precisar refazer o teste.

### Velocidade

O que ninguém tinha olhado: **num modelo local o tamanho da resposta é o tempo
de espera**. O texto sai a ~10 tokens/s, e a pergunta rápida herdava o teto de
2.000 tokens do chat — três minutos de digitação para uma dúvida de `netstat`.

Com teto próprio e prompt de formato fixo, a mesma pergunta caiu de **173
tokens / 14,2 s** para **49 tokens / 6,1 s**. Mesmo comando na resposta; sumiu
a explicação de cada parâmetro. Média de quatro perguntas: 3,9 s. De quebra,
perguntado sobre uma ferramenta inexistente ele passou a responder "não sei" em
1,1 s, em vez de inventar o comando.

O que **não** foi resolvido: o 7b descarrega da RAM após 5 min parado, e
recarregar 4,7 GB custa **143,5 s até a primeira palavra**. Quente ele responde
em 8,4 s; o 3b quente responde em 0,7 s.

### Documentação

`docs/ai/LOCAL_MODEL_GUIDE.md` — o décimo documento de `docs/ai/`, e o único de
uso e não de projeto. O índice ainda dizia "nada aqui está implementado", o que
deixou de ser verdade com as Fases 1 e 2 entregues.

611 testes, `ruff` limpo, aplicativo reempacotado e no ar na 8765.

### Continua com você

- [ ] **decidir o modelo padrão.** Ou `setx OLLAMA_KEEP_ALIVE 60m` (segura o 7b
      na RAM, custa 5 GB presos, resolve os 143 s frios mas não os 34 s
      quentes), ou voltar o 3b (0,7 s quente, sem perda de acerto medida). Duas
      linhas no `.env` em `C:\Users\User\DevCockpit\`
- [ ] `ollama rm llama3.2:3b` e `llama3.2:1b` — 3,3 GB parados, dos modelos que
      erraram 3 de 4 no teste
- [ ] **Fase 3**: especialistas, orquestrador e ações propostas com
      confirmação. É onde "o agente sobe o servidor pra mim" passa a existir —
      pela allowlist, com confirmação, nunca comando novo (D-A3)
- [ ] o painel não gerencia o Ollama (lista de modelos, o que está na RAM,
      descarregar). Cabe bem no que ele já é
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- [ ] conferir a aba Docker com o Docker Desktop **desligado** (pendente desde
      21/08)

---

## 2026-08-25 (continuação) — Sessão 21: a IA passa a agir, com você confirmando

Retomada para a Fase 3. Terminou com "sobe o kiteasy" ligando o ambiente —
depois de um clique em Confirmar.

### Medi antes de construir, porque o desenho dependia disso

Duas perguntas que decidiam se a Fase 3.4 se sustentava num provedor local. Um
modelo pequeno consegue escolher uma ação de um registro fechado? E consegue
achar o projeto certo entre os 18 cadastrados?

| | Escolher a ação | Recusar o que não existe | Achar o projeto |
|---|---|---|---|
| `qwen2.5-coder:3b` | 5 de 6 | **falhou** — propôs `environment.up` para "deploy em produção" | — |
| `qwen2.5-coder:7b` | 6 de 6 | acertou | **7 de 7** |

O 7b corrigiu "smartdah" para `smartdash` e recusou projeto inexistente. Isso
**valida a sua escolha dele como padrão** — que a medição anterior não tinha
sustentado. Rotear é tarefa muito mais fácil que diagnosticar, e é justamente
na parte perigosa (recusar o que não existe) que o modelo maior ganha.

### O desenho

`app/services/ai/actions.py` é um catálogo fechado de doze coisas que o painel
**já faz por botão**, cada uma apontando para a rota daquele botão. Um teste
confere contra o OpenAPI que nenhuma aponta para rota inexistente.

O fluxo é: o modelo escolhe um nome da lista → o servidor valida → a tela
mostra e você confirma → a execução vai pela rota de sempre. A IA não ganha
caminho de execução próprio, que é a defesa D-A3 ao pé da letra.

Vira recusa, nunca ação aproximada: nome fora do registro, projeto inventado,
JSON quebrado, e ação que precisa de projeto sem projeto resolvido.

O erro que mais preocupava — ação certa no **projeto errado** — tem teste
próprio: com dois projetos "OperaLaby ..." cadastrados, "sobe o operalaby" não
propõe nada. Propor no projeto errado é pior que não propor, porque parece que
funcionou.

### Regra primeiro, modelo no empate

Medido contra o painel real:

| Frase | Tempo | Caminho |
|---|---|---|
| `sobe o kiteasy` | **0,2 s** | regra |
| `abre o site3d no vscode` | 0,2 s | regra |
| `sobe o smartdah` | 15,6 s | modelo, corrigindo o nome |
| `como desfaço um commit?` | — | sem proposta; vira pergunta normal |
| `faz o deploy em produção` | — | recusado, não existe no registro |

Num provedor local, 0,2 s contra 15 s é a diferença entre usar e não usar. E a
regra é código: funciona com o Ollama fechado.

### Um defeito de isolamento achado de brinde

Dois testes de IA começaram a falhar. Causa: `Settings` lê `DEVCOCKPIT_*` do
ambiente, e esta máquina agora tem essas variáveis definidas. A suíte estava
afirmando algo sobre **a configuração da máquina** em vez de sobre o código —
passaria em qualquer outra. Uma fixture autouse limpa as variáveis antes de
cada teste.

### O empacotamento

O `Remove-Item` falhou com `VCRUNTIME140.dll` travada. Desta vez o culpado não
era o próprio app: era o **VS Code**, com a DLL carregada. Fechar o editor de
quem está trabalhando não é opção, então conferi o hash — idêntica nos dois
builds — e copiei o resto com `robocopy`, verificando arquivo por arquivo que a
instalação ficou idêntica ao build.

635 testes (24 novos), `ruff` limpo, app no ar na 8765.

### Continua com você

- [ ] **decidir o modelo padrão.** `setx OLLAMA_KEEP_ALIVE 60m` segura o 7b na
      RAM (custa 5 GB presos, resolve os 143 s frios, não os 34 s quentes); ou
      voltar o 3b, que responde em 0,7 s quente
- [ ] `ollama rm llama3.2:3b` e `llama3.2:1b` — 3,3 GB parados
- [ ] **Fase 3, o que falta**: perfis de especialista, command palette (`/plan`,
      `/find-bugs`), e `actor="ai"` ponta a ponta na auditoria — hoje a
      execução da ação confirmada é registrada como ação do usuário, que é
      verdade parcial: quem propôs foi a IA
- [ ] o painel não gerencia o Ollama (modelos, o que está na RAM, descarregar)
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- [ ] conferir a aba Docker com o Docker Desktop **desligado** (desde 21/08)

---

## 2026-08-25 (continuação) — Sessão 22: o ecossistema vira mapa

Pedido novo, e com uma regra dura no enunciado: **não criar outra IA, não criar
outro agente, não criar outro dashboard.** Dar forma visual ao que já existe.

Antes de escrever código, um levantamento e uma proposta — `docs/ai/HYPERBRAIN.md`,
com estado atual, arquitetura, riscos e critérios de aceite. Três decisões
ficaram travando o início: biblioteca de grafo, tema, e tamanho do primeiro
corte.

### A correção que a proposta precisou fazer

O pedido descrevia animar "a IA consultando o projeto X", com energia fluindo do
núcleo até o nó. Isso não corresponde ao que o backend faz: o chat é sempre
escopado a **um** projeto que a pessoa escolheu, e nenhuma varredura dos outros
acontece. Acender uma aresta até um projeto que ninguém consultou seria o painel
afirmando o que não mediu — o mesmo defeito já corrigido duas vezes aqui ("no
ar" porque a porta respondia, "3 projetos rodando" porque a porta estava
ocupada).

Sobraram três sinais que são fato: o projeto que a proposta resolveu, as camadas
de contexto que de fato entraram, e o projeto em foco. Aresta só acende com um
desses três por trás.

### Nenhuma biblioteca, e o número que decide

React Flow, Cytoscape, Sigma, D3 e Three.js entraram na comparação. Todas caem
no mesmo ponto: por npm trazem build e `node_modules`, contra o ADR-005; por CDN
quebram o uso offline do executável.

Faltava o dado do meio — quantos nós. Com os 19 projetos cadastrados, 31 nós e
72 arestas. Com a expansão prevista para as fases seguintes, 60 a 200.

Medido no Chromium, um passo da simulação:

| Nós | ms por passo |
|-----|--------------|
| 31 (real) | 0,011 |
| 100 | 0,039 |
| 200 | 0,156 |
| 400 | 0,576 |

O orçamento de um quadro a 60 fps é 16,7 ms. Com 400 nós — o dobro do teto
previsto — a simulação usa 3,5% dele. WebGL resolveria um problema que este
projeto não tem. SVG à mão, e ADR-009 registrando por quê.

### O que a tela faz

Núcleo no centro, os projetos ao redor, e as tecnologias **compartilhadas** como
satélites que ligam projeto a projeto. Tecnologia usada por um projeto só não
vira nó: ela não relaciona nada, e o nome já está no painel lateral.

Zoom, deslocamento, arraste, foco (o nó e seus vizinhos ficam nítidos, o resto
atenua), painel de contexto com dois caminhos — abrir o projeto pelo fluxo de
sempre, ou focar. Ligar, parar, portas e Git continuam na tela do projeto.

O núcleo diz o estado da IA, e diz a verdade: com o Cockpit AI desligado, ele
mostra "IA desligada" e o resto da tela funciona igual. **O grafo é dado, não
IA** — nenhuma linha de backend mudou.

Na tela: estabiliza em 0,96 s, ~65 quadros no primeiro segundo, e **zero**
quadros pedidos depois disso. O laço encerra em vez de girar em vazio.

### Quatro ajustes que só apareceram com a tela no ar

- **rótulo longo atravessava o vizinho** — "PLATAFORMA DE INGRESSOS" ocupa
  quatro vezes a largura do nó. Cortado em 18 caracteres no desenho; o nome
  inteiro fica no `aria-label` e no painel;
- **satélites amontoados no meio** — a repulsão passou a ser proporcional ao
  peso do nó, e a tecnologia declara peso maior que o próprio tamanho;
- **o grafo nascia transbordando as bordas** — ao parar de se mexer, a câmera
  calcula a caixa que contém tudo e enquadra uma vez;
- **nó arrastado fica onde foi solto** — organizar o mapa é gesto de quem
  trabalha com ele. "Reorganizar" solta todos.

### Dois defeitos, os dois achados olhando a tela

`Esc` não saía do foco. O atalho estava preso ao palco SVG, mas quem acabou de
clicar em "Focar" no painel lateral tem o foco do teclado no botão — o evento
nunca chegava ao palco. Ou seja: só funcionava depois de clicar num nó, que é
exatamente quando não se precisa dele. Achado pela verificação ao vivo, não por
leitura de código.

O segundo apareceu numa captura de tela: um aro solto flutuando no canto, longe
do núcleo. Era o anel do próprio núcleo. Num elemento SVG, `transform-origin:
center` se refere ao centro do **viewBox**, e não ao do elemento — o anel girava
numa órbita de centenas de pixels. `transform-box: fill-box` resolve. Nenhum
teste pegaria: o elemento estava lá, com os atributos certos. Foi preciso olhar.

16 testes novos no grafo (26 de frontend), 635 no `pytest`, `ruff` limpo.

### Continua com você

- [ ] **usar a tela antes do MVP 2.** O Ask ligado à IA existente é o próximo
      corte, mas o que ele deve destacar depende de o mapa provar que serve
- [ ] o MVP 2 precisa expor `ai_enabled` em `ProjectSummary`: projeto excluído
      da IA tem que aparecer diferente antes de a tela falar com modelo nenhum
- [ ] as três pendências da sessão 21 seguem de pé — modelo padrão do Ollama,
      Fase 3 (3.2, 3.3, 3.5, 3.6) e a decisão sobre `Dockerfile`

---

## 2026-08-25 (continuação) — Sessão 23: o mapa passa a responder

MVP 2 do HyperBrain: a barra "Ask HyperBrain" dentro do palco, ligada à IA que
já existia. Nenhum agente novo, nenhum provedor novo — só um caminho novo até os
mesmos.

### Três caminhos, e um porteiro

O que se digita segue nesta ordem: filtro de visão (regra local), ação (proposta
com confirmação) e, por último, pergunta.

O filtro é o que mais surpreende: "mostre os projetos em python" não precisa de
IA nenhuma. É filtro sobre dado que o navegador já tem, resolvido em
milissegundos, **com zero chamada de rede** — verificado contando as requisições
durante o gesto. Funciona com o Cockpit AI desligado.

O porteiro do passo 2 existe por causa do relógio. Pedir proposta custa 0,1 s
quando a regra do servidor decide, e de 3 a 26 s quando cai no modelo local. Se
toda frase pagasse esse pedágio, "onde paramos ontem?" começaria a ser respondida
meio minuto depois de escrita.

### O que a medição mostrou sobre os dois modelos

| Frase | 7b | 3b |
|---|---|---|
| `sobe o devcockpit` | 0,1 s — regra | 0,1 s — regra |
| `faz o deploy em produção` | 25,8 s — **recusou** | 3,1 s — propôs `environment.up` |
| `apaga o banco do devcockpit` | 5,5 s — **recusou** | 4,2 s — propôs `server.stop` |

É a mesma diferença medida na Fase 3.4, agora vista da tela do grafo. E a
contenção não depende do modelo: com o 3b propondo `server.stop` para "apaga o
banco", o log de atividade ficou em **7 antes e 7 depois**. Nada executa sem o
clique.

Os verbos destrutivos entraram na lista de propósito, embora nenhum exista no
registro fechado — justamente por isso. Mandados para o servidor, voltam como
recusa explícita. "Apaga o banco" merece "não faço isso", não um modelo
divagando sobre como apagar um banco.

### Um interruptor que não tinha interruptor

`ai_enabled` existe na tabela `project` desde a Fase 2, e a defesa D-A1 diz que
excluir um projeto da IA é decisão da pessoa, projeto a projeto. Só que não
havia rota para mudar o campo: ele nascia `true` e ficava `true` para sempre.
Agora está em `ProjectUpdate` e em `ProjectSummary` — a segunda porque uma tela
que mostra todos os projetos de uma vez precisa sinalizar quem está fora
**antes** de qualquer requisição.

Verificado ao vivo: com `ai_enabled = false`, perguntar com o projeto
selecionado não chama a rota de chat. Aparece só `ai/ask` na rede, e a tela
avisa que perguntou sem o contexto dele.

### O defeito, e ele era bom

O botão Cancelar do cartão de ação não fazia nada.

O estado do núcleo passava pelo mesmo observável do painel lateral, então cada
`thinking` ou `success` remontava o painel inteiro. O `blur` do campo de
pergunta chegava junto com o clique: o cartão era removido e recolocado no meio
do gesto, e o clique se perdia no vão. Quem fosse **recusar** uma ação apertava
Cancelar e não acontecia nada.

O conserto foi tirar o estado do núcleo do observável — ele é atributo de um
elemento, não estado de tela. Achado clicando, não lendo.

### Verificação ao vivo, em banco separado

A primeira tentativa rodou contra o banco do app instalado e deu `database is
locked`: dois servidores escrevendo no mesmo SQLite. O resto da verificação
passou a rodar em banco próprio, com cinco projetos cadastrados só para isso.

### Rótulos, e a vida do núcleo

Com os 19 projetos na tela, dois problemas de layout ficaram óbvios:
"QRCODE_GENERATION" cruzando "DEVCOCKPIT", e nomes cinzas cortados pelas
arestas que passavam por baixo.

`labels.js` escolhe, para cada rótulo, o primeiro lugar livre em volta do nó —
abaixo, acima, direita, esquerda —, com os nós e o núcleo contando como
obstáculo. Quem não acha lugar some, e volta no hover. Roda **só quando o grafo
para**: medir texto obriga o navegador a calcular layout, e por quadro custaria
mais que a simulação inteira. Medido na tela: **0 pares sobrepostos**, 1
escondido de 30.

E o pedido de "movimento, pulsante, com cores" virou regra: cada coisa que se
mexe carrega informação. Halo respirando, dois anéis em sentidos opostos, trinta
partículas orbitando, dois pulsos defasados — e o que importa mais: **nó de
projeto respirando em verde significa que ele está no ar agora**. Cada
tecnologia ganhou matiz derivada do hash do nome, aplicada como `hue-rotate`
sobre o token: cor literal continua morando só no `tokens.css`.

Tudo desliga junto em `prefers-reduced-motion`, no botão de movimento e acima de
150 nós. Nenhuma animação roda em JavaScript.

42 testes de frontend (18 novos), 636 no `pytest`, `ruff` limpo.

### O executável, e uma porta que ninguém tinha declarado

Empacotado e instalado, com o mesmo contorno da sessão 21 para a
`VCRUNTIME140.dll` travada — desta vez pelo VS Code, com o painel já parado.
Hash conferido, `robocopy` no resto, e verificação arquivo por arquivo: 320
arquivos idênticos ao build.

Ao reabrir, o painel subiu na **8765** e não na 8790. Descoberta: a 8790 não
está gravada em lugar nenhum — nem em `configs/defaults.yml`, nem em variável de
usuário. Ela vinha do ambiente de quem tinha lançado o app da última vez. 8765 é
o padrão do código.

### Continua com você

- [ ] **usar a tela.** O MVP 3 (tarefas, sessões, decisões e serviços como nós)
      só faz sentido depois de o mapa provar que serve para alguma coisa
- [ ] `ai_enabled` tem rota, mas **não tem botão**: hoje só muda por `PATCH`.
      Um interruptor na tela do projeto fecharia a defesa D-A1 de verdade
- [ ] o seletor de modelo (7b/3b) não existe no HyperBrain; a pergunta rápida
      tem. Com a diferença de tempo medida acima, pode valer
- [ ] as pendências das sessões 21 e 22 seguem de pé

---

## 2026-08-25 (madrugada) — Sessão 24: o 3D que não vingou, e o núcleo que passou a bater

Sessão longa, com uma reversão no meio. O que ficou de pé: o mapa 2D com
rótulos que não se atropelam e um núcleo com batimento. O que caiu: o 3D
inteiro, por decisão sua depois de ele travar duas vezes na sua máquina.

### Rótulos: o problema que a força não resolve

A simulação cuida dos **nós**; o rótulo é um retângulo largo pendurado num
deles. "QRCODE_GENERATION" ocupa oito vezes a largura do próprio círculo, e dois
nós confortavelmente separados podem ter nomes que se cruzam.

`labels.js` escolhe, para cada rótulo, o primeiro lugar livre em volta do nó —
abaixo, acima, direita, esquerda — com os nós e o núcleo contando como
obstáculo. Quem não acha lugar some e volta no hover. Roda **só quando o grafo
para**: medir texto obriga o navegador a calcular layout.

Medido na tela real: **0 pares sobrepostos**, 1 escondido de 30.

### A tentativa de 3D, e por que ela foi revertida

Você pediu o 3D depois de eu recomendar contra. Foi implementado: three.js r170
vendorizado (sem npm, sem CDN, com mapa de importação), terceiro eixo na
simulação, luz no núcleo, rótulos continuando no DOM, oclusão por raio, anel de
seleção, neblina e poeira para paralaxe.

Você aprovou uma versão ("ficou incrível") e pediu refino. Depois disso a tela
**travou**, e não voltou a ser usável. Decisão sua: voltar ao mapa plano.

**A causa do travamento não era o WebGL.** Eram dois defeitos meus no código em
volta dele, e os dois valem ficar escritos porque qualquer tentativa futura vai
esbarrar neles:

1. **Eu media `offsetWidth` de cada rótulo a cada quadro.** Ler essa propriedade
   força o navegador a recalcular o layout na hora — trinta vezes por quadro,
   logo depois de escrever os `transform`. É *layout thrashing* clássico: o
   quadro para e espera.
2. **A oclusão testava triângulo a triângulo.** Um `Raycaster` por nó contra a
   geometria real: 31 nós × ~1.100 triângulos × 31 raios ≈ um milhão de testes a
   cada oito quadros. Vira conta de esfera em trinta multiplicações.

Os dois foram corrigidos antes da reversão, e a correção está no histórico
(66a6b3c, e5f87e2). Reverti com `revert`, não com `reset`: os commits continuam
recuperáveis com um revert do revert.

Fica também o achado de plataforma: quando o navegador bloqueia a GPU, o WebGL
**continua existindo**, emulado na CPU pelo SwiftShader. A tela não fica lenta,
fica travada — e `getContext('webgl')` devolvendo um contexto não prova nada. O
teste que presta é ler `WEBGL_debug_renderer_info` e recusar quando o nome bate
com swiftshader/llvmpipe/software.

### Outros dois defeitos achados clicando

- **O botão Cancelar do cartão de ação não fazia nada.** O estado do núcleo
  passava pelo mesmo observável do painel lateral, então cada `thinking` ou
  `success` remontava o painel — e o `blur` do campo de pergunta chegava junto
  com o clique. O cartão saía e voltava no meio do gesto, e o clique se perdia.
  Quem fosse **recusar** uma ação apertava Cancelar e não acontecia nada.
- **`transform-origin: center` em elemento SVG** se refere ao centro do
  *viewBox*, não ao do elemento. O anel do núcleo girava numa órbita de centenas
  de pixels, aparecendo como um aro solto no canto da tela. `transform-box:
  fill-box` resolve.

### O núcleo passou a bater

O disco ganhou batimento em vez de respiração — contrai rápido e solta devagar,
com contragolpe. A curva simétrica lê como pulsação de aparelho; esta lê como
algo vivo. Junto: um arco curto girando em 3,6 s, três pulsos defasados, poeira
quase duas vezes mais rápida.

O ritmo é informação: pronto 3,2 s, ouvindo 2,2 s, **pensando 1,5 s**,
desligado **parado**. Tudo em CSS, sem um quadro de JavaScript, e desliga junto
em `prefers-reduced-motion`.

### Verificação executada

| O que | Resultado |
|---|---|
| `pytest -q` | **636 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend/*.test.mjs` | **42 passaram** |
| `ruff check .` | limpo |
| Mapa ao vivo, 19 projetos reais | 31 nós, **0 rótulos sobrepostos**, console limpo |
| Filtro `mostre os projetos em python` | responde com **zero chamada de IA** |
| Executável reconstruído e instalado | 321 arquivos, **idêntico ao build** |

### Situação ao encerrar

Branch `main`, árvore limpa, tudo publicado (`378c14d`). O app instalado roda na
**8765** — e não na 8790: a 8790 vinha do ambiente de quem lançou o app antes, e
não está gravada em configuração nenhuma.

Aceito como está, não pendente: o HyperBrain é 2D. A decisão foi sua, depois de
ver o 3D falhar.

Pendente de verdade:

- `ai_enabled` tem rota, mas **não tem botão**: só muda por `PATCH`
- `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- Cockpit AI: faltam 3.2, 3.3, 3.5 e 3.6; MVPs 3 a 5 do HyperBrain não começaram

### Próximo passo

**Usar a tela por alguns dias antes de mexer nela de novo.** O MVP 3 (tarefas,
sessões e decisões como nós) só faz sentido depois de o mapa provar que serve
para alguma coisa no dia a dia — e esta sessão mostrou o custo de empilhar
camada visual sem esse teste.

---

## 2026-08-26 — Sessão 25: a auditoria passa a dizer quem pediu

Sessão curta e fechada: três pendências que estavam abertas há dias, e uma fase
inteira do Cockpit AI.

### O executável e os Docker

O painel instalado subiu com o núcleo batendo — rebuild, `robocopy` com o mesmo
contorno da `VCRUNTIME140.dll` travada pelo VS Code, 321 arquivos conferidos por
hash contra o build.

`Dockerfile`, `docker-compose.yml` e `.dockerignore` ficam **versionados, com
aviso no topo**. A decisão pedia honestidade mais que gosto: dentro de um
container o painel perde abrir editor, pasta e terminal (nenhum dos três existe
lá), a varredura (os caminhos de `roots.yml` são do host), o servidor de projeto
e a verificação de porta — `localhost` ali é o do container, então todo serviço
do host apareceria offline. Sobra cadastro, Git, leitura de Docker com o socket
montado, portas declaradas e o Cockpit AI. Serve ao cenário de rodar num
servidor Linux contra projetos do próprio servidor, e a nada além disso.

Junto saiu `DEVCOCKPIT_HOST` do compose: não afeta o bind (quem manda é o `CMD`)
nem a validação de origem, que usa **só a porta**. Eu havia afirmado antes que a
divergência daria 403 em todo botão — fui verificar `self_origins` e estava
errado. Variável que não faz nada confunde mais do que ajuda, e por isso saiu.

### Fase 3.6 — o que ela realmente resolve

Não é funcionalidade, é honestidade do log. Até aqui, ação que o agente propôs e
a pessoa confirmou era gravada como **ação da pessoa**.

A saída óbvia — o cliente mandar um cabeçalho dizendo "isto veio da IA" — foi
descartada logo: seria o cliente **afirmando** autoria, e um log de auditoria
que confia no auditado não audita. É a mesma razão que proibiu o cliente de
mandar URL na decisão D-13.

O que ficou: o servidor emite um bilhete ao propor (`app/services/ai/propostas.py`)
e só reconhece autoria se ele voltar para a **mesma rota e o mesmo método**.
Bilhete inventado, vencido, já usado ou apontando para outra rota não marca nada
— e a ação segue, gravada como o que ela é. Uso único, porque bilhete
reutilizável transformaria uma confirmação em quantas execuções o cliente
quisesse.

O registro vive em memória de propósito: proposta é objeto de segundos, e
sobreviver a um reinício não é qualidade nenhuma para ela.

A autoria chega ao `ActivityService` por `ContextVar`, ao lado do
`correlation_id` — quem grava a auditoria é o serviço lá no fundo, e passar isso
por parâmetro obrigaria a atravessar rota, serviço, adapter e runner com um
argumento que só a última linha usa.

### Achados

- **Ação de leitura não gera auditoria nenhuma** no painel (`git.status`,
  `ports.map`, `docker.ps`), e isso é anterior à 3.6. Descoberto ao ver a
  verificação ao vivo dar `actor=ai: 0` — o caminho estava certo, a ação
  escolhida é que não deixava rastro. Consequência: "o que o agente **fez**
  ontem?" tem resposta; "o que ele **leu**?" não. Mudar é decisão de produto.
- **A poda do registro deixava TETO + 1.** `_podar` rodava antes da inserção,
  sobre um registro já cheio. Achado por teste, não por leitura.
- **Os primeiros testes abriam o Explorer de verdade** a cada rodada da suíte,
  porque `open/folder` executa comando real. Trocados por `PATCH /projects/{id}`,
  que passa pelo mesmo caminho de auditoria sem tocar na máquina.

### Verificação executada

| O que | Resultado |
|---|---|
| `pytest -q` | **647 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend/*.test.mjs` | **42 passaram** |
| `ruff check .` | limpo |
| Ao vivo, painel real, Ollama ligado | "abre o devcockpit no vscode" virou proposta em **0,01 s** pela regra |
| Confirmação com bilhete | `actor=ai`, `agent=open.vscode`, motivo nomeando quem decidiu |
| Mesmo bilhete de novo | gravado como **ação do usuário** — uma confirmação, uma execução |

### Situação ao encerrar

Branch `main`, árvore limpa, tudo publicado (`e81a002`). Painel instalado de pé
na **8765**, com o núcleo batendo. Nenhum servidor de desenvolvimento no ar.

Do Cockpit AI faltam **3.2, 3.3 e 3.5**. Do HyperBrain, os MVPs 3 a 5 — e o
combinado continua: usar a tela antes de empilhar camada nova.

### Próximo passo

**O interruptor do `ai_enabled` na tela do projeto.** A defesa D-A1 diz que
excluir um projeto do Cockpit AI é decisão da pessoa, projeto a projeto — e hoje
isso só muda por `PATCH`. É pequeno e fecha o último buraco de honestidade
aberto. Depois 3.2 + 3.3 juntos, e 3.5 quase de graça em cima deles.

---

## 2026-08-26 (tarde) — Sessão 26: a chave que existia sem fechadura

Sessão curta, um item só, e ele fecha um buraco antigo.

### O interruptor da defesa D-A1

A coluna `ai_enabled` existe na tabela `project` desde a Fase 2, e o modelo de
segurança diz com todas as letras que tirar um projeto do Cockpit AI é decisão
da pessoa — projeto a projeto, porque cliente, contrato ou dado sensível é ela
quem sabe onde estão.

Só que **não havia como decidir**. O campo nascia `true` e ficava `true`: uma
defesa cuja chave ninguém alcançava. Na sessão anterior a rota `PATCH` passou a
aceitar o campo; nesta ele ganhou botão, na aba Overview, com o significado
escrito ao lado — "participa: o contexto deste projeto pode ser enviado ao
provedor" ou "fora: nada deste projeto entra em contexto, nem por engano".

Decisão pequena que vale registrar: **sem cor de perigo no botão**. Tirar um
projeto da IA é proteção, não estrago, e pintar de vermelho ensinaria o
contrário.

Junto fechou o critério de aceite que o MVP 2 do HyperBrain tinha deixado
pendente: o painel lateral do nó avisa quem está fora **antes** de alguém
perguntar. Sem isso, a resposta viria sem contexto e ninguém entenderia por quê.

### Verificação executada

Em banco separado, com dois projetos cadastrados só para isso:

| O que | Resultado |
|---|---|
| `pytest -q` | **649 passaram**, 1 pulado, 3 desmarcados |
| `ruff check .` | limpo |
| Clique no interruptor | rótulo e explicação trocam; aviso na tela |
| Estado no servidor | `ai_enabled: false` gravado |
| Painel do HyperBrain | passa a dizer "Fora do Cockpit AI" |
| Efeito colateral | nenhum: nome, caminho, status, fixado e trava de detecção intactos (teste dedicado) |

### Situação ao encerrar

Branch `main`, árvore limpa, publicado em `410c11c`. Nenhum servidor no ar — o
de verificação usava banco próprio em pasta temporária e foi derrubado.

Do Cockpit AI faltam **3.2, 3.3 e 3.5**. Do HyperBrain, os MVPs 3 a 5.

### Próximo passo

**3.2 + 3.3 juntos**, e a sessão parou exatamente na leitura do
`docs/ai/AGENT_ORCHESTRATION.md`. O desenho já está escrito lá: especialista é
**perfil** (instrução de sistema + ferramentas permitidas + camadas de contexto
preferidas), não agente autônomo; sete perfis; no máximo dois por pergunta; e
regra primeiro, modelo no empate — a mesma doutrina do orquestrador de ações.

Três decisões precisam do usuário antes de escrever código:

1. **Quantos perfis no primeiro corte.** Os sete do documento, ou os três que
   cobrem o uso diário deste painel (DevOps, Full Stack, QA)?
2. **Escolha manual.** A pessoa pode fixar o especialista, ou o roteamento é
   sempre automático?
3. **Onde registrar quem respondeu.** `ai_message` não tem coluna para isso —
   entra por migração `009`, ou vai junto do `context_summary`?

---

## 2026-08-27 — Sessão 27: a conversa ganha chapéu

Fase 3 do Cockpit AI fechada: **3.2 (perfis), 3.3 (seleção) e 3.5 (comandos)**.
O pedido foi "finalize todas as pendências", com três decisões dadas: três
perfis, especialista fixável com botões de um clique, e quem respondeu gravado
em `ai_message` por migração.

### O que um especialista é aqui

Um chapéu, não um agente. Instrução de sistema própria, um punhado de ações do
registro fechado, e nada mais: um processo, um modelo, três chapéus. DevOps
(ambiente, container, porta, log), Full Stack (código, API, integração) e QA
(teste, bug, regressão).

Três e não os sete do `AGENT_ORCHESTRATION.md`. Os sete cobrem o produto
imaginado; três cobrem o que este painel faz hoje. Perfil sem uso é prompt para
manter sem ninguém ler.

### A divergência que vale registrar

O desenho previa o modelo desempatando quando nenhuma regra casasse. **Não há
chamada de modelo no roteamento**, e o motivo é medido: num provedor local uma
classificação curta custa de 3 a 26 s — mais que a resposta inteira em muitos
casos. Roteamento que custa isso não é roteamento, é espera.

A regra decide pela palavra na pergunta; sem casar, o Full Stack atende; e a
escolha da pessoa vence as duas. É a mesma doutrina do orquestrador de ações,
levada até o fim: regra primeiro, e o modelo só onde ele é insubstituível.

### Os botões, que era o pedido de verdade

> "tem como ficar especialista, subir terminal, abrir ambiente com um click,
> subir container com um click, pra nao ficar pedindo ajuda ao claude"

Cada perfil traz uma barra de atalhos. Nenhum deles é caminho novo: apontam para
ações do **mesmo registro fechado** das propostas, com bilhete emitido pelo
servidor — clicar equivale a confirmar uma proposta, e a linha de auditoria sai
com `actor=ai` igual à que veio de uma frase (D-A3 + Fase 3.6).

Um teste percorre os três perfis e falha se algum atalho apontar para fora do
registro. Sem ele, a barra de atalhos seria exatamente o lugar onde uma
capacidade nova entraria sem ninguém notar.

Detalhe que os testes pegaram e eu não tinha visto: `ports.map` **não leva
projeto no caminho** — é da máquina, não do projeto. As duas formas convivem na
mesma barra, e o filtro só remove a ação de projeto quando não há projeto.

### Migração 009

`ai_message.agent` e `ai_message.prompt_versao`. A segunda parece exagero até o
prompt mudar: depois disso, uma resposta guardada sem a versão vira algo que
ninguém consegue explicar, porque o texto que a produziu não existe mais em
lugar nenhum.

Armadilha de ambiente, de novo: `alembic upgrade head` rodou e as colunas não
apareceram em `data/devcockpit.db`. O banco efetivo é
`C:/Users/User/DevCockpit/data/devcockpit.db` — `settings.resolve` reescreve o
caminho relativo. Conferir a versão no arquivo errado dá "não aplicou" quando
aplicou.

### Comandos de barra

`/status`, `/plan`, `/find-bugs`, `/why`, `/review`, `/document`. Cada um é uma
frase pronta com o chapéu certo já escolhido — economia de digitação, não
capacidade nova. Texto depois do comando entra como complemento em vez de ser
descartado: quem digita "/why o banco" tinha algo específico em mente.

### O que foi verificado, e como

| Verificação | Resultado |
|---|---|
| `pytest -q` | **668 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend` | 48 passaram |
| `ruff check app tests` | limpo |
| `GET /ai/specialists?project_id=…` (painel real) | três perfis, atalhos resolvidos, um bilhete por botão |
| Clique num atalho (`git.status`, bilhete real) | `200`, pela mesma rota do botão de sempre |
| Migração `009` no banco efetivo | `agent` e `prompt_versao` presentes, versão `009_ai_especialista` |

**O que não foi verificado ao vivo:** a resposta de chat com chapéu fixado
gravando `agent` na tabela. O provedor local levou mais de 4 minutos e a sessão
foi encerrada antes. O caminho está coberto por teste de unidade
(`test_quem_respondeu_fica_gravado_com_a_versao_do_prompt`), mas a confirmação
no painel real fica para a próxima sessão — é o primeiro item a fazer.

### Situação ao encerrar

Fase 3 inteira entregue. Do Cockpit AI faltam as Fases 4 e 5, e o item 17
(integração com VS Code / Claude Code). Do HyperBrain, os MVPs 3 a 5 — e eles
seguem esperando **uso real da tela**, não código.

### Próximo passo

1. Abrir o painel e mandar uma pergunta com chapéu fixado; conferir que a bolha
   assina "Cockpit AI · QA" e que `ai_message.agent` foi gravado.
2. Usar os atalhos por alguns dias antes de acrescentar perfil ou botão. A
   sessão 24 já cobrou o preço de empilhar camada sem esse teste.

### Correção depois do fechamento — "database is locked" no clique do atalho

O primeiro clique em **Subir o servidor** devolveu "Erro interno" na tela. O log
disse o que era, e não tinha nada a ver com a Fase 3:

```
sqlite3.OperationalError: database is locked
[SQL: INSERT INTO dev_server (project_id, pid, command, ...)]
```

**A causa, que é anterior aos chapéus:** o repositório de mensagens só chama
`flush()`, nunca `commit()`. A pergunta era gravada **antes** do stream começar,
e a transação de escrita ficava aberta até o fim da requisição — com provedor
local, minutos. O SQLite admite um escritor por vez; nessa janela, qualquer
outra escrita falhava. O poller de health caiu junto, no mesmo segundo.

Ou seja: conversar com a IA travava o painel inteiro para escrita enquanto ela
respondia. O sintoma aparecia longe da causa — o erro surgia num botão que não
tem relação nenhuma com o chat, e foi por isso que passou despercebido até
agora.

**O conserto:** `commit()` logo depois de gravar a pergunta, e de novo depois de
gravar a resposta. A pergunta já está completa no primeiro ponto; não havia
razão para segurá-la. Somado a isso, `PRAGMA busy_timeout=15000` — o padrão do
driver são 5 s, e não substitui transação curta: só evita que um pico normal
vire erro na tela.

**O teste vale porque falha sem o conserto**, e isso foi verificado nos dois
sentidos: `test_a_pergunta_e_liberada_antes_do_stream_comecar` consome o
primeiro pedaço do stream e exige `not session.in_transaction()`. A primeira
versão do teste passava com e sem o conserto — olhava `session.dirty`, que fica
vazio depois do `flush`. Teste que passa dos dois jeitos não é teste.

Verificado no painel real: com uma resposta em stream, **seis escritas seguidas
devolveram 200**, e o log não registrou nenhum lock depois disso.

### Armadilha de plataforma, terceira aparição

Reinstalar o executável esbarrou em `VCRUNTIME140.dll` travada — desta vez por
`chrome-native-host.exe`, processo do Claude no Chrome, sem relação com o
projeto. O hash do arquivo instalado e do novo era **idêntico**, então a saída
foi copiar tudo menos ele (`robocopy /XF`) e conferir arquivo por arquivo que
nada faltou. Matar processo alheio para trocar um arquivo que não mudou seria
custo sem ganho.

---

## 2026-08-27 (tarde) — Sessão 28: portas, e o painel gravando o impossível

Sessão que começou com "os atalhos funcionam?" e terminou em três defeitos de
porta. Nenhum deles era do que tinha acabado de ser entregue.

### O que foi testado de verdade

O pedido era honesto: os atalhos da Fase 3 tinham sido verificados só no nível
de rota e bilhete, com um único clique real (`git.status`, leitura). Executados
nesta sessão, com bilhete emitido pelo servidor:

| Atalho | Resultado |
|---|---|
| Subir o servidor (`server.start`) | `200`, pid 9404, porta respondendo, auditado com `actor=ai` |
| Ligar o ambiente (`environment.up`) | job `SUCCESS`: imagem construída, rede criada, container de pé, aplicação subida |

Os outros oito continuam verificados só no nível de rota — e isso está dito na
tela, não escondido.

### O primeiro defeito: conversar travava a escrita do painel

O clique em "Subir o servidor" devolveu "Erro interno". O log dizia
`database is locked` num INSERT em `dev_server`.

O repositório de mensagens só chama `flush()`, nunca `commit()`. A pergunta era
gravada **antes** do stream começar, e a transação de escrita ficava aberta até
o fim da requisição — com provedor local, minutos. O SQLite admite um escritor
por vez: nessa janela, qualquer outra escrita falhava. O poller de health caiu
junto, no mesmo segundo.

Conversar com a IA travava o painel inteiro para escrita enquanto ela respondia,
e o sintoma aparecia num botão sem relação nenhuma com o chat.

O conserto é `commit()` depois de gravar a pergunta e depois da resposta, mais
`PRAGMA busy_timeout=15000` como segunda linha. Verificado no painel real: com
uma resposta em stream, **seis escritas seguidas devolveram 200**.

**A lição do teste:** a primeira versão dele passava com e sem o conserto,
porque olhava `session.dirty` — que o `flush` já esvazia. Teste que passa dos
dois jeitos não é teste. A versão final consome o primeiro pedaço do stream e
exige que a sessão não esteja em transação; foi verificada nos dois sentidos.

### O segundo: a porta do Node escorregava

Levantado o mapa de portas dos 19 projetos, **nenhuma declaração colidia**. O
conflito nascia noutro lugar: em `resolve_run_plan`, Python, subprojeto e
estático recebiam a porta declarada, e `plan_from_node` **não**.

Sem porta no comando, `npm run dev` de um Next pega a 3000 e, se ela estiver
ocupada, escorrega para a 3001 — em silêncio. Dois projetos que não conflitam
no cadastro passam a disputar o mesmo número, o verificador mede a porta errada
e o diagnóstico vira adivinhação. Era o caso do SmartDash, que subia na 3001
declarando 3013.

Agora o Node recebe a porta e a fixa com a bandeira do framework: `-p` no Next,
`--port --strictPort` no Vite (sem `strictPort` ele também desliza), `--port` em
Astro, Nuxt e Remix. Duas recusas deliberadas: script que já fixa a porta não é
sobrescrito, e framework desconhecido fica como está.

**Erro meu, pego pelo próprio teste do diff:** a primeira versão de
`_declared_port` preferia `web` a `backend` pelo nome, e escolhia a porta 3017
(container) na PLATAFORMA DE INGRESSOS, onde quem sobe é o `runserver` da 3002.
Ordem é o que o projeto declarou; nome é o que o painel imagina. Ficou: pula
serviço TCP (para não mandar o Next subir na porta do Postgres) e, entre HTTPs,
respeita a ordem declarada.

Medido nos 19 projetos: **3 comandos Node mudam, nenhum Python.**

### O terceiro: o painel gravava estado impossível

A tela de Ports do AgilContabil mostrava três serviços declarados na **mesma
porta 3000**, com rótulos dizendo 5442 e 9010. Não era projeto mal configurado:

- `PUT /services` **não auditava** — a troca das três portas não estava no log,
  e "quem mudou isso?" não tinha resposta;
- **aceitava porta duplicada** no mesmo projeto, e a tela avisava depois sobre a
  inconsistência que o próprio painel gravou;
- **o rótulo não acompanhava a porta**: `App (5442)` numa linha cuja porta é
  3000 são dois números discordando, e o da esquerda é o que se lê primeiro.

Os três consertados. O rótulo com porta embutida é gerado pelo próprio painel ao
cadastrar uma porta observada, então só ele é reescrito — `Postgres` fica como
está.

O teste que criava a duplicata pela API passou a criá-la direto no banco: a tela
precisa continuar sabendo mostrar o caso, porque instalação antiga tem linhas
gravadas antes da regra.

### HyperBrain

O contexto do nó era uma coluna de 320px à direita, cobrando largura do grafo em
tempo integral para mostrar, quase sempre, o convite a selecionar um nó. Virou
faixa horizontal no topo: vazia ocupa uma linha, cheia deita o cartão.

Comparadas as duas telas lado a lado, com 19 projetos: antes os nós da direita
ficavam **cortados na borda**; agora cabem. A sobreposição entre nós vizinhos
existia antes e continua — é do layout, não da largura.

### Duas armadilhas de plataforma

**O banco efetivo não é o do repositório.** `alembic upgrade head` rodou e as
colunas não apareceram em `data/devcockpit.db`: o banco real é
`C:/Users/User/DevCockpit/data/devcockpit.db`, porque `settings.resolve`
reescreve o caminho relativo.

**Migração nova quebra o executável instalado.** O `.exe` carrega as migrações
empacotadas dentro dele; com o banco na 009 e o bundle na 008, o painel abre com
"Can't locate revision identified by '009_ai_especialista'". Migração nova =
reconstruir e reinstalar junto.

Na reinstalação, `VCRUNTIME140.dll` estava travada — desta vez pelo
`chrome-native-host.exe`, sem relação com o projeto. Hash idêntico ao novo, então
a saída foi copiar tudo menos ele (`robocopy /XF`) e conferir arquivo por arquivo
que nada faltou.

### Situação ao encerrar

Publicado até `fb2ab2a`, árvore limpa. 681 testes, 48 no frontend, ruff limpo.

O painel está no ar (PID 6112) com o **executável antigo**: as correções desta
tarde ainda não estão nele. Dois arquivos do HyperBrain (`hyperbrain.css` e
`hyperbrain.js`) foram copiados à mão para a instalação para ver o layout, então
a instalação está adiante do bundle nesses dois e atrás em todo o resto.

Containers de pé: `agilcontabil-postgres-1`, `agilcontabil-minio-1`, e
`eventos_api`/`eventos_db`, que não foram subidos por esta sessão. Os do kiteasy
foram derrubados com `docker compose down` depois do teste.

### Próximo passo

1. **Reconstruir e reinstalar** — é o que leva as três correções para o painel
   que você usa, e sincroniza os dois arquivos copiados à mão.
2. **Consertar os dados do AgilContabil**, que a regra nova impede piorar mas
   não desfaz: Postgres na 5442, MinIO em 9010/9011, e a porta real do backend —
   que segue em aberto, porque o comando detectado diz 3012 e o cadastro dizia
   3010. Decisão do usuário: rodar a detecção ou informar os números.

## 2026-08-27 (noite) — Sessão 29: o executável alcança o repositório

Sessão curta, dois itens: levar as correções da tarde para o painel instalado e
desfazer o cadastro torto do AgilContabil.

### Reinstalação, e a armadilha da quarta vez

O painel estava rodando na **8790**, não na 8765: quando ele subiu, a 8765
ainda estava ocupada pela instância da tarde, e ele escolheu outra. Vale saber
disso antes de concluir que o painel está fora do ar.

O `robocopy /MIR` travou por cinco minutos. Causa: **um DevCockpit voltou a
subir** depois que eu parei o anterior, segurando o `_internal` inteiro — e o
robocopy tenta de novo um milhão de vezes, esperando 30 s entre elas, por
padrão. Com `/R:2 /W:1` o problema vira erro em segundos em vez de espera
indefinida.

O `VCRUNTIME140.dll` seguia travado, agora pelo VS Code. Hash idêntico, então
continua fora do espelhamento (`/XF`), com conferência arquivo a arquivo depois:
**0 faltando**, e o `.exe` com hash igual ao do build.

### O cadastro do AgilContabil

O projeto já tinha a verdade escrita em `infra/.env`, e ninguém tinha olhado
lá: `POSTGRES_PORT=5442`, `MINIO_PORT=9010`, `MINIO_CONSOLE_PORT=9011`,
`BACKEND_PORT=8100`.

O cadastro dizia outra coisa — três serviços na porta 3000, rótulos citando
portas que não eram as deles, e o Postgres marcado como **HTTP**, o que sozinho
já garantiria verificação falhada para sempre.

Decisão do usuário: backend em **8100**, a mesma do Compose. Vale para as duas
formas de subir; se o container e o servidor nativo forem ligados juntos, o
segundo não sobe — e esse é o aviso correto, não um defeito.

| | antes | depois |
|---|---|---|
| Backend | `App (5442)` · 3000 · HTTP | `Backend` · 8100 · HTTP |
| Postgres | `App (5442)` · 3000 · HTTP | `Postgres` · 5442 · **TCP** |
| MinIO | `App (9010)` · 3000 · HTTP | `MinIO` · 9010 · HTTP |
| Console | `App (9011)` · 3010 · HTTP | `MinIO Console` · 9011 · HTTP |

### O que os três consertos da tarde provaram valer, no painel real

1. **O comando seguiu o cadastro sozinho:** virou `--port 8100`, e **pulou o
   Postgres** porque agora é TCP. Era exatamente para isso que `_declared_port`
   passou a ignorar serviço TCP — sem isso, mandaria o `uvicorn` subir na porta
   do banco.
2. **A auditoria registrou `services.replace`**, que antes não deixava rastro
   nenhum.
3. **Porta duplicada foi recusada com `422`** e mensagem dizendo de quem é a
   porta, com o cadastro intacto depois da recusa — nada gravado pela metade.

E o fim da linha: `server.start` subiu o backend na 8100, `/docs` respondeu
`200`, e os quatro serviços do projeto ficaram **ONLINE**. É o mesmo projeto que
abria a sessão passada dizendo "0/4 online".

Um susto no caminho: a primeira verificação deu `OFFLINE` nos três containers. O
`docker ps` mostrou `Up Less than a second` — estavam reiniciando naquele
instante. Segunda verificação, todos no ar.

### Situação ao encerrar

Painel instalado **igual ao build**, rodando na 8765 com as correções de hoje.
681 testes, ruff limpo, árvore publicada.

No ar agora: backend do AgilContabil (nativo, 8100), containers `postgres` e
`minio` do mesmo projeto, e `eventos_api`/`eventos_db`, que não são desta sessão.

### Próximo passo

O cadastro de porta dos **outros 18 projetos** nunca foi conferido contra o que
cada um declara em `.env` ou Compose. O AgilContabil só apareceu porque quebrou
na cara. Vale uma varredura que compare cadastro × arquivo do projeto e liste as
divergências — sem corrigir nada sozinha, porque a decisão de qual número vale é
de quem conhece o projeto.

## 2026-08-27 (noite) — Sessão 30: o prompt de caça em uso

O prompt de caça de bugs foi escrito e imediatamente usado. Quatro defeitos,
todos do formato que ele nomeia, nenhum encontrado por acaso.

### Padrão 7 — correção que para na raiz (dois casos)

A busca profunda de Compose entrou na detecção e na aba Docker, e **duas outras
buscas continuaram só na raiz**:

- `environment_service._compose_file` — e aqui a consequência é pior que uma
  tela vazia: `plano.compose_file` ficava `None`, então **"Ligar o ambiente"
  subia a aplicação e pulava os containers**. No AgilContabil, isso é o app no
  ar sem Postgres nem MinIO, sem o painel dizer que faltou algo.
- `manifest_service._docker_section` — exportar um projeto com Compose em
  `infra/` produzia manifesto sem a seção `docker`.

### Padrão 3 — a terceira porta de entrada

A regra de porta única vivia dentro de uma função de rota. A tela recusava
duplicata, a detecção passou a pular, e a **importação de manifesto continuava
gravando**. Três caminhos para a mesma tabela, uma cópia da regra.

Agora ela mora em `app/services/portas.py`, e o manifesto valida o estado
**resultante** — não só o que ele traz: importar um serviço na porta de outro
que já existe grava a mesma duplicata.

### Padrão 6, aplicado a um lugar novo — o launcher

Porta ocupada tinha uma resposta só: pegar a próxima livre. Quando quem ocupa é
o **próprio** DevCockpit, isso sobe uma segunda instância — e duas instâncias
contra o mesmo SQLite disputam a escrita.

É a origem de um sintoma já visto: "database is locked" num botão sem relação
com o que estava sendo feito. E de outro, mais silencioso: depois de reconstruir
o executável, a janela aberta continua servindo o código velho, então um
conserto recém-instalado parece não ter funcionado. Isso aconteceu **nesta
sessão**, duas vezes, antes de eu perceber a causa.

O launcher agora pergunta quem está na porta, pela assinatura do `/api/health` —
não só por um `200`, porque qualquer servidor responde 200 e mandar a pessoa
para a tela de outro programa seria pior.

Verificado ao vivo: a segunda abertura respondeu "o DevCockpit já está aberto em
http://127.0.0.1:8765" e encerrou; uma instância, uma porta.

### Dois falsos positivos, descartados com evidência

- **site3d com `app_online=True`** parecia mentira. Não era: há um Next servindo
  de `C:\Users\User\Desktop\SITE3D` na 3006.
- **smartdash** sobe na 3001 declarando 3013. É dado do projeto, não defeito do
  painel — que já avisa, com a mensagem certa, no aviso de porta divergente.

### As três regras de "qual serviço é a aplicação"

Medidas nos 19 projetos, elas discordam em **um**: o smartdash, cujo backend
está cadastrado como TCP. Não vale unificar agora — o custo seria alto e o
ganho, um projeto com dado torto. Fica registrado como dívida conhecida:

| Onde | Regra |
|---|---|
| `dev_server_service._declared_port` | primeiro HTTP (pula TCP de propósito) |
| `environment_service._app_service_key` | primeiro com porta |
| `projects.py` (colore o grafo) | primeiro com `open_in_browser` |

### Situação ao encerrar

Publicado até `319780f`. 696 testes, 51 no frontend, ruff limpo. Painel
instalado igual ao build, uma instância na 8765.

### Próximo passo

O prompt tem sete padrões e a sessão usou quatro. Faltam varrer o **padrão 2**
(`null` virando `0`) fora do card de projeto, o **4** (ordem decidindo o que
deveria ser evidência) fora da detecção, e o **5** (transação longa) nas rotas
de job.

## 2026-08-28 — Sessão 31: o campo que a rota esquecia

Continuação da caça, pelos padrões que a sessão anterior não tinha varrido.

### O buraco no meu próprio conserto (padrão 7, de novo)

A checagem de instância única entregue ontem perguntava "quem está na porta
preferida?" e parava aí. O painel estava na **8790**, aberto com `--port 8790`,
e abrir o atalho subiu uma segunda instância na 8765 livre — o defeito que a
checagem existia para impedir, intacto. Reproduzido: duas instâncias, dois
pollers.

Varrer a faixa 8765–8785 não resolve: porta arbitrária fica fora de qualquer
faixa razoável, e o teste que escrevi para isso falhou por essa razão. A
instância que sobe passou a **anotar** porta e PID em `runtime.json`, no
diretório de dados que todas compartilham.

A anotação não é prova — o arquivo sobrevive a encerramento abrupto —, então
quem decide continua sendo a resposta do `/api/health`. A varredura ficou como
segunda fonte, para instância de versão antiga.

### O campo que a rota esquecia (padrão 2)

A resposta do dashboard se contradizia ao vivo: **sete serviços ativos e a lista
de medidos vazia**, no mesmo objeto.

A rota montava `DashboardOut(...)` e não passava `checked_project_ids`. O
serviço calculava, o schema declarava, e o campo chegava sempre vazio. Ou seja:
a distinção entre "nenhum serviço respondeu" e "ninguém perguntou ainda" existia
no código e **nunca chegou à tela** — o conserto anterior só trocou um rótulo
errado por outro.

Junto, o outro lado do mesmo defeito: a barra lateral fixa nunca recebeu a
distinção. Era ela que dizia "0/1 online · Desligado" para projeto com os
containers de pé. Agora diz "N serviço(s) · não verificado", com o ponto vazado
em vez de vermelho.

Depois do conserto, no painel real: `checked_project_ids` com **12 projetos**,
contra zero antes.

### Teto de exibição virando contagem errada (padrão 4)

`_active_services` cortava em 20 e `_pending_changes` em 10, e nenhum dos dois
era corte de exibição: a lateral e o card **contam** a partir da primeira lista,
e a página de Projects lê a segunda para o chip de Git de cada card.

Com projetos suficientes no ar, um projeto inteiro de pé apareceria como "3/6
online". O corte foi para a tela; quem conta recebe tudo.

### Uma suspeita medida e descartada (padrão 5)

`environment.up` mantém a sessão aberta durante minutos de `docker compose`. A
hipótese era transação longa segurando o banco. **Falsa**: a sessão só lê, e o
driver do SQLite não abre transação de verdade antes da primeira escrita — uma
sessão com leitura aberta vê o que outra gravou depois, verificado por
experimento. Fica registrado como conferido, para não voltar como suspeita.

### O conserto que funcionou contra o usuário

Durante os testes o painel ficou rodando com `--no-browser` — servidor sem
janela. Aí a checagem de instância única fez exatamente o que devia e o
resultado foi péssimo: o atalho recusou abrir um segundo painel, e não havia
tela nenhuma para o usuário. "O executável não está pegando."

Duas coisas saíram disso. O painel voltou com janela, e o comportamento mudou:
com um painel já aberto, o atalho **traz a janela existente para a frente**
(`EnumWindows` filtrando pelo PID anotado). O navegador continua como
alternativa, para quem subiu em modo servidor — ficar sem nada é pior.

Verificado no painel real: segunda abertura respondeu "janela trazida para a
frente", nenhuma instância nova.

**Ponta solta assumida:** o Windows recusa `SetForegroundWindow` para processo
em segundo plano em certas situações. Quando isso acontecer, o certo é piscar o
ícone na barra em vez de fingir que trouxe. Não foi implementado porque não foi
reproduzido.

### Risco latente medido, e não consertado

`_app_service_key` escolhe a aplicação pelo **primeiro serviço com porta**, sem
pular TCP — enquanto `_declared_port` pula de propósito. Se um projeto declarar
o banco antes da aplicação, o ambiente trataria o banco como app e esperaria a
porta do app antes de subi-lo: espera que nunca termina.

Medido nos 19 projetos: **nenhum** cai nesse caso hoje. Fica anotado como risco,
não como defeito — consertar sem dano observado seria mexer por palpite.

### Situação ao encerrar

Publicado até `79119b9`. 704 testes, 55 no frontend, ruff limpo. Painel
instalado igual ao build, uma instância com janela.

### Próximo passo

Do prompt, sobra varrer o **padrão 4** fora do dashboard e o **1** (duas fontes
para o mesmo fato) fora do que já foi visto. A dívida das três definições de
"qual serviço é a aplicação" segue registrada e não paga — discordam em um
projeto, o smartdash, por dado torto dele.
