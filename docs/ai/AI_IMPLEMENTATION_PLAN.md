# Plano de implementação

> **Status: Fases 1 e 2 implementadas em 2026-08-25. As demais seguem propostas.**

## A inversão que esta análise propõe

O prompt de visão coloca a IA na Fase 1. A análise do sistema real sugere o
contrário: **a Fase 1 não precisa de IA nenhuma.**

Sessão, memória, tarefas e o briefing do dia são valor imediato e independente
de provedor — e são justamente a fundação que a IA precisa para não inventar.
Construí-los primeiro tem três efeitos:

1. o usuário ganha utilidade antes de configurar chave de API ou gastar centavo;
2. quando a IA entrar, ela lê fatos em vez de deduzir;
3. se a IA se mostrar cara ou ruim, o que ficou de pé continua útil.

É o mesmo princípio que o produto já segue: prova antes de afirmação.

---

## Fase 1 — Fundação sem IA ✅ entregue em 2026-08-25

**Entrega:** o painel passa a lembrar o trabalho.

Uma correção ao plano, feita na implementação: `ai_message` **não** entrou na
migração 006. Ela só passa a ser escrita quando o chat existir, e tabela criada
antes de alguém escrever nela é o defeito que este projeto já corrigiu duas
vezes (`health_snapshot` e `git_repository`). Fica para a Fase 2.

| # | Item | O que é |
|---|------|---------|
| 1.1 | ~~Migração `006`~~ | `ai_session`, `ai_memory`, `activity_log.actor/agent/reason`, `project.ai_enabled` |
| 1.2 | ~~`SessionService`~~ | abrir, encerrar, listar sessões |
| 1.3 | ~~Coleta de fatos~~ | `git diff --stat`, ações da janela, quedas de serviço |
| 1.4 | ~~`MemoryService`~~ | CRUD de memória com `source` e confirmação |
| 1.5 | ~~Rotas de sessão, memória e briefing~~ | contrato HTTP |
| 1.6 | ~~Tela **Sessão** no projeto~~ | iniciar, ver anterior, encerrar com resumo |
| 1.7 | ~~**Start My Day**~~ | briefing de todos os projetos, sem IA |
| 1.8 | ~~`actor` na auditoria~~ | preparação para o passo seguinte |

**Critério de saída — verificado em 2026-08-25**, no painel real: uma sessão
aberta no próprio DEVCOCKPIT marcou `e1e574a` com 24 arquivos sujos; ao
encerrar, o resumo saiu montado sozinho — *"1 commit(s), o último: 'feat:
sessão de trabalho e memória de projeto'. 4 arquivo(s) sem commit ao encerrar"*
— com o commit capturado pelo corte de sha, sem modelo nenhum configurado.
20 testes novos; 516 no total.

**Risco:** baixo. Nada disso toca execução de comando nem segurança.

---

## Fase 2 — O agente entra ✅ entregue em 2026-08-25

**Entrega:** perguntar sobre o projeto sem explicar o projeto.

| # | Item |
|---|------|
| 2.1 | ~~`AIProvider` + Anthropic, OpenAI e local (Ollama)~~ |
| 2.2 | ~~`ContextEngine` v1 — camadas, orçamento, proveniência~~ |
| 2.3 | ~~Chat com stream (SSE, mesmo transporte do console de job)~~ |
| 2.4 | ~~Redação de segredos e consentimento (D-A1, D-A2, D-A5)~~ |
| 2.5 | ~~`ai_usage_day`, teto diário, gasto visível na tela~~ |
| 2.6 | ~~Resumo de sessão redigido **a partir dos fatos**~~ |
| 2.7 | ~~Testes de segurança (os sete de `AI_SECURITY.md`)~~ |

**Critério de saída — verificado em 2026-08-25.** Sem chave de provedor à mão,
a verificação foi feita contra um servidor que imita a API e **relata o que
recebeu**:

- o contexto chegou com identidade do projeto, memória, sessão em andamento,
  estado e o README rotulado como *dado, não instrução*;
- um projeto com `.env` contendo `OPENAI_API_KEY` e `DB_PASSWORD`: **nada disso
  chegou ao provedor**;
- um `README.md` com `STRIPE_SECRET_KEY=sk-live-…`: chegou **redigido**;
- gasto contabilizado e visível (1.290 tokens na primeira pergunta).

O que **não** foi verificado, e precisa ser dito: nenhuma chamada à API real de
nenhum provedor. O formato de requisição e a leitura do stream dos três estão
exercitados por HTTP contra o servidor de imitação
(`tests/unit/test_ai_provider_wire.py`), o que prova o cliente — não o contrato
do fornecedor.

**Risco:** médio — é onde dado passa a sair da máquina. Os sete testes de
segurança passam.

---

## Fase 3 — Especialistas, ações e tarefas

| # | Item |
|---|------|
| 3.1 | ~~Migração `007` (`ai_task`) e tela de tarefas por projeto~~ ✅ |
| 3.2 | Perfis de especialista + prompts versionados |
| 3.3 | Orquestrador (regra primeiro, modelo no empate) |
| 3.4 | ~~Ações propostas com confirmação e classificação~~ ✅ |
| 3.5 | Command palette (`/plan`, `/find-bugs`, `/status`…) |
| 3.6 | `activity_log` com `actor="ai"` ponta a ponta |

**Critério de saída — 3.4 verificado em 2026-08-25**, no app instalado: "sobe o
kiteasy" devolveu `environment.up` em **0,2 s** (caminho da regra, sem tocar no
modelo), com cartão de confirmação nomeando o projeto; "faz o deploy em
produção" foi **recusado**, porque `deploy` não existe no registro.

Antes de implementar, dois números decidiram o desenho: o `qwen2.5-coder:7b`
acertou 6 de 6 na escolha de ação e 7 de 7 na escolha de projeto entre 18
cadastrados — inclusive corrigindo "smartdah" para `smartdash`. O `3b` falhou
justamente em recusar o que não existe.

Falta de 3.4: a execução confirmada ainda é auditada como ação do usuário. É
verdade parcial — quem propôs foi a IA —, e fecha com 3.6.

**Risco:** médio-alto — é onde a IA encosta em execução. A defesa é não ter
capacidade nova nenhuma (D-A3), verificada por teste.

---

## Fase 4 — Project Intelligence

| # | Item |
|---|------|
| 4.1 | Tela Project Intelligence |
| 4.2 | Health Score com critérios mensuráveis |
| 4.3 | Recomendação de próxima ação a partir de fatos + memória |

Critérios do score, todos derivados de algo que o painel já mede — **sem número
inventado**:

| Indicador | Como se mede | Fonte |
|-----------|--------------|-------|
| Documentação | README existe, tem seções mínimas, `docs/` existe, `devcockpit.yml` presente | disco |
| Testes | diretório de testes, suíte roda, cobertura se declarada | disco + execução |
| Git | frequência de commit, arquivos sujos, upstream configurado | `GitService` |
| Ambiente | sobe pelo painel, portas sem conflito, health estável | `analytics` + portas |
| Atividade | sessões recentes, tarefas fechadas | `ai_session`, `ai_task` |
| Dívida | itens de `technical_debt` abertos | `ai_memory` |

Indicador sem dado **não vira zero**: vira "não medido", e o score agregado diz
sobre quanto foi calculado. Zero é uma afirmação; ausência não é.

---

## Fase 5 — Dados e automação

Data Analyst sobre CSV/Excel, análise de qualidade de dados, recomendação de
visualização; workflows e automações.

Fica por último de propósito: é a fase mais distante do uso diário atual do
painel, e a que mais depende de as anteriores terem ficado boas.

---

## O que muda por fase (resumo de impacto)

| Fase | Arquivos novos | Arquivos tocados | Migração | Dado sai da máquina |
|------|----------------|------------------|----------|---------------------|
| 1 | ~10 | 4 | 2 | não |
| 2 | ~8 | 3 | — | **sim** |
| 3 | ~6 | 4 | 1 | sim |
| 4 | ~4 | 2 | — | sim |
| 5 | ~6 | 2 | 1 | sim |

## Antes de qualquer linha de código — resolvido

As três pendências que travavam o início foram fechadas antes da Fase 1: o
trabalho acumulado virou sete commits temáticos, a `main` absorveu a branch de
varredura, e o repositório foi publicado (privado). Sobra decidir se
`Dockerfile`, `docker-compose.yml` e `.dockerignore` entram.
