# 02 — Requisitos Funcionais

Convenção: `FR-NNN`. Prioridade `MUST` (MVP), `SHOULD` (MVP se couber),
`LATER` (pós-MVP).

## Projetos

| ID | Requisito | Prio |
|----|-----------|------|
| FR-001 | Cadastrar um projeto informando um diretório local absoluto. | MUST |
| FR-002 | Validar que o diretório existe, é diretório e está dentro de um root permitido. | MUST |
| FR-003 | Rejeitar cadastro de diretório já cadastrado (path canonicalizado é único). | MUST |
| FR-004 | Listar projetos com filtro por status, stack e presença de Docker. | MUST |
| FR-005 | Editar nome, descrição, stack, serviços e configuração Docker de um projeto. | MUST |
| FR-006 | Remover um projeto do registro sem tocar nos arquivos em disco. | MUST |
| FR-007 | Registrar e expor o timestamp do último acesso de cada projeto. | MUST |
| FR-008 | Marcar projeto como favorito/fixado. | SHOULD |
| FR-009 | Varrer um diretório raiz e sugerir projetos ainda não cadastrados, como job assíncrono. | MUST |
| FR-010 | Cadastrar em lote os projetos sugeridos pela varredura. | SHOULD |
| FR-011 | Ignorar, na varredura, diretórios de dependência (`node_modules`, `.venv`, `dist`, `build`). | MUST |

## Detecção de stack

| ID | Requisito | Prio |
|----|-----------|------|
| FR-020 | Detectar tecnologias por marcadores de arquivo no diretório do projeto. | MUST |
| FR-021 | Suportar no MVP: `requirements.txt`, `pyproject.toml`, `package.json`, `Dockerfile`, `docker-compose.yml`, `compose.yml`, `vite.config.*`, `next.config.*`, `pom.xml`, `build.gradle`, `go.mod`, `Cargo.toml`. | MUST |
| FR-022 | Permitir registrar novos detectores sem alterar código existente (registry). | MUST |
| FR-023 | Extrair portas declaradas do arquivo Compose e de `vite.config.*` quando possível. | SHOULD |
| FR-024 | Permitir que a detecção seja sobrescrita manualmente e não ser desfeita em novo scan. | MUST |
| FR-025 | Reexecutar a detecção sob demanda em um projeto já cadastrado. | MUST |

## Git

| ID | Requisito | Prio |
|----|-----------|------|
| FR-030 | Detectar se o diretório é **a raiz** de um repositório Git. Estar dentro de um repositório cuja raiz é outra não conta como repositório próprio (ADR-008). | MUST |
| FR-031 | Informar a branch atual, ou estado detached. | MUST |
| FR-032 | Informar contagem de arquivos modificados, novos, removidos e staged. | MUST |
| FR-033 | Listar os arquivos alterados, limitado a N, com o total. | MUST |
| FR-034 | Informar o último commit: hash curto, autor, data e assunto. | MUST |
| FR-035 | Listar os últimos N commits. | MUST |
| FR-036 | Listar remotes e a URL do remote `origin`. | MUST |
| FR-037 | Informar divergência com o upstream (ahead/behind), quando houver upstream. | SHOULD |
| FR-038 | Nunca executar operação que altere o repositório no MVP. `commit`, `reset`, `clean`, `checkout` e `push` são proibidos. | MUST |
| FR-039 | Listar branches locais. | SHOULD |

## Docker

| ID | Requisito | Prio |
|----|-----------|------|
| FR-050 | Detectar o arquivo Compose do projeto, ou usar o caminho configurado. | MUST |
| FR-051 | Listar containers do projeto com nome, serviço, status, imagem, portas e uptime. | MUST |
| FR-052 | Executar `compose up -d` como job assíncrono. | MUST |
| FR-053 | Executar `compose down`, `start`, `stop` e `restart` como job assíncrono. | MUST |
| FR-054 | Expor logs de um serviço do Compose, últimas N linhas. | MUST |
| FR-055 | Transmitir logs em tempo real via SSE. | SHOULD |
| FR-056 | Reportar estado `UNKNOWN` com mensagem clara quando o daemon Docker não responder, sem quebrar o restante da resposta. | MUST |
| FR-057 | Impedir duas operações Compose concorrentes no mesmo projeto. | MUST |

## Serviços locais e health check

| ID | Requisito | Prio |
|----|-----------|------|
| FR-060 | Cadastrar serviços de um projeto com nome, porta, URL e URL de health. | MUST |
| FR-061 | Classificar o estado de cada serviço em `ONLINE`, `OFFLINE`, `STARTING`, `ERROR`, `STALE` ou `UNKNOWN`. | MUST |
| FR-062 | Executar as verificações em background com intervalo configurável, servindo o resultado de cache. Só para projetos fixados e acessados nos últimos N dias (D-32). | MUST |
| FR-063 | Permitir forçar reverificação de um projeto sob demanda. | MUST |
| FR-064 | Detectar conflito de porta entre projetos cadastrados. | SHOULD |
| FR-065 | Identificar qual processo ocupa uma porta. Sem ação de encerrar processo no MVP. | LATER |

## Ações de sistema operacional

| ID | Requisito | Prio |
|----|-----------|------|
| FR-070 | Abrir o projeto no VS Code. | MUST |
| FR-071 | Abrir a pasta do projeto no explorador de arquivos do SO. | MUST |
| FR-072 | Abrir um terminal já posicionado no diretório do projeto. | MUST |
| FR-073 | Abrir uma URL de serviço do projeto no browser padrão. | MUST |
| FR-074 | Reportar erro compreensível quando a ferramenta não estiver instalada, por exemplo `code` fora do PATH. | MUST |

## Dashboard

| ID | Requisito | Prio |
|----|-----------|------|
| FR-080 | Exibir totais: projetos, ativos, parados, com Docker, containers rodando. | MUST |
| FR-081 | Listar projetos com alteração Git pendente. | MUST |
| FR-082 | Listar serviços locais ativos com porta e link. | MUST |
| FR-083 | Listar projetos acessados recentemente. | MUST |
| FR-084 | Responder a partir de cache, sem executar varredura síncrona de disco. | MUST |

## Jobs (execução assíncrona)

| ID | Requisito | Prio |
|----|-----------|------|
| FR-090 | Toda ação com duração potencialmente maior que 2 s retorna um `job_id` em vez de bloquear. | MUST |
| FR-091 | Consultar o estado de um job: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `TIMEOUT` ou `CANCELLED`. | MUST |
| FR-092 | Consultar a saída acumulada (stdout e stderr) de um job. | MUST |
| FR-093 | Aplicar timeout por tipo de comando e marcar o job como `TIMEOUT`. | MUST |
| FR-094 | Cancelar um job em execução. | SHOULD |

## Auditoria

| ID | Requisito | Prio |
|----|-----------|------|
| FR-100 | Registrar toda ação executada com timestamp, projeto, ação, status, duração e mensagem. | MUST |
| FR-101 | Registrar o argv efetivamente executado, para rastreabilidade. | MUST |
| FR-102 | Listar o histórico com filtro por projeto e por ação. | MUST |
| FR-103 | Nunca gravar segredo ou variável de ambiente sensível no log. | MUST |

## Configuração por projeto

| ID | Requisito | Prio |
|----|-----------|------|
| FR-110 | Ler um arquivo `devcockpit.yml` opcional na raiz do projeto e importar sua configuração. | SHOULD |
| FR-111 | Exportar a configuração de um projeto cadastrado para `devcockpit.yml`. | SHOULD |
| FR-112 | Em conflito entre banco e arquivo, exigir resolução explícita do usuário. Nunca sobrescrever em silêncio. | MUST |
