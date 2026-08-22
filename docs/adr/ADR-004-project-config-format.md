# ADR-004 — SQLite como fonte de verdade e `devcockpit.yml` opcional

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O item 7 do prompt pede um estudo sobre onde a configuração de cada projeto
deve viver: YAML, JSON, banco de dados, ou combinação.

Há dois casos de uso diferentes escondidos na mesma pergunta:

1. **Consulta agregada** — o dashboard precisa filtrar 30 projetos por status,
   stack e porta em menos de 500 ms. Isso pede índice e query.
2. **Definição do projeto** — portas, serviços e configuração de Compose
   descrevem o projeto e idealmente viajariam com ele no Git, legíveis e
   editáveis por humano.

Escolher um formato só significa perder um dos dois.

## Decisão

**SQLite é a fonte de verdade operacional. `devcockpit.yml` na raiz do projeto
é um manifesto opcional, versionável, com sincronização sempre explícita.**

- o DevCockpit funciona plenamente sem nenhum manifesto
- projeto que tem manifesto ganha configuração reproduzível em outra máquina
- importar, exportar e comparar são ações do usuário; nunca há sincronização
  automática em background
- em divergência, a UI mostra a comparação e exige escolha (FR-112)

Precedência, da menor para a maior autoridade:

```
defaults do DevCockpit -> detecção automática -> devcockpit.yml importado
-> edição manual do usuário (vence sempre)
```

Schema completo em `08-project-configuration-spec.md`.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Só YAML por projeto** | montar o dashboard exigiria ler 30 arquivos do disco a cada consulta; sem índice, sem filtro, sem histórico de acesso |
| **Só JSON central** | escrita concorrente frágil entre requisição e poller; sem query; migração de schema manual |
| **Só banco** | configuração invisível, não versionável, não viaja com o projeto, difícil de editar à mão — perde exatamente o valor que o item 7 buscava |
| **Sincronização automática bidirecional** | sobrescrita silenciosa de configuração é o tipo de bug que destrói a confiança na ferramenta; e resolver conflito automaticamente exigiria heurística que erra |
| **JSON em vez de YAML no manifesto** | JSON não tem comentário. Um arquivo que humano edita precisa poder explicar por que a porta é 5173 |

## Consequências

Positivas:
- dashboard rápido, com índice, sem tocar no disco
- projeto opcionalmente autodescritivo e portável entre máquinas
- nenhuma configuração é perdida por sincronização silenciosa
- ausência do arquivo nunca degrada a experiência

Negativas:
- duas fontes possíveis de configuração exigem UI de comparação e resolução —
  trabalho extra na Fase 4
- exportar é a única situação em que o DevCockpit escreve dentro da pasta de um
  projeto gerenciado; exige confirmação explícita e está isolado num único
  serviço

## Restrições que o manifesto herda do modelo de segurança

O manifesto vive dentro de um repositório, que pode ter sido clonado de
terceiro. Por isso ele **não pode declarar comando executável**:

- sem `start_command`, sem `commands`, sem `hooks`, sem `scripts`
- `compose_file` precisa ser relativo e resolver dentro do path do projeto
- `url` e `health` restritos a `http`/`https` com host local
- campo desconhecido é ignorado com aviso, nunca interpretado

Sem essas restrições, clonar um repositório passaria a ser suficiente para
executar código, anulando o ADR-003.
