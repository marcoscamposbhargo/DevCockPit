# ADR-002 — SQLite no MVP com caminho para PostgreSQL

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O DevCockpit é uma aplicação local, single-user, que guarda o registro de
projetos, serviços, cache de estado Git/Docker e log de auditoria. O volume é
pequeno: dezenas de projetos, centenas de serviços, alguns milhares de linhas de
auditoria por mês.

O requisito real não é escala: é **query com filtro e índice** para o dashboard
responder rápido (NFR-010) sem varrer disco.

## Decisão

Usar **SQLite** como armazenamento no MVP, com acesso exclusivamente via
**SQLAlchemy** e **migrações versionadas desde a versão 0.1.0**. Nenhuma query
SQL espalhada pela aplicação: todo acesso passa pela camada
`app/repositories/`.

Migração para PostgreSQL fica viável sem reescrita, mas não é planejada — só
aconteceria se o produto deixasse de ser local, o que hoje é não-objetivo.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Arquivo JSON único** | sem query, sem índice, sem integridade referencial; escrita concorrente entre requisição e poller de background é frágil; migração de schema manual |
| **PostgreSQL já no MVP** | exigiria o usuário rodar um container só para usar a ferramenta que gerencia containers; dependência circular na experiência de instalação |
| **TinyDB / dataset** | economia marginal frente ao SQLite, que já vem na biblioteca padrão |
| **SQLite sem ORM (`sqlite3` puro)** | mais rápido de começar, mas espalharia SQL e fecharia a porta do PostgreSQL, contrariando o item 4 do prompt |

## Consequências

Positivas:
- zero dependência de infraestrutura: um arquivo em `data/`
- backup é copiar o arquivo
- índice e filtro reais para o dashboard
- migrações desde o início evitam perda de dado ao evoluir o schema (D-15)

Negativas:
- escrita concorrente é serializada; com poller de background e jobs escrevendo
  ao mesmo tempo, é preciso habilitar modo WAL e manter transação curta
- tipagem fraca do SQLite: `BOOLEAN` e `DATETIME` são convenção, não garantia;
  a validação real fica no Pydantic
- ORM adiciona indireção, custo aceitável pelo desacoplamento

Mitigações:
- `PRAGMA journal_mode=WAL` no startup
- transação curta e sessão por requisição
- purga periódica de `health_snapshot` para o arquivo não crescer sem limite

## Notas

Se o PostgreSQL entrar um dia, o trabalho previsto é: trocar a URL de conexão,
revisar tipos nas migrações e revisar as poucas expressões dependentes de
dialeto. O restante da aplicação não muda — é isso que a camada de repositório
compra.
