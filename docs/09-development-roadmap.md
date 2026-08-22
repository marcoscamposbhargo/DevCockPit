# 09 — Roadmap de Desenvolvimento

Cada fase tem critério de saída verificável. Fase não fecha por "achei que
estava pronto": fecha quando o critério é demonstrável.

Regra fixa em todas as fases: **código + testes + documentação entram juntos**.

---

## Fase 0 — Discovery, Specs e Docs

**Status: em andamento (esta entrega)**

Escopo:
- análise crítica do prompt, com inconsistências levantadas
- 14 documentos em `docs/`
- ADRs 001 a 007
- backlog e roadmap
- estrutura de diretórios
- `README.md`, `.gitignore`, `.env.example`, `PROJECT_STATUS.md`

Critério de saída: documentação completa e revisada pelo usuário. Nenhuma linha
de código de produção.

---

## Fase 1 — Fundação e Registro de Projetos

Objetivo: cadastrar projeto e ver a lista. O menor sistema que já é útil.

| Entrega | Detalhe |
|---------|---------|
| Bootstrap FastAPI | `main.py`, settings, log estruturado, validação de bind local |
| `core/paths.py` | canonicalização + allowlist, com testes de traversal e symlink |
| `core/errors.py` | hierarquia de erro de domínio + handler HTTP |
| Migração 001 | `project`, `project_technology`, `project_service` |
| `CommandRunner` | argv, timeout, captura, duração — com fake para teste |
| `ProjectService` + repositório | CRUD, validação de path, unicidade |
| Rotas de projeto | `GET`/`POST`/`GET {id}`/`PATCH`/`DELETE` |
| Guard CSRF | cabeçalho de cliente + CORS restrito |
| Frontend base | shell da app, sidebar, roteador por hash, tokens de CSS |
| Páginas | lista de projetos, formulário de cadastro |
| `ActivityService` | auditoria gravando desde a primeira ação |

Critério de saída:
- cadastrar 3 projetos reais pela interface e vê-los listados
- os 12 testes de segurança do `07` implementados e passando
- servidor recusa subir com host não-loopback
- cobertura >= 70% em `services/` e `runner/`

Riscos: nenhum grave. É a fase de disciplina.

---

## Fase 2 — Detecção e Git

Objetivo: o projeto passa a se descrever sozinho.

| Entrega | Detalhe |
|---------|---------|
| `DetectionRegistry` | registry + 12 detectores (FR-021) |
| Extração de porta | do arquivo Compose e do `vite.config.*` |
| `POST /detect` | re-detecção respeitando `detection_locked` |
| Descoberta | varredura de root como job, com candidatos e importação em lote |
| `GitAdapter` | `--porcelain=v2`, `--format` com separador estável |
| `GitService` + cache TTL | status, commits, branches, remotes |
| Rotas Git | as 4 rotas de leitura |
| Migração 002 | `git_repository` |
| UI | página do projeto com aba Git; badge de pendência na lista |

Critério de saída:
- varrer `C:/Users/User/Desktop` e importar os projetos encontrados
- status Git correto em repo limpo, sujo, detached e sem upstream
- diretório sem Git não gera erro, gera `is_repo: false`
- nenhum teste unitário executa `git` real; integração usa repo temporário

Riscos:
- parse de saída do Git é a maior fonte de bug sutil. Mitigação: formato
  estável obrigatório, nunca saída humana, com fixtures de saída real.
- varredura lenta em disco cheio. Mitigação: job assíncrono, profundidade
  limitada, lista de ignore.

---

## Fase 3 — Operação (dividida em 3a e 3b)

Esta é a fase de maior risco técnico do projeto, e por isso está **dividida**.
A versão original juntava quatro problemas difíceis ao mesmo tempo: subprocess
assíncrono, encerramento de árvore de processos no Windows, SSE atravessando
antivírus local, e parse de saída do `docker compose` variável entre versões.

Depurar job assíncrono **e** Compose simultaneamente é o pior cenário: quando
algo falha, não se sabe de qual dos dois veio. A divisão existe para que, ao
chegar no Docker, a máquina de jobs já seja terreno conhecido.

---

### Fase 3a — Máquina de jobs (sem Docker)

Objetivo: execução assíncrona sólida, validada com comandos triviais.

| Entrega | Detalhe |
|---------|---------|
| `JobManager` | estados, saída incremental, timeout, exclusão mútua por chave, cancelamento |
| Encerramento de árvore | job object no Windows; grupo de processo em POSIX |
| Limite de saída | truncamento pelo início ao passar de 2 MB, com marcação |
| Retenção | job concluído mantido em memória por 1 h; resultado final na auditoria |
| Rotas de job | consulta, listagem por projeto, cancelamento |
| SSE + fallback | stream de progresso, com queda automática para polling |
| UI `JobConsole` | painel com saída ao vivo, autoscroll pausável, tempo decorrido |

Comandos de validação: `ping`, `timeout`/`sleep` e um script próprio em
`scripts/` que emite linhas com atraso, sai com código configurável e ignora
sinal de término — este último é o que prova o encerramento de árvore.

Critério de saída:
- job que emite 500 linhas em 30 s aparece incrementalmente no console
- cancelamento encerra o processo em menos de 2 s
- comando que ignora término é morto mesmo assim, junto com os filhos
- nenhum processo órfão sobra após 20 execuções seguidas (verificado no
  Gerenciador de Tarefas)
- segundo job na mesma chave devolve 409
- jobs de chaves diferentes rodam em paralelo
- SSE bloqueado cai para polling sem o usuário perceber

Só depois destes itens a Fase 3b começa.

---

### Fase 3b — Docker

Objetivo: operar o projeto de verdade. A máquina de jobs já é confiável.

| Entrega | Detalhe |
|---------|---------|
| `DockerAdapter` | `compose ps --format json`, ações do Compose |
| Tolerância de formato | JSON por linha e array, conforme a versão do Compose |
| Detecção de versão | `docker compose version` exposto em `GET /api/health` |
| `DockerService` | status síncrono cacheado; ações sempre via job |
| Migração 003 | `docker_config` |
| Logs | `tail` em JSON e stream por SSE |
| Degradação | daemon fora do ar vira `available: false`, sem erro |
| UI | aba Docker: containers, ações inline, viewer de logs |

Critério de saída:
- subir e parar um projeto real com Compose pela interface
- segundo `up` concorrente devolve 409 sem executar
- desligar o Docker Desktop e o dashboard continuar respondendo
- `up` que estoura o timeout vira `TIMEOUT` e mata a árvore de processos
- nome de serviço inexistente devolve 422 sem executar comando
- `-v` inalcançável por qualquer caminho da API

Riscos remanescentes:
- saída do `docker compose` varia entre versões. Mitigação: formato JSON
  fixado, fixtures capturadas por versão, parse tolerante a array e a
  JSON-por-linha.
- inicialização lenta do Compose no Windows (2 a 5 s só para começar).
  Mitigação: o usuário vê o console de job desde o primeiro instante, então a
  espera é visível e não parece travamento.

---

## Fase 4 — Serviços, Health e Ações de SO

Objetivo: fechar o loop de DX. Ao fim desta fase o MVP está pronto.

| Entrega | Detalhe |
|---------|---------|
| `ServiceHealthService` | check HTTP e TCP, concorrente, com timeout de 2 s |
| `HealthPoller` | tarefa de background com intervalo configurável |
| Cache + `STALE` | idade do dado exposta na API |
| Migração 004 | `health_snapshot` + purga |
| Conflito de porta | `GET /api/services/ports` |
| `OSAdapter` | Windows: `code`, `explorer`, `wt.exe` com fallback para `powershell`, browser padrão |
| `OSAdapter` POSIX | `xdg-open` / `open`, terminal por detecção |
| Rotas de sistema | vscode, folder, terminal, browser (por `service_key`) |
| Detecção de ferramenta | `GET /api/health` informa git/docker/code disponíveis |
| `DashboardService` | agregação completa de cache |
| UI | dashboard final, aba Services, aba Activity, Settings |

Critério de saída:
- os 12 casos de uso do PRD executáveis ponta a ponta
- dashboard com 30 projetos abaixo de 500 ms
- `code` fora do PATH devolve `503 TOOL_NOT_FOUND` e a UI já mostra o botão
  desabilitado
- terminal abre no diretório correto no Windows
- conflito de porta entre dois projetos é apontado

**Marco: MVP completo.**

---

## Fase 5 — GitHub e Deploy (pós-MVP)

- `GithubService` com token só via variável de ambiente
- repositório, PRs abertos, issues, últimas execuções de Actions
- cache agressivo e respeito a rate limit
- link direto para o PR da branch atual
- containerização do próprio DevCockpit (`docker-compose.yml` da raiz)

Critério de saída: ver PRs abertos de um projeto sem sair da interface.

---

## Fase 6 — Dev Assistant (pós-MVP)

- `AIService` recebendo **apenas** dados já coletados: status Git, estado de
  container, logs, portas, resultado de health
- sem acesso a filesystem, sem execução de comando, sem geração de comando
- perguntas alvo: por que o container caiu, por que o backend não subiu, qual
  projeto tem pendência, qual porta está ocupada
- resposta é diagnóstico textual, nunca ação automática

Critério de saída: diagnosticar corretamente uma falha real de `compose up` a
partir dos logs coletados.

---

## Fora do escopo em todas as fases previstas

```
IDE web · terminal web · editor de código · CI/CD próprio
Kubernetes · execução remota · multiusuário · RBAC
```

Estes itens exigiriam refazer o modelo de segurança inteiro. Não são "depois":
são outro produto.
