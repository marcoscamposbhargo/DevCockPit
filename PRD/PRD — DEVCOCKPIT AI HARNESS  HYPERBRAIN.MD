# PRD — DEVCOCKPIT AI HARNESS / HYPERBRAIN

## 1. Visão do Produto

O **DevCockpit AI Harness / Hyperbrain** será a camada central de inteligência artificial do DevCockpit.

Seu objetivo não é ser apenas mais um chat com IA.

Ele deverá funcionar como uma plataforma de:

* orquestração de LLMs;
* roteamento inteligente de modelos;
* agentes de desenvolvimento;
* gerenciamento de contexto dos projetos;
* RAG;
* memória de projeto;
* integração com Git;
* integração com Docker;
* execução controlada de ferramentas;
* análise de código;
* QA;
* observabilidade;
* controle de consumo;
* otimização de custo.

O DevCockpit continuará sendo a interface principal.

O Hyperbrain será o cérebro.

O AI Harness será a infraestrutura responsável por conectar:

* modelos locais;
* APIs externas;
* agentes;
* projetos;
* ferramentas;
* dados;
* memória;
* RAG.

---

# 2. Princípio Fundamental

O DevCockpit não deve depender de nenhuma LLM específica.

OpenAI, Anthropic, DeepSeek, Google, Qwen, Llama, Mistral ou qualquer outro modelo deverão ser tratados como **provedores substituíveis de inteligência**.

A arquitetura deve seguir o princípio:

> O conhecimento pertence ao projeto.
> O Harness pertence ao DevCockpit.
> O modelo é substituível.

---

# 3. Objetivo Estratégico

Criar uma infraestrutura própria capaz de escolher automaticamente o melhor recurso de IA considerando:

1. tipo da tarefa;
2. complexidade;
3. custo;
4. velocidade;
5. disponibilidade;
6. tamanho do contexto;
7. privacidade;
8. capacidade de ferramentas;
9. qualidade esperada.

A regra econômica principal será:

> LOCAL FIRST → LOW COST CLOUD → PREMIUM ON DEMAND.

Ou seja:

1. tentar modelo local;
2. escalar para API econômica;
3. utilizar modelos premium somente quando necessário.

---

# 4. Arquitetura Geral

```text
DEVCOCKPIT
│
├── Dashboard
├── Projetos
├── Terminal
├── Git
├── Docker
├── Arquivos
│
└── HYPERBRAIN
        │
        ▼
    AI HARNESS
        │
        ├── Task Classifier
        ├── Agent Router
        ├── Model Router
        ├── Provider Router
        ├── Cost Router
        ├── Context Engine
        ├── RAG Engine
        ├── Memory Engine
        ├── Tool Engine
        ├── Evaluation Engine
        ├── Fallback Engine
        └── Observability
                 │
                 ▼
             PROVIDERS
```

---

# 5. Camadas do Sistema

## 5.1 DevCockpit

Interface utilizada pelo usuário.

Responsável por:

* gerenciamento dos projetos;
* acesso ao Hyperbrain;
* visualização de agentes;
* seleção opcional de modelo;
* histórico;
* logs;
* consumo;
* custo;
* Git;
* Docker;
* terminal;
* documentação;
* arquivos.

O usuário não deverá precisar conhecer a infraestrutura interna do Harness.

---

# 6. Hyperbrain

O Hyperbrain representa a interface operacional da inteligência artificial.

Ele deverá conhecer:

* projeto atual;
* stack;
* arquitetura;
* arquivos;
* documentação;
* decisões anteriores;
* tarefas;
* issues;
* Git;
* testes;
* estado do projeto.

Exemplo:

```text
Usuário:

"Analise o projeto e veja se existem problemas
na arquitetura antes de continuarmos."

Hyperbrain
     ↓
Project Context
     ↓
Task Classifier
     ↓
Architecture Agent
     ↓
Model Router
     ↓
modelo escolhido
     ↓
resultado
```

---

# 7. AI Harness

O AI Harness será um serviço independente.

Tecnologia inicialmente recomendada:

```text
Python
FastAPI
Pydantic
PostgreSQL
Redis
Docker
Docker Compose
```

O frontend do DevCockpit nunca deverá acessar diretamente as APIs das LLMs.

Fluxo:

```text
Frontend
   ↓
DevCockpit API
   ↓
AI Harness
   ↓
Provider
   ↓
LLM
```

---

# 8. Provider Registry

Criar uma abstração única para providers.

Estrutura conceitual:

```text
providers/
│
├── ollama.py
├── deepseek.py
├── openai.py
├── anthropic.py
├── google.py
├── groq.py
├── openrouter.py
├── mistral.py
└── custom.py
```

Interface padrão:

```python
class LLMProvider:

    async def generate():
        ...

    async def stream():
        ...

    async def healthcheck():
        ...

    async def models():
        ...
```

Nenhuma regra de negócio poderá depender diretamente de um SDK específico.

---

# 9. Model Registry

Modelos e providers são conceitos diferentes.

Exemplo:

```text
MODEL:
Qwen

PROVIDER:
Ollama
Groq
OpenRouter
```

Criar:

```yaml
models:

  qwen_coder:

    capabilities:
      - coding
      - debugging
      - agents

    providers:
      - ollama
      - groq
      - openrouter

    cost_tier: low
```

---

# 10. Modelos da V1

Preparar integração para:

## Local

* Qwen
* Llama
* Mistral
* Gemma
* Phi
* GPT-OSS
* variantes DeepSeek compatíveis com execução local

Runtime principal:

* Ollama

Runtime futuro:

* vLLM

---

# 11. Cloud / APIs

Preparar suporte desacoplado para:

* DeepSeek;
* OpenAI;
* Anthropic;
* Gemini;
* Groq;
* OpenRouter;
* Mistral;
* Together;
* outros providers compatíveis.

Nem todos precisam estar ativados.

O sistema deverá trabalhar com:

```yaml
enabled: true
```

ou:

```yaml
enabled: false
```

---

# 12. Task Classifier

Toda requisição deverá inicialmente ser classificada.

Exemplos:

```text
coding
debugging
architecture
documentation
testing
qa
data_analysis
research
planning
refactoring
classification
rag_query
simple_task
```

Além disso:

```json
{
  "complexity": 62,
  "privacy": "internal",
  "context_size": "medium",
  "tools_required": true
}
```

---

# 13. Model Router

Responsável por selecionar o modelo.

Exemplo:

```text
Corrigir CSS
↓
complexidade baixa
↓
Qwen local
```

Outro exemplo:

```text
Revisar arquitetura completa
↓
complexidade alta
↓
DeepSeek / modelo superior
```

---

# 14. Cost Router

Deverá impedir desperdício de tokens e APIs.

Regras:

```text
LOW COMPLEXITY
→ local

MEDIUM
→ local forte / API barata

HIGH
→ DeepSeek / outro cloud

CRITICAL
→ melhor modelo disponível
```

Configuração:

```yaml
budget:

  daily_limit: 5

  monthly_limit: 100

  prefer_local: true

  premium_requires_reason: true
```

---

# 15. Provider Fallback

Se determinado provider falhar:

```text
Qwen / Ollama
     ↓
falha
     ↓
Groq
     ↓
falha
     ↓
OpenRouter
```

Outro exemplo:

```text
DeepSeek
↓
timeout
↓
modelo alternativo
```

O fallback deverá ser configurável.

---

# 16. Context Engine

O Harness deverá entender o projeto antes de responder.

Cada projeto possuirá:

```text
.project-ai/

PROJECT.md
ARCHITECTURE.md
SPECS.md
RULES.md
DECISIONS.md
TASKS.md
MEMORY.md
```

Esses arquivos representam o contexto persistente do projeto.

---

# 17. Context Builder

Antes de chamar uma LLM:

```text
User Prompt
+
Project Context
+
Relevant Files
+
Architecture
+
Rules
+
Task Context
+
Relevant Memory
=
Final Model Context
```

Nunca enviar todo o projeto indiscriminadamente.

Utilizar seleção inteligente de contexto.

---

# 18. RAG

Criar módulo próprio:

```text
rag/
│
├── ingestion/
├── chunking/
├── embeddings/
├── retrieval/
├── reranking/
└── citations/
```

Banco vetorial inicialmente opcional.

Possibilidades:

* Qdrant;
* pgvector;
* Chroma.

Preferência:

```text
PostgreSQL + pgvector
```

pela redução de complexidade operacional.

---

# 19. Memória

Separar:

## Session Memory

Conversa atual.

## Project Memory

Decisões e conhecimento do projeto.

## Operational Memory

Execuções anteriores.

## Long-term Memory

Conhecimento persistido seletivamente.

Nunca salvar automaticamente todo o conteúdo sem critérios.

---

# 20. Agent Engine

Criar agentes especializados.

V1:

```text
Planner Agent

Architect Agent

Developer Agent

Code Review Agent

QA Agent

Test Agent

Documentation Agent

Data Agent
```

---

# 21. Planner Agent

Responsável por:

* entender solicitação;
* decompor problema;
* identificar arquivos;
* gerar tarefas;
* estimar dependências;
* determinar agentes necessários.

Não deve alterar arquivos.

---

# 22. Architect Agent

Responsável por:

* arquitetura;
* design patterns;
* banco;
* APIs;
* escalabilidade;
* segurança;
* decisões técnicas.

---

# 23. Developer Agent

Pode:

* criar arquivos;
* editar;
* refatorar;
* executar tarefas autorizadas.

Toda alteração deverá gerar registro.

---

# 24. QA Agent

Responsável por:

* requisitos;
* critérios de aceitação;
* análise de risco;
* edge cases;
* regressão;
* inconsistências;
* bugs prováveis.

---

# 25. Test Agent

Responsável por:

* testes unitários;
* integração;
* API;
* contratos;
* smoke tests.

---

# 26. Judge / Evaluation Engine

Para tarefas críticas, múltiplas respostas poderão ser avaliadas.

```text
Claude / DeepSeek / Qwen
       │
       ▼
     JUDGE
       │
       ▼
Resposta consolidada
```

Não utilizar múltiplos modelos para tarefas triviais.

---

# 27. Tool Engine

O AI Harness deverá possuir ferramentas próprias.

V1:

```text
read_file
search_files
list_files
git_status
git_diff
git_log
run_tests
docker_status
project_info
```

Posteriormente:

```text
terminal
database
browser
API
deploy
```

---

# 28. Segurança

Ferramentas deverão possuir permissões.

Exemplo:

```yaml
tools:

  read_file:
    auto: true

  git_status:
    auto: true

  run_tests:
    confirm: false

  delete_file:
    confirm: true

  git_push:
    confirm: true

  deploy:
    confirm: true
```

Nunca permitir execução arbitrária sem política explícita.

---

# 29. OpenCode

OpenCode será tratado como uma ferramenta/agente externo.

Não será considerado uma LLM.

Possíveis funções:

```text
OpenCode Explore
OpenCode Plan
OpenCode Build
```

Integração futura:

```text
Hyperbrain
   ↓
Agent Router
   ↓
OpenCode
   ↓
Modelo configurado
```

---

# 30. Git Intelligence

Integrar ao contexto:

* branch atual;
* commits recentes;
* alterações não commitadas;
* arquivos modificados;
* diff;
* histórico relevante.

Exemplo:

```text
"Por que isso quebrou?"

Harness
↓
git diff
↓
commits
↓
arquivos relacionados
↓
LLM
```

---

# 31. Docker Intelligence

Permitir ao Hyperbrain visualizar:

* containers;
* serviços;
* portas;
* status;
* logs;
* health checks.

Comandos destrutivos deverão exigir permissão.

---

# 32. Observability

Registrar:

```text
task_id
project
agent
model
provider
tokens
latency
estimated_cost
fallback
status
error
quality_score
```

---

# 33. Dashboard de IA

Criar módulo:

```text
AI USAGE

Requests hoje

Modelos utilizados

Providers

Tokens

Custo diário

Custo mensal

Uso local

Uso cloud

Falhas

Fallbacks

Tempo médio

Taxa de sucesso
```

---

# 34. Tela Hyperbrain

Interface sugerida:

```text
┌──────────────────────────────────────┐
│ HYPERBRAIN                           │
│                                      │
│ Projeto: Dashboard Contábil          │
│ Branch: main                         │
│                                      │
│ Modelo                               │
│ [ AUTO ▼ ]                           │
│                                      │
│ Agente                               │
│ [ AUTO ▼ ]                           │
│                                      │
│ Pergunte ao projeto...               │
│                                      │
│                                      │
│ Contexto                             │
│ 14 arquivos                          │
│ 3 docs                               │
│ Git ativo                            │
│                                      │
└──────────────────────────────────────┘
```

---

# 35. Modo AUTO

Deve ser o modo padrão.

Usuário pergunta:

```text
"corrija esse erro"
```

Sistema decide:

```text
Agent
Model
Provider
Tools
Context
Fallback
```

---

# 36. Modo Manual

Permitir seleção:

```text
Model:
Qwen

Provider:
Ollama

Agent:
Developer
```

Útil para testes e comparação.

---

# 37. Estrutura Recomendada

```text
devcockpit/

apps/

  frontend/

  backend/

services/

  ai-harness/

      app/

        api/

        agents/

        router/

        providers/

        models/

        context/

        memory/

        rag/

        tools/

        evaluation/

        observability/

        security/

      configs/

      prompts/

      tests/

      Dockerfile

packages/

  shared/

docs/

docker-compose.yml
```

---

# 38. API

Endpoints iniciais:

```text
POST /ai/chat

POST /ai/tasks

GET /ai/tasks/{id}

GET /ai/models

GET /ai/providers

GET /ai/agents

GET /ai/usage

GET /ai/health
```

---

# 39. Endpoint Chat

Entrada:

```json
{
  "project_id": "project-x",
  "message": "analise essa função",
  "agent": "auto",
  "model": "auto"
}
```

Retorno:

```json
{
  "task_id": "...",
  "agent": "code_review",
  "model": "qwen",
  "provider": "ollama",
  "response": "...",
  "cost": 0
}
```

---

# 40. Streaming

Implementar respostas por streaming usando:

```text
Server-Sent Events

ou

WebSocket
```

Preferência inicial:

```text
SSE
```

por simplicidade.

---

# 41. Banco de Dados

Entidades:

```text
projects

ai_tasks

ai_messages

agents

providers

models

model_capabilities

tool_executions

usage_records

project_memories

documents

rag_chunks
```

---

# 42. Segurança das APIs

Nunca armazenar keys:

```text
frontend
localStorage
cookies
Git
```

Utilizar:

```text
environment variables

ou

secret manager
```

---

# 43. MVP

O MVP deve possuir somente:

1. Hyperbrain Chat;
2. Project Context;
3. Ollama;
4. DeepSeek;
5. Model Registry;
6. Provider Registry;
7. Model Router;
8. Cost Router básico;
9. fallback;
10. logs;
11. consumo;
12. Code Review Agent;
13. Developer Agent;
14. QA Agent;
15. integração Git somente leitura.

NÃO implementar inicialmente:

* swarm complexo;
* dezenas de agentes;
* autonomia irrestrita;
* deploy automático;
* terminal irrestrito;
* memória excessivamente sofisticada.

---

# 44. Fase 2

Adicionar:

* RAG;
* embeddings;
* memória;
* OpenCode;
* Groq;
* OpenRouter;
* agentes adicionais;
* execução de testes;
* Docker Intelligence.

---

# 45. Fase 3

Adicionar:

* Multi-Agent;
* Judge;
* execução paralela;
* benchmark;
* qualidade automática;
* roteamento adaptativo;
* modelos self-hosted via vLLM.

---

# 46. Fase 4

Criar inteligência operacional.

O sistema passa a aprender:

```text
Para Python debugging:

Qwen resolveu 73%
DeepSeek resolveu 91%

Custo médio:
Qwen = R$0
DeepSeek = R$0,03
```

O Router poderá então tomar decisões baseadas no histórico real.

---

# 47. Métricas de Produto

Monitorar:

```text
% tarefas locais

custo por tarefa

custo por projeto

taxa de sucesso

fallback rate

latência

taxa de retrabalho

quantidade de bugs encontrados

test success

agent success rate
```

---

# 48. Meta Econômica

Meta inicial:

```text
70–80% das tarefas
→ local ou baixo custo

15–25%
→ APIs econômicas

<10%
→ premium
```

Não tratar os percentuais como regras rígidas.

Deverão ser metas observáveis.

---

# 49. Critérios de Aceitação do MVP

O MVP estará funcional quando:

* DevCockpit conversar com Harness;
* projeto atual for identificado;
* contexto for carregado;
* pelo menos um modelo local funcionar;
* DeepSeek funcionar opcionalmente;
* usuário puder escolher AUTO ou manual;
* Router escolher modelo;
* fallback funcionar;
* logs forem persistidos;
* consumo puder ser visualizado;
* API keys nunca forem expostas;
* agentes puderem analisar código;
* Git puder ser consultado;
* todas as funções principais tiverem testes.

---

# 50. Princípios Técnicos Obrigatórios

## Provider Agnostic

Nenhum modelo deve dominar a arquitetura.

## Local First

Utilizar recursos locais sempre que suficiente.

## Cost Aware

Toda execução deve considerar custo.

## Context Aware

Nenhuma análise significativa deve ocorrer sem contexto adequado.

## Secure by Default

Ações críticas requerem autorização.

## Observable

Toda execução relevante deve ser rastreável.

## Testable

Routers e agentes precisam ser testáveis isoladamente.

## Modular

Cada módulo precisa ser substituível.

## Spec-Driven

Não implementar funcionalidades sem especificação.

---

# 51. Resultado Esperado

Ao final, o DevCockpit deverá permitir algo como:

```text
Usuário:

"Hyperbrain, revise o backend antes de eu
começar a nova funcionalidade."

Sistema:

Projeto encontrado.

Contexto carregado.

Git analisado.

Agente:
Code Review

Modelo:
Qwen

Provider:
Ollama

Custo:
R$0

12 arquivos analisados.

Resultado:

3 problemas importantes
4 melhorias
2 riscos de arquitetura
1 possível regressão

Próxima ação recomendada:
...
```

Esse será o comportamento fundamental do AI Harness.
