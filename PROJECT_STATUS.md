# DevCockpit — Project Status

**Última atualização:** 2026-08-25 (Fase 3.4: a IA propõe ação e a pessoa confirma)

---

## Fase atual

**EM USO** — desenvolvimento guiado pelo uso real

**Status:** MVP entregue. A partir daqui, o que entra no backlog vem do que
incomoda no dia a dia, não de um plano feito antes de existir produto.

### Como registrar o que aparecer

Anote aqui embaixo, sem cerimônia. Uma linha basta.

```
## Anotações de uso

- [ ] (data) o que incomodou / o que faltou
```

## Anotações de uso

- [x] (2026-08-21) `@app.on_event` estava deprecado no FastAPI e gerava 385
      warnings na suíte. Migrado para `lifespan` em `app/main.py`. Sobra um
      único warning, de terceiro (`starlette.testclient` pedindo `httpx2`).
- [x] (2026-08-21) Rodada no browser encontrou quatro defeitos, todos
      corrigidos: dois `null` renderados na aba Manifest (`replaceChildren` não
      filtra nulos como o `mount`); cabeçalho do projeto com o nome antigo
      depois de importar; card "Rodando" sempre 0 no dashboard; e check TCP
      dando OFFLINE para serviço IPv4 cadastrado como `localhost`.
- [x] (2026-08-21) VS Code, Pasta e Terminal agora aparecem no card da lista de
      projetos, não só na aba Overview.
- [x] (2026-08-21) Bug relatado por você: botão VS Code com o cursor de
      bloqueado. O cache de `GET /api/health` guardava também a falha, então
      uma página aberta com o servidor fora do ar deixava as ferramentas
      desabilitadas pelo resto da sessão. Agora só o sucesso é cacheado e o
      rodapé revalida a cada 60 s (D-45).

- [x] (2026-08-22) Bug relatado por você: "o único botão que não tá
      funcionando é do VS Code". A auditoria registrava `SUCCESS` em toda
      execução — e estava certa. `code <path>` reaproveita a janela aberta e
      devolve 0 sem mostrá-la, porque o Windows recusa `SetForegroundWindow`
      vindo de processo sem foco. A pasta abria atrás do browser (D-46).
- [x] (2026-08-22) Item B2 entregue: card com sinais, busca unificada,
      dashboard com mapa de portas e camada visual retrabalhada (D-47, D-48).
- [x] (2026-08-22) "Por que tá quebrando o processo?" — não estava. O uvicorn
      era filho da chamada de ferramenta do agente e caía junto com qualquer
      interrupção. `scripts/serve.ps1` sobe solto do terminal (D-49, D-50).
- [x] (2026-08-22) "Não vi modificação no layout" — o servidor entregava o
      arquivo novo; faltava `Cache-Control` no frontend, então o navegador
      guardava CSS e JS sem nunca revalidar (D-51).

- [x] (2026-08-22) Polimento de layout pedido por você: barra lateral
      recolhível (`Ctrl+B`), trilho de projetos ativos como coluna própria à
      direita dela, e o liga/desliga do projeto virando uma chave de estado
      única — no card, no trilho e no cabeçalho do projeto (D-52, D-53, D-54).
- [x] (2026-08-22) "Trocar as portas do servidor local pra ter mais autonomia":
      tela **Ports**, com o mapa das portas declaradas, o conflito marcado e a
      troca do número na própria linha, com sugestão de porta livre. Ela edita
      o registro do DevCockpit, nunca o arquivo do projeto (D-55, D-56).
- [x] (2026-08-26) "Dificuldade pra subir os projetos, terminais com conflito":
      três causas distintas. Pré-voo de porta antes de ligar (o conflito
      aparecia só pelo erro do Compose); detecção por import no código,
      monorepo e site estático (sete projetos sem botão viraram zero); e a aba
      Server oferecendo cadastrar a porta que o framework escolheu.
- [x] (2026-08-25) Cockpit AI, Fase 2 entregue: chat contextual com stream,
      três provedores (Anthropic, OpenAI, Ollama local), Context Engine com
      orçamento e proveniência, redação de segredos e teto de gasto. Desligado
      por padrão — o painel só deixa de ser local quando você decide.
- [x] (2026-08-25) Cockpit AI, Fase 1 entregue: sessão de trabalho com resumo
      montado dos fatos observados (commits pelo corte de sha, ações, quedas),
      memória de projeto e global com origem declarada, e a tela "Meu dia".
      Nada disso usa IA — é o que dá à Fase 2 fato para ler em vez de dedução.
- [x] (2026-08-23) "Subiu 3 projetos ativos sem eu pedir": nada subiu — o
      painel é que afirmava "no ar" só porque a porta respondia. A atribuição
      de porta de container passou a vir do rótulo do Compose (fato, não
      palpite), e o dashboard separa "no ar, deste projeto" de "porta ocupada".
      "Rodando" caiu de 5 para 1, que era o número certo.
- [x] (2026-08-23) "Não quer desligar": servidor iniciado fora do painel ficava
      fora do alcance do botão. `down()` agora encerra processo não gerenciado
      do próprio projeto, com a mesma defesa D4 de sempre.
- [x] (2026-08-23) "A página vai direto pro módulo de Ports": o timer da tela
      se protegia com `container.isConnected`, e o `<main id="view">` nunca sai
      do DOM. O roteador ganhou `aoSairDaRota()`.
- [x] (2026-08-23) Varredura geral de portas: 6 serviços com número que nenhum
      projeto declarava (resíduo do "Sugerir livre" antigo) e 1 serviço
      duplicado. Zero divergência entre cadastro e arquivo depois disso.
- [x] (2026-08-23) Primeiro teste de frontend do projeto: DOM mínimo escrito à
      mão, runner do Node, dez casos cobrindo roteador e dashboard. Sem build e
      sem `node_modules`, como manda o ADR-005.
- [x] (2026-08-23) Dashboard: painéis "Disponibilidade" e "Ações mais
      executadas" retirados a pedido. Sobraram Atividade, Horário de trabalho e
      Stack. O backend segue calculando e gravando o histórico — parar isso
      devolveria `health_snapshot` a schema sem escrita, e sem histórico
      acumulado o painel não teria como voltar.
- [x] (2026-08-23) "Falha na requisição (404)" no painel de análise: o servidor
      no ar era anterior à rota. O painel passa a distinguir esse 404 e mandar
      reiniciar, em vez de sugerir dado ausente.
- [x] (2026-08-23) "Vamos fazer um executável": `scripts/build_exe.ps1` gera
      `dist/DevCockpit` (~40 MB) com `DevCockpit.exe`. A pasta é autocontida e
      portátil — banco, log e `configs/` nascem ao lado do executável na
      primeira execução. Defeito achado ao testar o pacote: a porta escolhida
      não chegava às `Settings`, e subir fora da 8765 dava 403 em todo botão
      com a tela carregando normal.
- [x] (2026-08-23) "Vamos melhorar o dashboard, preciso de gráficos de
      análise": cinco painéis no fim do dashboard, alimentados por
      `activity_log` (já havia dado) e por `health_snapshot`, que existia desde
      a Fase 4 sem ninguém escrever nela. Junto vieram a retenção das duas
      tabelas e o teto do job de varredura — três configurações que estavam no
      arquivo sem serem lidas.
- [x] (2026-08-22) Defeito achado ao testar a troca de porta no browser:
      `PUT /api/projects/{id}/services` respondia **200 e não gravava**. O
      `clear()` seguido de `append()` fazia o SQLAlchemy emitir os INSERT antes
      dos DELETE na mesma descarga; `UNIQUE(project_id, key)` estourava depois
      da resposta e a transação era desfeita em silêncio. Um `flush()` entre os
      dois resolve; há teste de regressão que falha sem ele.

## Prioridades (revisadas em 2026-08-22)

Ordem de execução acordada. O critério não é esforço, é dano: primeiro o que
faz o painel mentir ou crescer sem limite, depois o que ainda não existe,
depois o que protege o que já existe.

### ~~P0 — Gráficos de análise no dashboard~~ — entregue em 2026-08-23

O dashboard hoje responde "agora": quantos online, quais portas em conflito.
Não responde "e antes?" — que é a pergunta que separa rotina de aviso. Duas
fontes já estão no banco:

- `activity_log` tem ação, status, duração e horário de tudo que o painel
  executou. Dá volume por dia, taxa de erro por ação e duração típica **sem
  escrever uma linha de coleta** — os dados já estão lá.
- `health_snapshot` tem a forma certa para uptime e latência por serviço, mas
  **nada escreve nela**. O poller já mede; falta gravar.

Por isso este item absorve a pendência das tabelas mortas: gravar
`health_snapshot` deixa de ser dívida e vira a fonte do gráfico.

1. ~~Gráficos sobre `activity_log`~~ — atividade por dia, por hora e por ação,
   com taxa de erro e p50/p95 de duração
2. ~~Persistir `health_snapshot` no poller~~ — grava na mudança de estado e, sem
   mudança, a cada cinco minutos
3. ~~Gráficos de uptime e latência por serviço~~ — uptime ponderado por tempo,
   com `coverage_pct` ao lado: amostragem não afirma o que não mediu

### ~~P1 — Retenção do log de atividade~~ — entregue em 2026-08-23

`RetentionService` roda dentro do poller, de hora em hora, com retenção separada
por tabela (`activity_retention_days`, `health_snapshot_retention_days`).
`timeout_scan` virou teto do job de varredura — job que estoura termina como
`TIMEOUT` e libera a chave, em vez de ficar `RUNNING` recusando 409 para sempre.

### P1b — Empacotamento — entregue em 2026-08-23

`scripts/build_exe.ps1` gera `dist/DevCockpit`. O que sobra aqui: decidir se as
versões viram release versionada, e se um ícone próprio vale o trabalho.

### P2 — Higiene de repositório (risco de perder trabalho)

- `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- branch `varredura/bugs-e-organizacao` com 30 commits fora da `main`
- três edições no SmartDash (compose, Dockerfile, cadastro) não commitadas,
  dentro de um repo maior com 24 arquivos de outros projetos modificados

### P3 — Verificações manuais pendentes desde 21/08

Baratas e desbloqueiam afirmações que o painel faz hoje sem confirmação:

- clicar em VS Code e confirmar que a janela vem para frente (D-46)
- conferir a aba Docker com o Docker Desktop desligado

### P2b — Teste

- ~~zero teste de frontend~~ — a base existe desde 2026-08-23 (`tests/frontend`,
  dez casos). Falta cobrir Ports, projects e o painel de análise, que são
  justamente as telas onde os defeitos apareceram
- `git_service` a 47% de cobertura, o menor do projeto (total em 89%)

### P5 — Dúvida de modelagem, sem urgência

- o SmartDash usa SQLite no `.env` local e sobe um Postgres no Compose que a
  aplicação ignora — o serviço `db` cadastrado pode ser ruído

---

## 🏁 MVP COMPLETO

Fases 0, 1, 2, 3a, 3b e 4 fechadas: **131 de 131 pontos**. Os 12 casos de uso
do PRD estão implementados. O que vem a seguir (GitHub, Dev Assistant) é
pós-MVP e opcional.

---

## Concluído

### Fase 0

- [x] Análise crítica do prompt, com inconsistências e lacunas registradas
- [x] `00-product-vision.md`
- [x] `01-product-requirements.md`
- [x] `02-functional-requirements.md` — 62 requisitos com ID
- [x] `03-non-functional-requirements.md` — 8 categorias
- [x] `04-system-architecture.md` — camadas, 4 diagramas Mermaid, estrutura
- [x] `05-data-model.md` — 6 entidades, índices, o que não persistir
- [x] `06-api-specification.md` — endpoints, payloads, tabela de erros
- [x] `07-security-model.md` — 9 ameaças, 10 defesas, 14 testes obrigatórios
- [x] `08-project-configuration-spec.md` — formato resolvido
- [x] `09-development-roadmap.md` — 8 fases (3 dividida em 3a/3b) com critério de saída
- [x] `10-testing-strategy.md` — pirâmide, fakes, fixtures, metas
- [x] `11-ui-ux-spec.md` — design system, telas, acessibilidade
- [x] `12-decisions.md` — 22 decisões menores, divergências, 6 questões abertas
- [x] `13-backlog.md` — 10 épicos, 44 histórias, 131 pontos
- [x] ADR-001 a ADR-007
- [x] Estrutura de diretórios
- [x] `README.md`, `.gitignore`, `.env.example`
- [x] `configs/roots.example.yml`, `configs/defaults.yml`
- [x] `PROJECT_STATUS.md`

---

### Fase 1 (concluída em 2026-08-21)

- [x] `US-001` bootstrap: FastAPI, settings, log JSON, bind loopback validado
- [x] `US-002` `core/paths.py` — 98% de cobertura (a linha restante é o ramo POSIX, inalcançável no Windows)
- [x] `US-003` `CommandRunner` + `FakeCommandRunner` + testes de higiene do código-fonte
- [x] `US-004` migração 001 e modelo base, com WAL e foreign keys ligadas
- [x] `US-005` hierarquia de erro de domínio e `correlation_id`
- [x] `US-006` guards de `Host` (D10) e `Origin` (D5)
- [x] `US-010` a `US-012` CRUD de projetos
- [x] `US-013` frontend base: shell, roteador por hash, 5 telas, tokens de CSS
- [x] `US-081` (base) log de auditoria

Ajustes de escopo aplicados nesta sessão, a pedido:

- [x] defesa D10 (`Host`) adicionada ao modelo de segurança — fecha DNS rebinding
- [x] Fase 3 dividida em 3a (jobs) e 3b (Docker)

---

### Fase 2 (concluída em 2026-08-21)

- [x] `US-020` registry com 12 detectores; adicionar stack é adicionar arquivo
- [x] `US-021` extração de porta do Compose e do `vite.config.*`
- [x] `US-022` re-detecção com diff, respeitando `detection_locked`
- [x] `US-023` varredura de diretório (síncrona e limitada — ver D-23)
- [x] `US-024` importação em lote com falha parcial isolada
- [x] `US-030` estado do repositório com `--porcelain=v2`
- [x] `US-031` commits, branches e remotes
- [x] `US-032` aba Git na página do projeto
- [x] `US-033` ausência de rota de escrita Git verificada por teste
- [x] `US-014` projeto com diretório ausente destacado na UI
- [x] migração 002 (`git_repository`)
- [x] **ADR-008** — bug encontrado por teste: `git` sobe a árvore e faria todo
      projeto abaixo de `C:/Users/User` exibir a branch e os arquivos sujos do
      repositório pai

---

### Fase 3a (concluída em 2026-08-21)

- [x] `US-043` harness `scripts/job_probe.py` — linhas com atraso, código de
      saída configurável, modo que ignora término, criação de filhos
- [x] `US-040` `JobManager`: estados, saída incremental, timeout, exclusão
      mútua por chave, cancelamento, teto de saída, retenção
- [x] `AsyncCommandRunner` — saída linha a linha sem bloquear o event loop
- [x] encerramento de árvore de processos (`taskkill /T /F` no Windows,
      `killpg` em POSIX), isolado em `app/runner/process.py`
- [x] `US-041` rotas de job: consulta com `after`, listagem, cancelamento, SSE
      com keep-alive e fallback para polling
- [x] `US-042` `JobConsole` na UI: saída ao vivo, autoscroll pausável,
      cancelamento, indicação do transporte em uso
- [x] varredura migrada para job, cumprindo D-23 — `POST /scan` agora é 202

---

### Fase 3b (concluída em 2026-08-21)

- [x] `US-050` `DockerAdapter` — `compose ps --all --format json`, tolerante a
      array e a JSON-por-linha, ignorando avisos intercalados
- [x] portas lidas de `Publishers` (estruturado), com IPv4/IPv6 deduplicados
- [x] migração 003 (`docker_config`) e modelo `DockerConfig`
- [x] `US-051` ações Compose via job: up, down, start, stop, restart
- [x] validação de nome de serviço contra o Compose do projeto — desconhecido
      é 422 e nenhum comando roda
- [x] `US-052` logs com `tail` configurável
- [x] `US-053` aba Docker na UI, reaproveitando o `JobConsole`
- [x] degradação: daemon fora do ar devolve 200 com `available: false`

---

### Fase 4 (concluída em 2026-08-21)

- [x] `US-060` cadastro e substituição de serviços por projeto
- [x] `US-061` health check HTTP e TCP, concorrente, timeout de 2 s
- [x] `US-062` poller em background, cache e estado `STALE` após 3 ciclos
- [x] `US-063` mapa de portas com detecção de conflito
- [x] `US-070` `OSAdapter` para Windows, macOS e Linux: VS Code, pasta,
      terminal (com fallback de `wt.exe` para PowerShell)
- [x] `US-071` abrir URL por `service_key`, nunca por URL do cliente
- [x] `US-072` UI desabilita ação cuja ferramenta não existe, com o motivo
- [x] `US-080` dashboard agregado servido de cache
- [x] migração 004 (`health_snapshot`)
- [x] **Q-02 resolvida**: poller verifica fixados + acessados nos últimos N dias

---

### Fechamento das pontas soltas (2026-08-21)

- [x] `US-090` importar `devcockpit.yml`: schema da spec 08 validado, versão
      desconhecida e YAML inválido viram aviso, `compose_file` que escapa do
      projeto é recusado com `403`
- [x] `US-091` exportar e comparar: escrita com confirmação explícita,
      comparação campo a campo sem alterar nada, prévia do YAML antes de gravar
- [x] importação automática no cadastro de projeto que já tem o arquivo (FR-110)
- [x] aba **Manifest** na UI, com diff, avisos e prévia
- [x] tema claro por tokens, com opção "Sistema"; preferência no `localStorage`
- [x] migração de `@app.on_event` para `lifespan` (385 warnings a menos)
- [x] `D-37` a `D-41` registradas em `docs/12-decisions.md`

Verificado ao vivo, com projeto descartável no Desktop e servidor em porta
separada:

- [x] cadastro importou o manifesto sozinho: nome, descrição e serviço `api`
- [x] divergência apareceu em 4 campos, sem alterar nada
- [x] exportar sem `confirm` devolveu `422` e **não** tocou no arquivo
- [x] ida e volta (importar, exportar) deixou o projeto `in_sync`
- [x] `compose_file: ../../fora/...` recusado com `PATH_NOT_ALLOWED`
- [x] `health: http://evil.example.com/ping` invalidou o manifesto, com aviso
- [x] YAML quebrado devolveu `200` com aviso, projeto intacto

Ambiente devolvido ao estado original: projeto descartável, registro e banco de
teste removidos.

---

## Em andamento

Nada. Fases 1 e 2 do Cockpit AI entregues em 2026-08-25 (`docs/ai/`). A Fase 3
— especialistas, orquestrador e ações propostas — espera uso real do chat.

---

## Critério de saída da Fase 4 — verificado

Ao vivo, com o servidor e os serviços reais da máquina:

- [x] `GET /api/dashboard` em **168 ms** — bem abaixo dos 500 ms exigidos
- [x] segunda chamada marca `from_cache: true`
- [x] poller encontrou serviços reais sozinho: ZAPBOT Database (5433) e
      Dashdate (8123), ambos `ONLINE`
- [x] verificação sob demanda distingue `ONLINE`, `OFFLINE` e `ERROR`
      (porta 8000 do Dashdate: tempo esgotado, reportado como `ERROR`)
- [x] mapa de portas monta o índice e aponta conflitos
- [x] `GET /api/health` informa git, docker e code disponíveis — é o que a UI
      usa para desabilitar botão antes do clique
- [x] serviço inexistente em `open/browser` devolve 422 com a lista de chaves
- [x] payload com `url` em vez de `service_key` é rejeitado (D-13)
- [x] 285 testes passando, cobertura 92%
- [x] `ruff check` sem apontamento

---

## Critério de saída da Fase 3b — verificado

Com Docker real (Docker 29.7.2, Compose v5.3.1):

- [x] leitura do ZapCRM real: 1 container rodando, porta 5000, health
      `unhealthy`, serviços declarados `['zap-crm']`
- [x] logs reais devolvidos com `tail` configurável
- [x] `compose up` num projeto descartável: **573 ms**, saída incremental
      (2 linhas, depois 6), container criado de fato
- [x] `compose down` removeu container e rede
- [x] segundo `down` simultâneo devolveu `409 OPERATION_IN_PROGRESS`
- [x] serviço inexistente devolve 422 com a lista de disponíveis, sem executar
- [x] `prune`, `rm`, `kill`, `exec` devolvem 422 — nenhum verbo fora do
      conjunto fechado passa
- [x] projeto sem Compose devolve 200 com explicação, não erro
- [x] `-v` inalcançável por qualquer caminho da API (teste dedicado)
- [x] 242 testes passando, cobertura 93%
- [x] `ruff check` sem apontamento

Ambiente de teste devolvido ao estado original: container, rede e pasta
descartáveis removidos, registro do projeto de teste apagado.

---

## Critério de saída da Fase 3a — verificado

- [x] job com saída longa aparece **incrementalmente** (verificado com processo
      real, não só com fake)
- [x] cancelamento encerra em menos de 2 s
- [x] processo com `--ignore-term` morre mesmo assim
- [x] filhos morrem junto com o pai
- [x] **20 execuções seguidas não deixam processo órfão**
- [x] segundo job na mesma chave devolve 409; chaves diferentes rodam em
      paralelo (medido: 2 jobs de 1 s terminam em menos de 2 s)
- [x] SSE emite `log` e `end`; polling com `after` cobre a queda do stream
- [x] 190 testes passando (187 + 3 lentos), cobertura 92%
- [x] `ruff check` sem apontamento

Verificado ao vivo: varredura do Desktop em profundidade 3 devolveu 202,
concluiu em **179 ms** com 36 candidatos em 120 diretórios, e a segunda
varredura simultânea recebeu `409 OPERATION_IN_PROGRESS`.

---

## Critério de saída da Fase 2 — verificado

- [x] varredura real do Desktop: **31 candidatos em 0,19 s**, 56 diretórios
      percorridos, stack correta (Dashdate, MarketLab, AI Procedures, ZapCRM…)
- [x] importação em lote de projetos reais, com falha parcial isolada
- [x] status Git correto em repo limpo, sujo, detached, renomeado, sem upstream
      e com caminho contendo espaço e acento
- [x] diretório sem Git devolve `is_repo: false`, não erro
- [x] subdiretório de repositório não herda o estado do pai (ADR-008)
- [x] nenhum teste unitário executa `git` real; integração usa repo temporário
- [x] 151 testes passando, cobertura 92%
- [x] `ruff check` sem apontamento

---

## Próximo

O MVP está completo. As opções, em ordem de valor percebido:

**A — Usar por uma semana antes de programar mais.** É o caminho que eu
recomendo. O produto existe para reduzir troca de contexto; só o uso real diz
quais das 44 histórias restantes importam. Provavelmente vai revelar três
ajustes pequenos que valem mais que qualquer fase nova.

**B — ~~Fechar as pontas soltas~~** — feito em 2026-08-21. Sobra apenas polir a
UI com base no uso real, que depende de usar.

**B2 — ~~Melhorar o frontend~~** — entregue em 2026-08-22.

1. ~~Card do projeto mais útil~~ — mostra serviços online sobre o total, Docker
   e branch com contagem de arquivos sujos, tudo cruzado do cache do dashboard
   (D-47).
2. ~~Dashboard com mais densidade~~ — mapa de portas com conflito marcado na
   linha, e painéis nomeados com contagem no cabeçalho.
3. ~~Busca e filtros de verdade~~ — busca única na topbar filtrando ao vivo, e
   recortes por fixado, serviço online, Docker, alteração e diretório ausente,
   cada um com sua contagem (D-48).
4. ~~Polimento visual~~ — tokens de peso, altura de linha e elevação; superfícies
   do browser tematizadas; algarismos tabulares; conjunto de ícones SVG no lugar
   dos glifos Unicode; responsivo abaixo de 900 px.

O que sobra aqui é o polimento que **só se decide olhando**: falta a sua
rodada no browser dizendo o que ainda incomoda.

**C — Fase 5: GitHub** (pós-MVP)
- PRs abertos, issues e Actions por projeto
- containerizar o próprio DevCockpit

**D — Fase 6: Dev Assistant** (pós-MVP)
- diagnóstico assistido sobre dados **já coletados**, sem acesso livre ao
  sistema

---

## Bloqueios

Nenhum bloqueio técnico.

**Aguardando do usuário:**

| # | Pendência | Referência |
|---|-----------|------------|
| Q-01 | `configs/roots.yml` foi criado com `Desktop` e `Documents`. Confirmar ou ajustar. | `12-decisions.md` |
| Q-06 | Suporte a projeto em path UNC de WSL (`\wsl$\...`). Nenhum projeto em WSL apareceu na varredura real, então segue em aberto sem urgência. | ADR-007 |
| — | Confirmar se este diretório deve ganhar `.git` próprio | — |

---

## Checklist manual por fase

### Fase 1 — executado em 2026-08-21

```
[x] aplicação sobe com um comando (scripts/dev.ps1)
[x] cadastro de projeto funciona (3 projetos reais)
[x] path fora do root é recusado com PATH_NOT_ALLOWED
[x] path duplicado é recusado com PROJECT_ALREADY_EXISTS
[x] lista mostra os projetos cadastrados
[x] remover projeto não apaga nada do disco (verificado no disco)
[x] Host forjado é recusado, inclusive em GET
[x] Origin externa e ausência de Origin são recusadas
[ ] recarregar a página mantém a tela atual (checar no browser)
```

### Fase 2 — executado em 2026-08-21

```
[x] varredura do Desktop encontra os projetos existentes (31)
[x] importação em lote cadastra os selecionados
[x] stack detectada corresponde à realidade de cada projeto
[x] status Git correto em repo limpo, sujo e detached
[x] pasta sem Git não gera erro
[x] subdiretório de repositório não exibe o estado do pai
[ ] conferir a aba Git no browser
```

### Fase 3a — executado em 2026-08-21

```
[x] job com saída longa aparece incrementalmente no console
[x] cancelamento encerra o processo em menos de 2 s
[x] processo que ignora término é morto junto com os filhos
[x] 20 execuções seguidas não deixam processo órfão
[x] segundo job na mesma chave é recusado com 409
[x] jobs de chaves diferentes rodam em paralelo
[x] SSE emite log e end; polling com `after` cobre a queda
[ ] conferir o console de job no browser (tela Descobrir projetos)
```

### Fase 3b — executado em 2026-08-21

```
[x] subir projeto real com Compose (via API, projeto descartável)
[x] console de job mostra a saída durante a execução
[x] segundo comando simultâneo é recusado com 409
[x] parar/derrubar projeto funciona e remove rede
[x] logs de container são devolvidos
[x] projeto sem Compose não quebra
[ ] conferir a aba Docker no browser
[ ] conferir com o Docker Desktop desligado
```

### Fase 4 — parcialmente executado em 2026-08-21

Verificado via API:

```
[x] dashboard carrega em 168 ms
[x] poller encontra serviços reais sozinho
[x] verificação sob demanda distingue ONLINE, OFFLINE e ERROR
[x] mapa de portas monta o índice
[x] `code` fora do PATH deixaria o botão desabilitado (GET /api/health)
```

Verificado no browser pelo usuário em 2026-08-21:

```
[x] botão VS Code abre o projeto correto
[x] botão Pasta abre o Explorer no diretório certo
[x] botão Terminal abre já posicionado no diretório
[x] botão Abrir serviço abre a URL certa
[ ] aba Services mostra o estado e o botão "Verificar agora" funciona
```

### Rodada no browser — executada em 2026-08-21 (headless, Chromium)

```
[x] aba Manifest mostra prévia, avisos e diff
[x] botão "Exportar" pede confirmação antes de escrever
[x] botão "Importar do arquivo" fica desabilitado sem manifesto válido
[x] importar aplica e o cabeçalho do projeto atualiza na hora
[x] botão Tema no topo alterna Sistema → Escuro → Claro e sobrevive ao reload
[x] Settings e topbar ficam em sincronia ao trocar o tema
[x] tela no tema claro continua legível em Dashboard, Projects, Settings e abas
[x] abas Git, Docker e Services carregam sem erro de console
[x] "Verificar agora" traz ONLINE com latência real
[x] VS Code, Pasta e Terminal habilitados nos 6 projetos, e agora no card
```

Falta, porque depende de você:

```
[x] Ctrl+Shift+R e conferir o layout novo (confirmado por você em 2026-08-22)
[ ] clicar em VS Code e confirmar que a janela agora vem para frente (D-46)
[ ] dizer o que ainda incomoda visualmente
[ ] conferir a aba Docker com o Docker Desktop desligado
[ ] clicar na chave Ligado/Desligado de um projeto com Compose e confirmar que
    sobe e para de verdade (não testado aqui: subiria seus containers reais)
[ ] trocar uma porta em Ports e conferir que o "Abrir" do serviço leva ao
    endereço novo
```

---

## Métricas do projeto

| Métrica | Atual | Meta |
|---------|-------|------|
| Fase | **MVP completo + pontas fechadas** | 4 de 4 |
| Pontos entregues | 131 | 131 |
| Documentos | 14 + 8 ADRs | — |
| Cobertura de testes | 89% | >= 70% |
| Testes | 589 passando (10 de frontend), 1 pulado | — |

---

## Histórico de fases

| Fase | Início | Fim | Resultado |
|------|--------|-----|-----------|
| 0 — Specs e Docs | 2026-08-21 | 2026-08-21 | 21 documentos, 44 histórias, 7 ADRs |
| 1 — Fundação | 2026-08-21 | 2026-08-21 | 36 pontos, 74 testes, cobertura 94% |
| 2 — Detecção e Git | 2026-08-21 | 2026-08-21 | 32 pontos, 151 testes, ADR-008 |
| 3a — Jobs | 2026-08-21 | 2026-08-21 | 13 pontos, 190 testes, zero órfão em 20 execuções |
| 3b — Docker | 2026-08-21 | 2026-08-21 | 16 pontos, 242 testes, up/down real verificado |
| 4 — Serviços e SO | 2026-08-21 | 2026-08-21 | 34 pontos, 285 testes, dashboard em 168 ms |
| Pontas soltas | 2026-08-21 | 2026-08-21 | manifesto, tema claro, `lifespan`; 301 testes |
| Rodada no browser | 2026-08-21 | 2026-08-21 | 4 defeitos corrigidos, ferramentas no card; 302 testes |
| Frontend (B2) | 2026-08-22 | 2026-08-22 | card com sinais, dashboard denso, busca única; 313 testes |
| Layout e portas | 2026-08-22 | 2026-08-22 | lateral recolhível, trilho de ativos, liga/desliga, tela Ports; 316 testes |
| Análise e retenção | 2026-08-23 | 2026-08-23 | gráficos no dashboard, histórico de health gravado e podado; 475 testes |
| Executável | 2026-08-23 | 2026-08-23 | pasta autocontida de 39,7 MB, abre em 1,4 s; 483 testes |
| Aplicativo e portas | 2026-08-23 | 2026-08-23 | janela nativa, ícone, prova de dono de porta, teste de frontend; 496 testes |
| Cockpit AI — Fase 1 | 2026-08-25 | 2026-08-25 | sessão, memória, Meu dia, autoria na auditoria; 516 testes |
| Tarefas de projeto | 2026-08-25 | 2026-08-25 | `ai_task`, lista por projeto, próxima tarefa no Meu dia; 526 testes |
| Cockpit AI — Fase 2 | 2026-08-25 | 2026-08-25 | chat com contexto, 3 provedores, redação de segredos, teto de gasto; 572 testes |
| Operação de subida | 2026-08-26 | 2026-08-26 | pré-voo de porta, projeto leve detectado, porta sem cadastro oferecida; 589 testes |
