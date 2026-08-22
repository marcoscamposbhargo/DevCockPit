# 13 — Backlog

Formato: `EPIC-NN` agrupando `US-NNN`. Cada história tem critérios de aceite
verificáveis e referência aos requisitos funcionais que atende.

Estimativa em pontos relativos: `1` trivial, `2` pequena, `3` média,
`5` grande, `8` deve ser quebrada.

---

## EPIC-00 — Fundação técnica

### US-001 — Bootstrap da aplicação `[3]` · Fase 1
Como dev, quero subir a aplicação com um comando, para começar a trabalhar.

Aceite:
- `uvicorn app.main:app --reload` sobe em `127.0.0.1:8765`
- tentativa de bind em host não-loopback recusa o startup com mensagem clara
- `GET /api/health` responde com versão e disponibilidade de git/docker/code
- log estruturado em JSON gravado em arquivo
- configuração vem de `.env` via `pydantic-settings`

Atende: NFR-001, NFR-050, NFR-070

### US-002 — Validação de path `[3]` · Fase 1
Como responsável pela segurança, quero que todo path seja validado num único
lugar, para que não exista caminho alternativo.

Aceite:
- `core/paths.py` expõe uma função de validação usada por todos os serviços
- rejeita: relativo, inexistente, arquivo, fora do root, `..` que escapa,
  symlink que escapa
- comparação por componentes de path, não por `startswith` de string
- roots vêm de `configs/roots.yml`, nunca da API
- cobertura de 100% neste módulo

Atende: FR-002, NFR-004, NFR-005

### US-003 — CommandRunner `[5]` · Fase 1
Como responsável pela segurança, quero um ponto único de execução de comandos,
para que a auditoria e o timeout sejam inescapáveis.

Aceite:
- recebe `CommandSpec` com argv, cwd validado, timeout obrigatório e label
- executa com `shell=False`
- devolve exit code, stdout, stderr, duração e flag de timeout
- timeout encerra a árvore de processos
- toda execução gera entrada em `activity_log` com argv redigido
- existe `FakeCommandRunner` para testes
- teste automatizado falha se `shell=True` aparecer no código-fonte
- teste automatizado falha se `subprocess` for importado fora de `app/runner/`

Atende: NFR-003, NFR-051, NFR-061, FR-101

### US-004 — Migrações e modelo base `[3]` · Fase 1
Como dev, quero schema versionado desde o início, para não perder dado ao
evoluir o modelo.

Aceite:
- migração 001 cria `project`, `project_technology`, `project_service`
- índices de `05-data-model.md` criados
- rodar as migrações duas vezes é idempotente
- banco em `data/devcockpit.db`, fora do versionamento

Atende: NFR-072

### US-005 — Tratamento de erro e correlação `[2]` · Fase 1
Como usuário, quero mensagem de erro compreensível, para saber o que fazer.

Aceite:
- hierarquia `DomainError` mapeada para os `code` de `06`
- resposta segue o envelope de erro único
- `correlation_id` presente na resposta e no log
- erro não tratado vira 500 sem expor stack trace ao cliente

Atende: NFR-008, NFR-052

### US-006 — Guard de origem e de `Host` `[3]` · Fase 1
Como responsável pela segurança, quero bloquear requisição de página externa e
ataque de DNS rebinding, para que nenhuma aba do browser opere a ferramenta.

Aceite:
- middleware valida `Host` contra `localhost`, `127.0.0.1` e `[::1]` em
  **todas** as requisições, inclusive `GET` e SSE; outro valor retorna 403 e
  grava `DENIED`
- `POST`/`PATCH`/`PUT`/`DELETE` sem `X-DevCockpit-Client` retornam 403
- `Origin` é **obrigatório** em requisição que altera estado; ausente ou
  diferente da própria retorna 403
- CORS sem wildcard
- `GET` não exige `X-DevCockpit-Client`, mas passa pela validação de `Host`

Atende: NFR-006, defesas D5 e D10 de `07-security-model.md`

---

## EPIC-01 — Gestão de projetos

### US-010 — Cadastrar projeto `[3]` · Fase 1
Como dev, quero cadastrar um projeto informando a pasta, para acessá-lo por
uma interface única.

Aceite:
- informo path absoluto e, opcionalmente, nome
- path validado; fora do root retorna `PATH_NOT_ALLOWED`
- path duplicado retorna `PROJECT_ALREADY_EXISTS`
- nome ausente usa o nome da pasta
- `id` é slug único
- ação registrada na auditoria

Atende: FR-001, FR-002, FR-003

### US-011 — Listar projetos com filtro `[3]` · Fase 1
Aceite: filtro por status, stack, presença de Docker, fixado e busca textual;
ordenação padrão por último acesso; paginação com `total`.

Atende: FR-004

### US-012 — Ver, editar e remover projeto `[3]` · Fase 1
Aceite: detalhe atualiza `last_accessed_at`; `PATCH` altera nome, descrição,
fixado e config Docker; `path` não é editável; `DELETE` remove só o registro e
nunca toca em arquivo; remoção registrada na auditoria.

Atende: FR-005, FR-006, FR-007, FR-008

### US-013 — Frontend base e lista de projetos `[5]` · Fase 1
Aceite: shell com sidebar e topbar; roteador por hash que sobrevive a
recarregar; tokens de CSS aplicados; lista renderizada da API; estado vazio com
duas ações; nenhum `innerHTML` com dado da API.

Atende: `11-ui-ux-spec.md`

### US-014 — Projeto com diretório ausente `[2]` · Fase 2
Aceite: diretório inexistente marca `MISSING`; card em destaque; ações
desabilitadas exceto remover; nenhuma operação em cascata falha.

Atende: NFR-062

---

## EPIC-02 — Detecção e descoberta

### US-020 — Registry de detecção `[5]` · Fase 2
Aceite: 12 detectores de FR-021; adicionar stack nova é adicionar arquivo e
registrar; sem cadeia de `if`; tecnologia com categoria e evidência
(arquivo de origem); tecnologia `MANUAL` nunca sobrescrita.

Atende: FR-020, FR-021, FR-022, FR-024

### US-021 — Extração de porta declarada `[3]` · Fase 2
Aceite: portas lidas do arquivo Compose e do `vite.config.*`; serviços
sugeridos com porta e URL; YAML inválido gera aviso, não erro.

Atende: FR-023

### US-022 — Re-detecção sob demanda `[2]` · Fase 2
Aceite: `POST /detect` devolve o diff do que mudou; respeita
`detection_locked`; síncrono.

Atende: FR-025

### US-023 — Varredura de diretório `[5]` · Fase 2
Como dev com 30 projetos espalhados, quero apontar uma pasta raiz e receber os
projetos encontrados, para não cadastrar um por um.

Aceite:
- root precisa estar na allowlist
- varredura roda como job (não bloqueia)
- profundidade máxima configurável, padrão 3
- ignora `node_modules`, `.venv`, `venv`, `dist`, `build`, `.git`, `__pycache__`
- candidato traz nome sugerido, tecnologias e se já está cadastrado
- diretório sem permissão é registrado e ignorado, sem abortar

Atende: FR-009, FR-011, NFR-012

### US-024 — Importação em lote `[2]` · Fase 2
Aceite: seleciono vários candidatos e cadastro de uma vez; falha individual não
aborta o lote; relatório por item.

Atende: FR-010

---

## EPIC-03 — Git

### US-030 — Estado do repositório `[5]` · Fase 2
Aceite: usa `--porcelain=v2 --branch`; branch atual e detached; contagens de
modificado, novo, removido, staged e untracked; lista limitada com
`files_truncated`; ahead/behind quando houver upstream; diretório sem Git
devolve `is_repo: false` e não erro; cache com TTL de 5 s.

Atende: FR-030, FR-031, FR-032, FR-033, FR-037

### US-031 — Commits, branches e remotes `[3]` · Fase 2
Aceite: último commit com hash curto, autor, data e assunto; histórico com
limite validado; branches locais; remotes com URL; `provider` inferido da URL;
formato de saída estável, nunca saída humana.

Atende: FR-034, FR-035, FR-036, FR-039

### US-032 — Painel Git na UI `[3]` · Fase 2
Aceite: aba Git com branch, ahead/behind, contagens, arquivos e último commit;
badge de pendência no card do projeto; hash e path em monoespaçada;
`DataFreshness` visível.

Atende: `11-ui-ux-spec.md`

### US-033 — Bloqueio de escrita Git `[1]` · Fase 2
Aceite: nenhuma rota de escrita existe; teste garante que a allowlist não
contém `commit`, `reset`, `clean`, `checkout` nem `push`.

Atende: FR-038

---

## EPIC-04 — Jobs

### US-040 — JobManager `[5]` · Fase 3a
Aceite: `submit` devolve `job_id`; ciclo `PENDING`→`RUNNING`→final; saída
acumulada consultável durante a execução; timeout vira `TIMEOUT` e mata a
árvore de processos; exclusão mútua por chave devolve conflito; chaves
diferentes rodam em paralelo; resultado final vai para `activity_log`.

Atende: FR-090, FR-091, FR-092, FR-093, FR-057

### US-041 — Rotas de job `[3]` · Fase 3a
Aceite: consulta, listagem por projeto, cancelamento e SSE de progresso; SSE
indisponível cai para polling.

Atende: FR-091, FR-092, FR-094

### US-042 — Console de job na UI `[3]` · Fase 3a
Aceite: painel abaixo da ação (não modal); saída mono com autoscroll pausável;
tempo decorrido; estado final destacado; `aria-live` ao concluir.

Atende: `11-ui-ux-spec.md`

### US-043 — Harness de validação de job `[2]` · Fase 3a
Como dev, quero validar a máquina de jobs com comandos triviais antes de
encostar no Docker, para não depurar dois sistemas difíceis ao mesmo tempo.

Aceite:
- `scripts/job_probe.py` emite N linhas com atraso configurável, sai com código
  configurável e tem modo que ignora sinal de término
- job com 500 linhas em 30 s aparece incrementalmente no console
- cancelamento encerra o processo em menos de 2 s
- processo que ignora término é morto mesmo assim, junto com os filhos
- 20 execuções seguidas não deixam processo órfão
- SSE bloqueado cai para polling sem quebra visível

Atende: critério de saída da Fase 3a

---

## EPIC-05 — Docker

### US-050 — Estado dos containers `[5]` · Fase 3b
Aceite: detecta arquivo Compose ou usa o configurado; `compose ps --format
json` parseado (inclusive JSON por linha); nome, serviço, estado, health,
imagem, portas e uptime; daemon fora do ar devolve 200 com
`available: false`; sem Compose devolve `NO_COMPOSE_FILE`.

Atende: FR-050, FR-051, FR-056

### US-051 — Ações Compose `[5]` · Fase 3b
Aceite: up, down, start, stop, restart, todos como job com 202; segundo pedido
concorrente devolve 409; `services` opcional validado contra o Compose do
projeto, desconhecido devolve 422 sem executar; `-v` inexistente em qualquer
caminho.

Atende: FR-052, FR-053, FR-057

### US-052 — Logs de container `[3]` · Fase 3b
Aceite: `tail` configurável em JSON; stream por SSE com eventos `log` e `end`;
logs nunca persistidos pelo DevCockpit.

Atende: FR-054, FR-055

### US-053 — Aba Docker na UI `[3]` · Fase 3b
Aceite: tabela de containers com ação por linha; botões de Compose no topo;
viewer de logs com filtro e pausa; daemon fora do ar exibe estado `UNKNOWN` na
própria tela, com botão de reverificar.

Atende: `11-ui-ux-spec.md`

---

## EPIC-06 — Serviços e health

### US-060 — Cadastro de serviços `[3]` · Fase 4
Aceite: `PUT` substitui a lista; chave única por projeto; URL restrita a
`http`/`https` em host local; `health_kind` em `HTTP`, `TCP` ou `NONE`;
serviços sugeridos pela detecção pré-preenchidos.

Atende: FR-060

### US-061 — Health check `[5]` · Fase 4
Aceite: HTTP considera 2xx e 3xx como `ONLINE`; sem `health_url` usa TCP;
timeout de 2 s vira `ERROR`; checks concorrentes; `health_kind: none` não é
verificado; resultado no `health_snapshot`.

Atende: FR-061, NFR-013

### US-062 — Poller em background `[3]` · Fase 4
Aceite: tarefa com intervalo configurável; API sempre serve de cache; dado
além do TTL marcado `STALE`; reverificação sob demanda; poller que falha não
derruba a aplicação.

Atende: FR-062, FR-063, NFR-010, NFR-011

### US-063 — Conflito de porta `[2]` · Fase 4
Aceite: `GET /api/services/ports` mapeia porta para projeto e serviço e aponta
conflitos; conflito em destaque no topo do dashboard.

Atende: FR-064

---

## EPIC-07 — Ações de sistema

### US-070 — Abrir no VS Code, pasta e terminal `[5]` · Fase 4
Aceite: `OSAdapter` com implementação por plataforma; Windows usa `code`,
`explorer` e `wt.exe` com fallback para `powershell`; terminal abre já no
diretório do projeto; ferramenta ausente devolve `503 TOOL_NOT_FOUND` com
instrução; nenhum path montado por concatenação de string.

Atende: FR-070, FR-071, FR-072, FR-074, NFR-040, NFR-041

### US-071 — Abrir URL de serviço `[2]` · Fase 4
Aceite: recebe `service_key`, nunca URL; URL resolvida no backend; chave
inexistente devolve 422.

Atende: FR-073

### US-072 — UI ciente de ferramenta ausente `[2]` · Fase 4
Aceite: UI consulta `GET /api/health` e desabilita preventivamente as ações
indisponíveis, com tooltip explicando o motivo.

Atende: `11-ui-ux-spec.md`

---

## EPIC-08 — Dashboard e auditoria

### US-080 — Dashboard agregado `[5]` · Fase 4
Aceite: todos os totais de FR-080; pendências Git, serviços ativos, projetos
recentes e conflitos de porta; servido de cache com `from_cache` e
`generated_at`; abaixo de 500 ms com 30 projetos; Docker fora do ar não impede
resposta.

Atende: FR-080 a FR-084, NFR-010, NFR-060

### US-081 — Log de atividade `[3]` · Fase 1 (base) / Fase 4 (UI)
Aceite: toda ação registrada com timestamp, projeto, ação, status, duração,
exit code e argv redigido; `DENIED` gravado quando a allowlist recusa; filtro
por projeto, ação e status; nenhum segredo gravado.

Atende: FR-100 a FR-103

---

## EPIC-09 — Manifesto do projeto

### US-090 — Importar `devcockpit.yml` `[3]` · Fase 4
Aceite: schema de `08` validado; `version` desconhecida ignora com aviso; YAML
inválido não quebra o projeto; `compose_file` relativo resolvido dentro do
path; importação sugerida no cadastro quando o arquivo existe.

Atende: FR-110

### US-091 — Exportar e comparar `[3]` · Fase 4
Aceite: exportação escreve o arquivo com confirmação explícita — única escrita
em pasta de projeto; comparação mostra diferença campo por campo sem alterar
nada; divergência exibe aviso com dois botões, sem resolução automática.

Atende: FR-111, FR-112

---

## Pós-MVP (não estimado)

| ID | História | Fase |
|----|----------|------|
| US-100 | Ver PRs abertos e issues do repositório | 5 |
| US-101 | Última execução do GitHub Actions por projeto | 5 |
| US-102 | Containerizar o próprio DevCockpit | 5 |
| US-103 | Identificar processo que ocupa uma porta (FR-065) | 5 |
| US-104 | Tema claro | 5 |
| US-105 | Dev Assistant diagnosticando falha de `compose up` | 6 |
| US-106 | `start_command` com confirmação explícita por projeto | a decidir |

---

## Resumo por fase

| Fase | Histórias | Pontos |
|------|-----------|--------|
| 1 | US-001 a US-006, US-010 a US-013, US-081 (base) | 36 |
| 2 | US-014, US-020 a US-024, US-030 a US-033 | 32 |
| 3a | US-040 a US-043 | 13 |
| 3b | US-050 a US-053 | 16 |
| 4 | US-060 a US-063, US-070 a US-072, US-080, US-081 (UI), US-090, US-091 | 34 |

Total do MVP: 131 pontos.
