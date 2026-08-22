# 08 — Especificação da Configuração de Projeto

O item 7 do prompt pede um estudo sobre o formato: YAML, JSON, banco ou
combinação. Este documento é a resposta.

## Análise

| Opção | A favor | Contra |
|-------|---------|--------|
| Só YAML no projeto | versionável, portável, legível, viaja com o repositório | consultar 30 projetos é ler 30 arquivos do disco; não serve para dashboard; sem índice; sem histórico |
| Só JSON central | um arquivo, fácil de ler em bloco | escrita concorrente frágil, sem query, sem migração, sem integridade |
| Só banco (SQLite) | query, índice, integridade, migração, rápido para dashboard | invisível, não versionável, não viaja com o projeto, difícil de editar à mão |

O erro é tratar como escolha binária. Os dois casos de uso são diferentes:

- **Consulta agregada** (dashboard, listas, filtros) exige índice e query.
- **Definição do projeto** (portas, comandos, serviços) pertence ao projeto e
  deveria viajar com ele no Git.

## Decisão

**SQLite é a fonte de verdade operacional. `devcockpit.yml` é um manifesto
opcional, versionável, com sincronização explícita.**

Formalizado em `ADR-004`.

Consequências:

- o DevCockpit funciona sem nenhum `devcockpit.yml` — o arquivo é conveniência,
  não requisito;
- projeto com manifesto ganha configuração reproduzível em outra máquina;
- a sincronização é sempre **ação do usuário**, nunca automática em background.
  Sobrescrita silenciosa de configuração é o tipo de bug que destrói confiança
  na ferramenta (FR-112).

YAML e não JSON para o manifesto: comentário. Um arquivo de configuração que
um humano edita precisa poder explicar por que a porta é 5173.

## Schema do `devcockpit.yml`

Fica na raiz do projeto gerenciado. Todos os campos são opcionais exceto
`version` e `name`.

```yaml
# versão do schema deste arquivo, não do projeto
version: 1

name: Dashboard Contábil
description: Painel de indicadores contábeis

# livre; complementa a detecção automática, não a substitui
stack:
  - python
  - fastapi
  - postgresql
  - docker

docker:
  enabled: true
  compose_file: docker-compose.yml
  # nome do projeto Compose; default = nome da pasta
  project_name: dashboard-contabil

services:
  frontend:
    label: Frontend
    port: 5173
    url: http://localhost:5173
    health: http://localhost:5173
    open_in_browser: true

  backend:
    label: Backend
    port: 8000
    url: http://localhost:8000
    health: http://localhost:8000/health

  api_docs:
    label: API Docs
    url: http://localhost:8000/docs
    # sem porta e sem health: é atalho, não serviço monitorado
    health_kind: none

  database:
    label: PostgreSQL
    port: 5432
    # sem URL HTTP: check por TCP
    health_kind: tcp

repository:
  provider: github
  url: https://github.com/usuario/dashboard-contabil
```

### Campos deliberadamente ausentes

| Campo | Por que não existe |
|-------|--------------------|
| `path` | o path é onde o arquivo está; declará-lo criaria contradição possível |
| `commands` / `start_command` | executar comando declarado em arquivo do projeto quebra a allowlist (D2). Ver abaixo. |
| `env` / segredos | o DevCockpit não lê `.env` de projeto (D8) |
| `hooks` / scripts | mesma razão que `commands` |

### Sobre `start_command`

É a ausência mais sentida: seria natural declarar
`start_command: uvicorn app.main:app --reload`. Está fora do MVP porque um
arquivo dentro de um repositório clonado se tornaria fonte de comando
executável — exatamente o que o modelo de segurança impede. Clonar um repo de
terceiro passaria a ser suficiente para executar código.

Se entrar no roadmap, precisa de: confirmação explícita na primeira execução
por projeto, exibição do comando exato antes de rodar, e ADR próprio.
Até então, subir projeto é via Docker Compose, que é declarativo e já tem
limites conhecidos.

## Regras de validação

| Regra |
|-------|
| `version` desconhecida → arquivo ignorado com aviso na UI, nunca erro fatal |
| YAML inválido → aviso, projeto continua funcionando pelo banco |
| `compose_file` precisa ser relativo e resolver dentro do path do projeto |
| `port` inteiro em 1–65535 |
| `url` e `health` restritos a `http`/`https` com host `localhost`, `127.0.0.1` ou `[::1]` |
| chave de serviço em `[a-z0-9_-]{1,32}` |
| campo desconhecido → ignorado, com aviso |

A restrição de host nas URLs impede que um manifesto transforme o DevCockpit em
cliente HTTP para host arbitrário.

## Sincronização

Três operações, todas iniciadas pelo usuário:

| Operação | Efeito |
|----------|--------|
| **Importar** | lê `devcockpit.yml` e aplica ao banco. Padrão no cadastro de projeto que já tem o arquivo. |
| **Exportar** | escreve o estado do banco em `devcockpit.yml`. Única situação em que o DevCockpit escreve em pasta de projeto, sempre com confirmação. |
| **Comparar** | mostra as diferenças entre banco e arquivo, campo por campo, sem alterar nada. |

Ao abrir um projeto cujo manifesto divergiu do banco, a UI mostra um aviso com
a comparação e dois botões explícitos. Nenhuma resolução automática (FR-112).

## Precedência de dados

Da menor para a maior autoridade sobre a configuração final:

```
1. defaults do DevCockpit          (configs/defaults.yml)
2. detecção automática             (source = DETECTED)
3. devcockpit.yml importado        (no momento da importação)
4. edição manual do usuário na UI  (source = MANUAL) — vence sempre
```

Edição manual grava `source: MANUAL` e `detection_locked`, e nova detecção não
a desfaz (FR-024). O usuário sempre tem a última palavra sobre a própria
máquina.

## `configs/` do próprio DevCockpit

| Arquivo | Conteúdo | Editável por API? |
|---------|----------|-------------------|
| `configs/roots.yml` | roots permitidos (D4) | **Não.** Só no disco. |
| `configs/defaults.yml` | TTLs, timeouts, intervalo do poller, profundidade de scan | Não no MVP |
| `configs/detectors.yml` | detectores habilitados e ordem | Não no MVP |
| `.env` | porta do servidor, nível de log, path do banco | Não |

`roots.yml` fora do alcance da API é o que sustenta a defesa D4: uma allowlist
que o próprio cliente pode ampliar não é allowlist.
