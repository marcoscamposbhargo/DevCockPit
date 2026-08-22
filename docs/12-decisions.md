# 12 — Registro de Decisões

Índice das decisões da Fase 0. Decisões com peso arquitetural têm ADR próprio
em `docs/adr/`.

## Índice de ADRs

| ADR | Título | Status |
|-----|--------|--------|
| [ADR-001](adr/ADR-001-use-fastapi.md) | FastAPI como framework backend | Aceito |
| [ADR-002](adr/ADR-002-use-sqlite-for-mvp.md) | SQLite no MVP com caminho para PostgreSQL | Aceito |
| [ADR-003](adr/ADR-003-command-execution-strategy.md) | CommandRunner com allowlist e sem shell | Aceito |
| [ADR-004](adr/ADR-004-project-config-format.md) | SQLite como fonte de verdade + `devcockpit.yml` opcional | Aceito |
| [ADR-005](adr/ADR-005-frontend-strategy.md) | Frontend sem framework e sem build | Aceito |
| [ADR-006](adr/ADR-006-async-job-execution.md) | Execução assíncrona por jobs para operações longas | Aceito |
| [ADR-007](adr/ADR-007-os-abstraction-windows-first.md) | OSAdapter com Windows como plataforma primária | Aceito |
| [ADR-008](adr/ADR-008-git-repo-root-detection.md) | Um projeto só é repositório Git se for a raiz dele | Aceito |

## Decisões menores (sem ADR)

| # | Decisão | Razão |
|---|---------|-------|
| D-01 | Porta padrão `8765` | fora da faixa comum de dev (3000, 5173, 8000, 8080) para não competir com os projetos gerenciados |
| D-02 | `git` CLI em vez de GitPython | uma dependência menos, mesmo caminho de auditoria do resto, formato `--porcelain=v2` estável |
| D-03 | `docker compose` CLI em vez do SDK Python | o SDK não cobre Compose v2; o CLI é o contrato real |
| D-04 | Lista de arquivos e commits não persistidos | o Git já é o banco disso; persistir criaria obrigação de invalidar sem ganho |
| D-05 | `id` de projeto é slug, não UUID | URL legível; `path` já garante unicidade real |
| D-06 | `path` não é editável | mudar diretório é remover e recadastrar; preserva unicidade e auditoria |
| D-07 | Estado de job é volátil | resultado final vai para `activity_log`, que é persistente; estado em execução não sobrevive a restart e isso é aceitável |
| D-08 | Health check TCP quando não há `health_url` | mais rápido e não polui log de acesso da aplicação alvo |
| D-09 | `UNKNOWN` separado de `ERROR` | "não sei" e "está quebrado" levam a ações diferentes |
| D-10 | `configs/roots.yml` não editável por API | allowlist que o cliente amplia não é allowlist |
| D-11 | DevCockpit não containerizado no MVP | precisa falar com o Docker e o filesystem do host; container só complica |
| D-12 | Não ler `.env` dos projetos gerenciados | superfície de vazamento de segredo desproporcional ao ganho |
| D-13 | `open/browser` recebe `service_key`, não URL | aceitar URL do cliente reabriria o vetor que o modelo de segurança fecha |
| D-14 | Cache com TTL de 5 s para leituras | absorve rajada da UI sem exibir dado velho demais |
| D-15 | Migrações desde a versão 0.1.0 | schema de dev que muda sem migração vira perda de dado |
| D-16 | `docker compose down` sem `-v` | preserva volume nomeado; `-v` não é exposto por nenhum caminho |
| D-17 | Projetos fixados na sidebar | com dezenas de projetos, os poucos ativos do dia precisam de um clique |
| D-18 | `DataFreshness` visível na UI | nunca apresentar dado de cache como tempo real |
| D-19 | Fixtures capturadas de saída real | fixture inventada é a origem clássica do teste que passa e do código que falha |
| D-20 | `start_command` fora do schema do manifesto | comando declarado em repositório clonado se tornaria execução de código de terceiro |
| D-21 | Validação de `Host` em todas as requisições, e `Origin` obrigatório nas de escrita | fecha DNS rebinding (T9), que derrota a checagem de `Origin` "quando presente" |
| D-22 | Fase 3 dividida em 3a (jobs) e 3b (Docker) | juntava subprocess assíncrono, kill de árvore no Windows, SSE e parse de Compose; falhando, não se saberia de qual dos quatro veio |
| D-23 | Varredura síncrona e limitada na Fase 2, virando job na 3a | o `JobManager` só existe na 3a; profundidade máxima, lista de ignorados e teto de candidatos já satisfazem NFR-011, que proíbe varredura *ilimitada*. Medido: 31 candidatos em 0,19 s no Desktop real |
| D-24 | `is_repo` exige que o diretório seja a **raiz** do repositório | `git` sobe a árvore; com um repositório em `C:/Users/User`, todo projeto abaixo reportaria a branch e os arquivos sujos do pai. Ver `docs/adr/ADR-008` |
| D-25 | Detector de HTML estático só roda como fallback | um `index.html` de template rotularia um projeto Next.js como "site estático" |
| D-26 | A varredura não desce dentro de projeto encontrado | um monorepo vira um candidato, não trinta |
| D-27 | Faixa de portas no Compose (`9000-9010:9000-9010`) é ignorada | sugerir a primeira porta de uma faixa é adivinhação; melhor não sugerir nada |
| D-28 | Saída de job não distingue stdout de stderr | `docker compose` e `git` escrevem **progresso** em stderr; marcar tudo como erro treinaria o usuário a ignorar a marcação. Sucesso e falha vêm do código de saída |
| D-29 | Portas lidas de `Publishers`, não da string `Ports` | `Publishers` é estruturado; a string exige parse e muda de formato. Entradas IPv4 e IPv6 da mesma porta são deduplicadas |
| D-30 | `uptime_s` não é calculado; expõe-se o `Status` textual do Docker | "Up 3 hours (unhealthy)" é texto humano que varia por locale; converter em segundos seria inventar precisão |
| D-31 | Teste que enfileira job precisa dublar **os dois** runners | dublar só o síncrono deixou um teste subir containers de verdade na máquina; há agora uma fixture que bloqueia execução real fora de teste de integração |
| D-32 | Poller verifica apenas projetos fixados e acessados nos últimos N dias | resposta a Q-02. Verificar 36 projetos a cada 30 s é caro e inútil: a maioria está parada há semanas. Qualquer projeto pode ser verificado sob demanda |
| D-33 | `DateTime` do banco é um `TypeDecorator` que sempre devolve UTC ciente | o SQLite não guarda timezone e devolvia datetime ingênuo; comparar com `utcnow()` quebrava o poller **em silêncio**, dentro do `except` que o protege |
| D-34 | `STALE` entra após três ciclos do poller | um único ciclo perdido é normal; três indicam que algo parou |
| D-35 | Abrir URL usa `webbrowser`, não `start` | `start` é comando interno do shell do Windows e exigiria shell — proibido por ADR-003 |
| D-36 | `explorer.exe` tem código de saída ignorado | devolve 1 mesmo quando abre a pasta corretamente |
| D-37 | Importar manifesto faz **upsert** por chave de serviço; não apaga o que o arquivo não menciona | apagar seria resolução automática de conflito, que FR-112 proíbe. O usuário que quiser remover um serviço remove na UI |
| D-38 | Tecnologia vinda do `stack` do manifesto entra como `MANUAL` | é declaração, não detecção. Como `MANUAL`, sobrevive à re-detecção — a precedência da spec 08 põe declaração acima de detecção |
| D-39 | Ler o manifesto degrada; importar não | leitura acontece em toda carga de tela e precisa de `200` com aviso. Importar é ação explícita: recusar com `422` é mais honesto que aplicar metade |
| D-40 | O manifesto é importado por padrão no cadastro de um projeto que já tem o arquivo | não há o que sobrescrever num projeto recém-criado, então a confirmação de FR-112 não se aplica. Manifesto quebrado não impede o cadastro |
| D-41 | Preferência de tema mora no `localStorage`, não no banco | é ajuste de quem olha a tela, não configuração do projeto; guardar no servidor exigiria rota de escrita para mudar cor de fundo |
| D-42 | "Rodando" no dashboard vem do health observado, não da coluna `status` | `status` descreve o registro, não o processo, e nunca chega a `RUNNING` sozinho. O painel mostrava "0 rodando" na mesma tela em que listava quatro serviços online |
| D-43 | Check TCP usa `happy_eyeballs_delay` | no Windows `localhost` resolve `::1` antes de `127.0.0.1`; serviço que só ouve em IPv4 pendurava a tentativa IPv6 até estourar o timeout e aparecia OFFLINE estando no ar |
| D-44 | Ferramentas (VS Code, Pasta, Terminal) também no card da lista | abrir o editor é o motivo mais comum de procurar um projeto; exigir dois cliques a mais até a aba Overview era atrito puro |

## Divergências em relação ao prompt original

Registradas para rastreabilidade — cada uma tem justificativa acima ou em ADR.

| Item do prompt | Divergência | Onde |
|----------------|-------------|------|
| Item 5 — lista de services | `SystemService` e `ProcessService` fundidos em `SystemActionService`; inspeção de porta foi para `ServiceHealthService` | `04` |
| Item 6 — estrutura | `integrations/` renomeado para `adapters/`; adicionados `runner/`, `jobs/`, `detection/`, `migrations/`, `core/paths.py`, `core/errors.py` | `04` |
| Item 6 — `docker-compose.yml` na raiz | postergado para a Fase 5 | D-11 |
| Item 7 — formato de config | resolvido como híbrido, não escolha única | `08`, ADR-004 |
| Item 22 — endpoints Docker síncronos | viraram assíncronos com `job_id` | ADR-006 |
| Módulo 2 — só cadastro manual | adicionada descoberta por varredura (FR-009) | `02` |
| Módulo 6 — health check | adicionado poller em background com cache; a especificação original travaria o dashboard | `04`, NFR-010 |
| Item 12 — segurança | adicionados bind local obrigatório, guard CSRF e validação de path; o prompt cobria apenas a ausência de `/execute-command` | `07` |
| Item 14 — logs | adicionado `DENIED` como status e redação de segredo no argv | `05`, `07` |
| Módulo 5 — logs de container | exigem SSE; HTTP JSON simples não atende streaming | FR-055 |

## Questões abertas

Precisam de decisão antes das fases indicadas.

| # | Questão | Decidir antes de |
|---|---------|------------------|
| Q-01 | Quais diretórios entram em `configs/roots.yml` na máquina do usuário? | Fase 1 |
| ~~Q-02~~ | **Resolvida na Fase 4:** fixados + acessados nos últimos N dias (`DEVCOCKPIT_HEALTH_HISTORY_DAYS`, padrão 7). Ver D-32. | — |
| Q-03 | Purga de `health_snapshot`: manter histórico ou só o último estado? Proposta: último estado obrigatório, histórico de 7 dias. | Fase 4 |
| Q-04 | Tema claro entra no MVP ou depois? **Decidido: depois** — os tokens já estão preparados para isso. | pós-MVP |
| Q-05 | `start_command` com confirmação explícita entra no roadmap? | pós-MVP |
| Q-06 | Suporte a WSL: projeto em `\\wsl$\...` é caso a tratar? | Fase 2 |
