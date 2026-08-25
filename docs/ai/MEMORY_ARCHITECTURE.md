# Arquitetura de memória

> **Status: proposta.**

## Três níveis, três tempos de vida

```
MEMÓRIA GLOBAL       o desenvolvedor        vive para sempre
      ↓              preferências, padrões, comandos, stacks
MEMÓRIA DO PROJETO   um projeto             vive enquanto o projeto existir
      ↓              contexto, arquitetura, decisões, pendências, dívida
MEMÓRIA DA SESSÃO    um dia de trabalho     vira resumo ao terminar
                     objetivo, o que foi feito, o que ficou
```

A sessão é o que alimenta as outras duas: ao encerrar, o resumo entra na
memória do projeto, e o que for padrão (preferência, comando, convenção) pode
subir para a global — sempre com aprovação.

## A regra que impede memória virar ficção

> **Memória se ancora em fato observado ou em declaração do humano. Nunca em
> dedução do modelo apresentada como registro.**

É a mesma doutrina que fez o painel parar de dizer "no ar" sem prova. Aplicada
aqui:

| Entrada | Origem | Pode ir para a memória? |
|---------|--------|------------------------|
| "backend subiu às 11:43, pid 7944" | `activity_log` | sim — fato |
| "o serviço caiu 3 vezes ontem" | `health_snapshot` | sim — fato |
| "decidimos usar sessão em vez de JWT" | usuário escreveu ou aprovou | sim — declaração |
| "o projeto parece usar Clean Architecture" | inferência do modelo | **só como sugestão**, marcada, até alguém confirmar |

Toda linha de memória carrega `source` (`observed`, `human`, `ai_suggested`) e
`confirmed_at`. O Context Engine trata os três com pesos diferentes, e a tela
mostra a diferença. Sugestão não confirmada aparece com marca — nunca como
afirmação do projeto.

## Memória do projeto

```
ProjectMemory
├── context          o que é o projeto, para quem, qual problema resolve
├── architecture     como está construído; padrões adotados
├── decisions        escolha + alternativa descartada + porquê  (ADR curto)
├── tasks            o que falta, com prioridade
├── bugs             conhecidos, com estado
├── technical_debt   o que se sabe que está torto e por que ficou
├── discoveries      "o Postgres do compose é ignorado pelo .env local"
├── next_steps       derivado da última sessão
└── documentation    ponteiros para README/docs do próprio projeto
```

Uma tabela só (`ai_memory`) com `kind` discriminando, não nove tabelas: os
campos são os mesmos (texto, origem, relevância, datas) e o custo de nove
migrações não se paga. Ver [`AI_DATABASE_SCHEMA.md`](AI_DATABASE_SCHEMA.md).

### O que **não** é memória

Estado vivo. Porta, container, saúde, branch e sujeira do Git são consultados
na hora, do sistema que já os conhece. Copiar isso para dentro da memória
criaria uma segunda verdade que envelhece — exatamente o defeito que custou
duas sessões de conserto neste projeto.

## Memória global (Developer Memory)

```
DeveloperMemory
├── preferências     "prefere pytest a unittest", "comenta o porquê, não o quê"
├── padrões          convenções que se repetem entre projetos
├── stacks           o que o desenvolvedor usa e como configura
├── comandos         atalhos e receitas que funcionam nesta máquina
├── ambientes        Docker Desktop ocupa 8765; Postgres nativo em 5433
└── aprendizados     armadilhas já pagas
```

Alimentada por promoção explícita: ao encerrar uma sessão, o que se repetiu
entre projetos é **oferecido** para virar memória global. Nada sobe sozinho —
memória global errada contamina todos os projetos de uma vez.

## Memória da sessão

Uma sessão tem começo, objetivo, trabalho e fim:

```
Start Session                          End Session
  projeto escolhido                      o que foi feito (fatos coletados)
  contexto carregado                     arquivos tocados (git diff)
  última sessão lida                     ações executadas (activity_log)
  pendências lidas                       decisões (o usuário confirma)
  objetivo proposto → confirmado         pendências (o usuário confirma)
                                         próximo passo → memória
```

**O resumo de fim de sessão é montado de fatos, não escrito do zero pelo
modelo.** `git diff --stat` diz o que mudou; `activity_log` diz o que rodou;
`health_snapshot` diz o que subiu e caiu. O modelo redige e agrupa; ele não
inventa o que aconteceu. Isso é o que separa um registro confiável de um
diário simpático e inútil.

## Ciclo de vida e poda

A memória cresce. O painel já aprendeu essa lição com `activity_log` crescendo
sem limite:

- sessões: mantidas integralmente por `ai_session_retention_days` (padrão 180),
  depois só o resumo;
- memórias `ai_suggested` não confirmadas em 30 dias: apagadas;
- memórias confirmadas: nunca apagadas por rotina — só pelo usuário;
- poda roda no mesmo `RetentionService` que já existe.

## Ancoragem no projeto real

Onde o projeto tiver documentação própria (`README`, `docs/`, `devcockpit.yml`,
ADRs), a memória **aponta** em vez de copiar. Cópia envelhece; ponteiro não.
O Context Engine lê o arquivo na hora, se couber no orçamento.
