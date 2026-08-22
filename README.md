# DevCockpit

Central local de gerenciamento dos projetos de desenvolvimento da sua máquina.

Um lugar só para responder: **quais projetos eu tenho, o que está rodando, o
que tem alteração pendente, qual porta é de quem** — e executar as ações mais
frequentes sem abrir terminal.

> **Status: MVP completo.** Fases 0 a 4 concluídas, 131 pontos, 285 testes.
> A ferramenta encontra seus projetos, identifica a stack, mostra o Git, opera
> o Docker, verifica os serviços locais e abre VS Code, pasta e terminal.
> Acompanhe em [`PROJECT_STATUS.md`](PROJECT_STATUS.md).

---

## O problema

Manter 30 projetos locais significa manter 30 conjuntos de conhecimento
operacional na cabeça: onde a pasta está, qual comando sobe, qual porta usa,
qual container é de qual projeto, se tem coisa sem commit. Retomar um projeto
parado há três semanas custa de 5 a 15 minutos de arqueologia.

Toda essa informação já está no disco. O DevCockpit lê, guarda o que não é
derivável e coloca as ações a um clique.

## O que ele faz (MVP planejado)

| Módulo | Entrega |
|--------|---------|
| **Dashboard** | totais do ambiente, pendências Git, serviços ativos, conflito de porta |
| **Projects** | cadastro, edição, busca e **varredura automática** de uma pasta raiz |
| **Detection** | identifica stack por marcadores (`pyproject.toml`, `package.json`, `docker-compose.yml`, ...) |
| **Git** | branch, alterações, último commit, histórico, remotes — **somente leitura** |
| **Docker** | containers, `compose up/down/start/stop/restart`, logs em tempo real |
| **Services** | health check de `localhost` com estado `ONLINE`/`OFFLINE`/`ERROR` |
| **Ações** | abrir no VS Code, abrir pasta, abrir terminal no diretório, abrir o app |
| **Activity** | log de auditoria de tudo que foi executado |

## O que ele não faz — por decisão

```
terminal web · editor de código · IDE embutida · CI/CD próprio
Kubernetes · execução remota · multiusuário · escrita destrutiva no Git
```

Não são "features futuras": exigiriam refazer o modelo de segurança inteiro.

## Segurança

O DevCockpit executa comandos na sua máquina. Isso é o produto — e é o risco.
Três garantias estruturais:

1. **Escuta só em `127.0.0.1`.** Validado no código, não apenas na configuração.
   Não existe flag para expor na rede.
2. **Nenhum comando vem do cliente.** A interface envia identificadores de ação
   (`docker.up`); a tradução para comando é uma tabela fixa no código. Não
   existe `/execute-command`. Execução sempre sem shell, com argv em lista.
3. **Todo path é validado** contra uma allowlist de diretórios raiz, com
   resolução de symlink. A allowlist só é editável no disco, nunca pela API.
4. **`Host` e `Origin` validados.** Toda requisição precisa chegar por
   `localhost`/`127.0.0.1`; requisição de escrita exige `Origin` próprio. É o
   que fecha DNS rebinding, o ataque que derrota a checagem ingênua de origem.

O modelo completo, com ameaças, defesas e testes obrigatórios, está em
[`docs/07-security-model.md`](docs/07-security-model.md).

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy |
| Banco | SQLite (com migrações desde a v0.1.0) |
| Frontend | HTML, CSS e JavaScript — ES modules, sem framework, sem build |
| Externo | `git` CLI, `docker compose` v2 CLI |

Cada escolha tem ADR em [`docs/adr/`](docs/adr/).

## Documentação

| Doc | Conteúdo |
|-----|----------|
| [00 — Product Vision](docs/00-product-vision.md) | problema, público, valor, longo prazo |
| [01 — PRD](docs/01-product-requirements.md) | objetivos, personas, casos de uso, riscos |
| [02 — Requisitos Funcionais](docs/02-functional-requirements.md) | `FR-001` em diante |
| [03 — Requisitos Não Funcionais](docs/03-non-functional-requirements.md) | `NFR-001` em diante |
| [04 — Arquitetura](docs/04-system-architecture.md) | camadas, diagramas, fluxos, estrutura |
| [05 — Modelo de Dados](docs/05-data-model.md) | entidades, campos, índices |
| [06 — API](docs/06-api-specification.md) | endpoints, payloads, erros |
| [07 — Segurança](docs/07-security-model.md) | ameaças, defesas, testes obrigatórios |
| [08 — Config de Projeto](docs/08-project-configuration-spec.md) | `devcockpit.yml` e precedência |
| [09 — Roadmap](docs/09-development-roadmap.md) | fases com critério de saída |
| [10 — Testes](docs/10-testing-strategy.md) | pirâmide, fakes, fixtures, metas |
| [11 — UI/UX](docs/11-ui-ux-spec.md) | design system, telas, acessibilidade |
| [12 — Decisões](docs/12-decisions.md) | índice de ADRs e decisões menores |
| [13 — Backlog](docs/13-backlog.md) | épicos, histórias, critérios de aceite |

## Estrutura

```
app/
  api/routes/        rotas HTTP — não conhecem o sistema operacional
  core/              config, log, erros, validação de path, cache
  models/ schemas/   SQLAlchemy e Pydantic
  repositories/      acesso a dados, sem query espalhada
  services/          casos de uso
  runner/            CommandRunner — único ponto de execução
  jobs/              execução assíncrona
  detection/         registry extensível de detectores de stack
  adapters/          git · docker · system · github
frontend/            HTML, CSS e ES modules, sem build
migrations/ data/ configs/ docs/ tests/ scripts/ docker/
```

## Como rodar

Um comando, do zero:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

O script cria o ambiente virtual, instala as dependências, copia o `.env`,
aplica as migrações e sobe o servidor em `http://127.0.0.1:8765`.

Passo obrigatório antes do primeiro cadastro — defina os diretórios permitidos:

```powershell
copy configs\roots.example.yml configs\roots.yml
# edite allowed_roots com as pastas onde seus projetos vivem
```

Sem isso nenhum projeto pode ser cadastrado, por decisão de segurança
(defesa D4). O arquivo não é editável pela API.

Manualmente, se preferir:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

### No dia a dia

Deixe rodando numa janela e acesse `http://127.0.0.1:8765`.

Primeira vez:

1. **Projects → Varrer diretório** — aponte `C:/Users/User/Desktop` e importe
   tudo de uma vez. É mais rápido que cadastrar um a um.
2. **Fixe os 3 ou 4 projetos do momento** — eles vão para a sidebar, e são os
   únicos que o verificador de serviços acompanha em background.
3. **Dashboard** passa a responder: o que está no ar, o que tem alteração
   pendente, que porta está em conflito.

Atalhos: `Ctrl+K` busca projeto, `g d` vai para o Dashboard, `g p` para
Projects, `r` recarrega a tela.

### Testes

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing
.venv\Scripts\python.exe -m ruff check app tests
```

Os testes que exigem Docker estão marcados e não rodam por padrão.

## O que já funciona

**Projetos**
- cadastro, listagem, busca, edição e remoção — sem nunca tocar em arquivo do disco
- **varredura de um diretório raiz**: 31 projetos encontrados em 0,19 s no
  Desktop real, com importação em lote
- detecção de stack por 12 marcadores, com portas extraídas do arquivo Compose
  e do `vite.config.*`
- edição manual da stack vence a detecção automática, sempre

**Git (somente leitura)**
- branch, ahead/behind, contagem por tipo de alteração, arquivos, commits,
  branches e remotes
- um diretório só conta como repositório se for a **raiz** dele — ver
  [ADR-008](docs/adr/ADR-008-git-repo-root-detection.md), que existe por causa
  de um bug real encontrado por teste

**Docker**
- containers do projeto com serviço, estado, health, imagem e portas
  publicadas, lidas do campo estruturado do Compose
- `up`, `down`, `start`, `stop` e `restart` com console ao vivo
- logs por serviço, com `tail` configurável
- nome de serviço é validado contra o Compose do projeto: desconhecido é 422 e
  nenhum comando roda
- Docker Desktop desligado degrada para "indisponível", sem quebrar a tela
- não existe caminho para `down -v`, `prune` ou `volume rm` — perder volume é
  perder dado

**Operações longas**
- job assíncrono com saída **incremental**: o console mostra o progresso
  enquanto o comando roda, em vez de uma tela parada
- exclusão mútua por chave: duas operações no mesmo projeto ao mesmo tempo
  recebem `409`, sem executar
- timeout que encerra a **árvore** de processos — verificado com um processo de
  teste que ignora o sinal de término, e com 20 execuções seguidas sem deixar
  órfão
- SSE para acompanhar em tempo real, com queda automática para polling

**Serviços locais**
- health check HTTP e TCP, concorrente, com timeout de 2 s
- verificador em background para projetos fixados e acessados recentemente;
  qualquer projeto pode ser verificado sob demanda
- estado `STALE` quando o dado envelhece — a tela nunca finge tempo real
- mapa de portas com detecção de conflito entre projetos

**Ações de um clique**
- abrir no VS Code, abrir a pasta, abrir o terminal já no diretório
- abrir a URL de um serviço, por chave cadastrada e nunca por URL do cliente
- ação indisponível aparece desabilitada **com o motivo**, em vez de falhar
  depois do clique

**Dashboard**
- totais do ambiente, alterações pendentes, serviços online, conflito de porta
  e projetos recentes
- servido de cache, com a idade do dado à vista: **168 ms** medidos

**Manifesto `devcockpit.yml`**
- importar, exportar e **comparar campo a campo** — nunca há resolução
  automática de conflito (FR-112)
- manifesto de um projeto que você acabou de cadastrar é importado sozinho;
  arquivo quebrado não impede o cadastro
- YAML inválido, versão desconhecida e campo estranho viram **aviso**: o
  projeto continua funcionando pelo banco
- URL do manifesto restrita a `localhost`, e `compose_file` que escape do
  diretório do projeto é recusado — um repositório clonado de terceiro não
  transforma o DevCockpit em cliente HTTP de host arbitrário
- exportar é a **única** escrita do DevCockpit dentro de pasta de projeto, e
  exige confirmação explícita

**Fundação**
- `CommandRunner` com argv, timeout obrigatório, captura e auditoria
- validação de path com allowlist, resolução de symlink e proteção contra traversal
- guards de `Host` e `Origin`, bind loopback validado no startup
- log de auditoria com `correlation_id`

**Interface**: Dashboard, Projects, descoberta com console de job, página do
projeto com abas Overview, Git, Docker, Services e Manifest, Activity e
Settings. Tema claro e escuro, seguindo o sistema por padrão.

301 testes passando, cobertura de 92%.

## Como contribuir com este código

Regra de trabalho, aplicada em toda fase:

```
READ -> ANALYZE -> PLAN -> IMPLEMENT -> TEST -> DOCUMENT
```

Uma entrega só está pronta com **código + testes + documentação** juntos.
A definição completa de pronto está em
[`docs/10-testing-strategy.md`](docs/10-testing-strategy.md).

Os testes de segurança de `docs/07` são bloqueantes: falha ali reprova a
entrega.

## Licença

Uso pessoal. Ainda sem licença definida.
