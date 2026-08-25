# Context Engine

> **Status: proposta.**

## O problema

Mandar o projeto inteiro para o modelo é caro, lento e **pior**: contexto
excessivo dilui o que importa. Um projeto de 5.000 linhas cabe numa janela
moderna, mas 28 projetos não cabem, e a resposta útil quase nunca depende de
tudo.

O Context Engine responde a uma pergunta só: **o mínimo que precisa estar na
mensagem para esta pergunta ser bem respondida.**

## Pipeline

```
pergunta do usuário
        ↓
1. intenção          → o que se quer (planejar, depurar, documentar, analisar)
        ↓
2. escopo            → projeto ativo? todos? um arquivo?
        ↓
3. orçamento         → teto de tokens desta chamada
        ↓
4. coleta            → camadas, em ordem de prioridade
        ↓
5. corte             → o que não couber no orçamento cai, do menos relevante
        ↓
6. montagem          → mensagem final, com proveniência de cada bloco
        ↓
      provedor
```

## Camadas, em ordem de prioridade

A ordem é a de "o que dói mais faltar":

| # | Camada | Fonte | Tamanho típico |
|---|--------|-------|----------------|
| 1 | Identidade do projeto | `project`, `project_technology` | ~200 tokens |
| 2 | Memória fixa | `ai_memory` tipo `context`/`architecture` | ~500 |
| 3 | Sessão anterior | `ai_session` (resumo + próximos passos) | ~300 |
| 4 | Estado agora | dashboard, portas, saúde, Docker | ~300 |
| 5 | Decisões relevantes | `ai_memory` tipo `decision`, filtradas por assunto | ~500 |
| 6 | Git recente | branch, sujeira, últimos commits | ~300 |
| 7 | Trechos de arquivo | leitura sob demanda, só o pedido | variável |
| 8 | Documentação do projeto | README, `docs/`, `devcockpit.yml` | variável |

Camadas 1 a 4 são **sempre** incluídas: são o que impede a pergunta "de qual
projeto estamos falando?". Da 5 em diante, entram por relevância e orçamento.

## Seleção por relevância, sem embeddings (v1)

A tentação é vetorizar tudo. Para 28 projetos e memórias curtas, isso é
maquinaria demais: índice para manter, modelo de embedding para escolher,
banco vetorial para instalar — em cima de um SQLite que hoje não tem nada
disso.

**v1 usa busca lexical** (`LIKE` + pontuação por termo, com os termos da
pergunta e da stack do projeto). É previsível, depurável e custa zero
dependência. Se a qualidade não bastar — e a medida disso é o usuário reclamar
de resposta fora de contexto —, `sqlite-vec` entra como evolução, não como
fundação.

## Orçamento de tokens

Cada chamada tem teto declarado, vindo de `Settings`:

```
DEVCOCKPIT_AI_MAX_CONTEXT_TOKENS = 12000   # contexto montado
DEVCOCKPIT_AI_MAX_OUTPUT_TOKENS  =  2000   # resposta
```

O corte é por camada inteira, nunca por metade de bloco: meia decisão é pior
que nenhuma. Quando algo é cortado, **a resposta diz** — a mesma regra de
`truncated` que a tela de análise já usa. O painel não omite em silêncio.

## Proveniência

Cada bloco entra marcado com de onde veio:

```
[projeto:dashboard-contabil] stack: python, fastapi, postgres
[memória:decision#12] Autenticação por sessão, não JWT — ...
[sessão:2026-08-20] parou em: pipeline de importação
[estado] 2 serviços no ar (backend 8000, db 5434)
[git] branch main, 3 arquivos sujos
```

Serve a três coisas: o usuário pode ver o que a IA sabia, a resposta pode citar
a fonte, e uma resposta errada revela qual bloco estava velho.

## Injeção de prompt

Conteúdo lido de projeto (README, código, log de container) é **dado**, nunca
instrução. Três defesas:

1. tudo que vem de arquivo entra delimitado e rotulado como não confiável;
2. o modelo não recebe ferramentas de escrita quando o contexto inclui arquivo
   de terceiro;
3. ação proposta passa por confirmação humana e pela allowlist — um README que
   diga "apague tudo" não tem como virar comando.

O risco é real: o painel varre 28 projetos, e nem todos são código escrito pelo
usuário.

## Cache

Contexto montado é cacheado por `(projeto, intenção)` com TTL curto, no mesmo
`TTLCache` já usado. Perguntas seguidas no mesmo projeto não remontam tudo.
Qualquer escrita de memória ou fim de sessão invalida.

## Medição

O que se mede desde a primeira versão, senão não há como melhorar:

- tokens de contexto por chamada (média, p95);
- quantas camadas foram cortadas por orçamento;
- custo por sessão;
- taxa de pergunta seguida de "não é esse projeto" / correção do usuário.
