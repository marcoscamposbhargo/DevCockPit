# Plano de implementação

> **Status: proposta, aguardando autorização.**

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

## Fase 1 — Fundação sem IA

**Entrega:** o painel passa a lembrar o trabalho.

| # | Item | O que é |
|---|------|---------|
| 1.1 | Migração `006` + `007` | tabelas de sessão, mensagem e memória |
| 1.2 | `SessionService` | abrir, encerrar, listar sessões |
| 1.3 | Coleta de fatos | `git diff --stat`, ações da janela, quedas de serviço |
| 1.4 | `MemoryService` | CRUD de memória com `source` e confirmação |
| 1.5 | Rotas `/api/ai/sessions`, `/api/ai/memory` | contrato HTTP |
| 1.6 | Tela **Sessão** no projeto | iniciar, ver anterior, encerrar com resumo |
| 1.7 | **Start My Day** | briefing de todos os projetos, sem IA |
| 1.8 | `actor` na auditoria | preparação para o passo seguinte |

**Critério de saída:** encerrar uma sessão e, no dia seguinte, o painel dizer
onde parou — com dados que ele mesmo observou, sem modelo nenhum configurado.

**Risco:** baixo. Nada disso toca execução de comando nem segurança.

---

## Fase 2 — O agente entra

**Entrega:** perguntar sobre o projeto sem explicar o projeto.

| # | Item |
|---|------|
| 2.1 | `AIProvider` + implementação Anthropic |
| 2.2 | `ContextEngine` v1 (camadas 1–6, busca lexical, orçamento) |
| 2.3 | Chat contextual com stream (SSE, reusando o padrão do console de job) |
| 2.4 | Redação de segredos e consentimento (D-A1, D-A2, D-A5) |
| 2.5 | `ai_usage_day`, teto diário, custo visível na tela |
| 2.6 | Resumo de sessão redigido pelo modelo **a partir dos fatos** da Fase 1 |
| 2.7 | Testes de segurança da IA (os sete de `AI_SECURITY.md`) |

**Critério de saída:** três perguntas reais respondidas com contexto correto;
custo por sessão visível; nenhuma chave vazando em nenhum caminho de contexto.

**Risco:** médio — é onde dado passa a sair da máquina. Nada avança sem os
testes 2.7 passando.

---

## Fase 3 — Especialistas, ações e tarefas

| # | Item |
|---|------|
| 3.1 | Migração `008` (`ai_task`) e tela de tarefas por projeto |
| 3.2 | Perfis de especialista + prompts versionados |
| 3.3 | Orquestrador (regra primeiro, modelo no empate) |
| 3.4 | Ações propostas com confirmação e classificação |
| 3.5 | Command palette (`/plan`, `/find-bugs`, `/status`…) |
| 3.6 | `activity_log` com `actor="ai"` ponta a ponta |

**Critério de saída:** o agente propõe "subir o Postgres deste projeto", o
usuário confirma, a ação roda pela allowlist e aparece na auditoria como IA.

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

## Antes de qualquer linha de código

Três pendências do repositório, que ficam piores com módulo novo por cima:

1. **52 arquivos sem commit**, acumulando sete sessões de trabalho;
2. a branch `varredura/bugs-e-organizacao` está 32 commits à frente da `main`;
3. `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz,
   sem decisão.

Começar o Cockpit AI sobre isso significa que um `git reset` errado leva junto
dois dias de trabalho e o módulo novo. **Recomendação: commitar e resolver a
branch antes da Fase 1.**
