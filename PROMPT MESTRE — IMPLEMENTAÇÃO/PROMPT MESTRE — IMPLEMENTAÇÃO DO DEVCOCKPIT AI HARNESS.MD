# PROMPT MESTRE — IMPLEMENTAÇÃO DO DEVCOCKPIT AI HARNESS / HYPERBRAIN

Você atuará como:

* Principal Software Architect;
* Staff Backend Engineer;
* AI Platform Engineer;
* Python Engineer;
* DevOps Engineer;
* QA Engineer;
* Security Engineer.

Sua missão é implementar no projeto existente **DevCockpit** uma nova infraestrutura denominada:

# DEVCOCKPIT AI HARNESS / HYPERBRAIN

Não trate esta tarefa como implementação de um simples chatbot.

Estamos construindo uma infraestrutura modular para utilização de múltiplos modelos de inteligência artificial, agentes, ferramentas, RAG, contexto de projetos e roteamento inteligente.

---

# REGRA Nº 1

ANTES DE ESCREVER CÓDIGO:

analise integralmente o projeto existente.

Você deve identificar:

* stack;
* estrutura;
* arquitetura;
* frontend;
* backend;
* banco;
* autenticação;
* APIs;
* Docker;
* Git;
* padrões existentes;
* convenções;
* serviços;
* dependências.

Não substitua partes existentes sem necessidade.

Não reconstrua o DevCockpit.

A implementação deverá ser incremental.

---

# REGRA Nº 2 — SPEC DRIVEN DEVELOPMENT

Não implemente diretamente.

Primeiro crie:

```text
docs/ai-harness/

00-overview.md
01-current-system-analysis.md
02-requirements.md
03-architecture.md
04-data-model.md
05-api-contracts.md
06-provider-system.md
07-model-router.md
08-agent-system.md
09-context-engine.md
10-security.md
11-observability.md
12-testing-strategy.md
13-implementation-plan.md
14-decisions.md
```

Só após a arquitetura estar consistente deverá começar a implementação.

---

# OBJETIVO

Transformar o Hyperbrain na camada de inteligência operacional do DevCockpit.

Arquitetura:

```text
DEVCOCKPIT

      ↓

HYPERBRAIN

      ↓

AI HARNESS

 ├── Task Classifier
 ├── Agent Router
 ├── Model Router
 ├── Provider Router
 ├── Cost Router
 ├── Context Engine
 ├── Memory
 ├── RAG
 ├── Tool Engine
 ├── Evaluation
 ├── Fallback
 └── Observability

      ↓

PROVIDERS
```

---

# PRINCÍPIO ARQUITETURAL

MODELS e PROVIDERS são conceitos diferentes.

Exemplo:

```text
MODEL
Qwen

PROVIDER
Ollama
```

Outro:

```text
MODEL
Qwen

PROVIDER
Groq
```

O restante da aplicação não deverá saber qual SDK está sendo utilizado.

---

# IMPLEMENTAR PROVIDER INTERFACE

Criar abstração equivalente a:

```python
class BaseLLMProvider:

    async def generate(...):
        pass

    async def stream(...):
        pass

    async def healthcheck(...):
        pass

    async def list_models(...):
        pass
```

Todos os providers deverão implementar o mesmo contrato.

---

# PROVIDERS MVP

Implementar inicialmente:

```text
OllamaProvider

DeepSeekProvider
```

Preparar interfaces para:

```text
OpenAIProvider
AnthropicProvider
GeminiProvider
GroqProvider
OpenRouterProvider
MistralProvider
```

Não obrigar APIs pagas para executar o sistema.

O sistema deve funcionar apenas com Ollama.

---

# MODEL REGISTRY

Criar Model Registry central.

Não espalhar nomes de modelos pelo código.

Exemplo:

```yaml
models:

  local_coder:

    model: qwen

    capabilities:

      - coding
      - debugging
      - documentation

    preferred_providers:

      - ollama
```

---

# PROVIDER REGISTRY

Criar registro:

```yaml
providers:

  ollama:

    enabled: true

    type: local

  deepseek:

    enabled: false

    type: cloud
```

---

# ROUTING ENGINE

Implementar:

```text
TaskClassifier

ModelRouter

ProviderRouter

CostRouter

FallbackEngine
```

Não criar lógica gigantesca em uma única classe.

---

# TASK CLASSIFIER

Deve classificar:

```text
simple_task

coding

debugging

architecture

documentation

testing

qa

data_analysis

planning

refactoring

rag_query
```

Deve produzir:

```json
{
  "task_type": "debugging",
  "complexity": 72,
  "privacy": "internal",
  "tools_required": true
}
```

O primeiro classificador pode ser baseado em regras.

Não desperdiçar outra LLM somente para classificar tarefas simples.

---

# ROUTER

Implementar uma política inicialmente determinística.

Exemplo:

```text
LOW
→ local

MEDIUM
→ melhor local

HIGH
→ cloud econômico se disponível

CRITICAL
→ melhor provider autorizado
```

Não criar sistema de machine learning para isso nesta fase.

---

# FALLBACK

Implementar fallback real.

Fluxo:

```text
Provider A

timeout

↓

Provider B

erro

↓

Provider C
```

Registrar todas as tentativas.

Evitar loops.

Definir máximo de tentativas.

---

# COST AWARENESS

Toda execução deverá gerar registro:

```text
provider

model

input tokens

output tokens

estimated cost

latency
```

Quando não for possível calcular custo exato, marcar:

```text
estimated_cost = unknown
```

Nunca inventar valor.

---

# CONTEXT ENGINE

Criar um Context Builder.

Entrada:

```text
project_id

task

prompt
```

O contexto deverá considerar:

```text
PROJECT.md

ARCHITECTURE.md

SPECS.md

RULES.md

DECISIONS.md

TASKS.md

MEMORY.md
```

Não enviar todo o repositório para a LLM.

Selecionar arquivos relevantes.

---

# PROJECT AI DIRECTORY

Adicionar suporte a:

```text
.project-ai/
```

Estrutura:

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

Se a pasta não existir:

não falhar.

O Context Engine deve trabalhar com informações disponíveis.

---

# AGENT ENGINE

Criar abstração:

```python
class BaseAgent:

    name

    role

    allowed_tools

    preferred_capabilities

    async execute(...):
        ...
```

Implementar MVP:

```text
DeveloperAgent

CodeReviewAgent

QAAgent
```

---

# CODE REVIEW AGENT

Deverá:

* analisar implementação;
* encontrar bugs;
* identificar riscos;
* detectar duplicação;
* sugerir melhoria;
* apontar regressões;
* avaliar segurança básica.

Não alterar código automaticamente.

---

# QA AGENT

Deverá avaliar:

```text
requirement coverage

acceptance criteria

edge cases

regression risks

test gaps
```

---

# DEVELOPER AGENT

Pode propor alterações.

Na primeira versão:

mudanças destrutivas devem continuar sob controle do usuário.

---

# TOOL SYSTEM

Criar interface comum.

MVP:

```text
read_file

list_files

search_files

git_status

git_diff

git_log

project_info
```

Todas as ferramentas devem:

* validar inputs;
* possuir timeout;
* registrar execução;
* retornar erro estruturado.

---

# NÃO CRIAR TERMINAL IRRESTRITO NO MVP

Não permita que a IA execute livremente:

```bash
rm
git push
git reset --hard
docker system prune
```

ou equivalentes.

Ferramentas críticas serão implementadas posteriormente.

---

# GIT CONTEXT

Implementar leitura de:

```text
branch

status

diff

recent commits
```

Incluir informação no contexto somente quando relevante.

---

# OBSERVABILITY

Criar armazenamento para:

```text
ai_task

ai_run

provider_attempt

tool_execution

usage_record
```

Cada execução deve possuir:

```text
correlation_id
```

permitindo acompanhar:

```text
request
→ agent
→ router
→ provider
→ tools
→ response
```

---

# DATABASE

Antes de criar tabelas:

analise o banco existente.

Não introduza outro banco se não houver necessidade.

Entidades conceituais:

```text
ai_tasks

ai_messages

ai_runs

ai_models

ai_providers

ai_usage

ai_tool_executions
```

---

# API

Criar inicialmente:

```text
POST /api/ai/chat

GET /api/ai/models

GET /api/ai/providers

GET /api/ai/agents

GET /api/ai/usage

GET /api/ai/health
```

Respeitar padrões existentes do projeto.

---

# STREAMING

Avaliar estrutura atual.

Preferência:

```text
Server-Sent Events
```

Não introduzir WebSocket se SSE resolver o problema adequadamente.

---

# FRONTEND

Não redesenhe o DevCockpit inteiro.

Integre o Hyperbrain preservando o design existente.

Criar interface contendo:

```text
Project

Agent

Model

Provider

AUTO mode

Chat

Context indicator

Cost indicator
```

Modo padrão:

```text
Agent: AUTO

Model: AUTO

Provider: AUTO
```

---

# TELA DE CONFIGURAÇÕES

Adicionar:

```text
AI Providers
```

Mostrar:

```text
Ollama
Connected

DeepSeek
Not configured

OpenAI
Disabled

Anthropic
Disabled
```

Nunca mostrar API keys.

---

# SEGREDOS

Não armazenar API keys:

```text
database plain text

frontend

localStorage

source code

Git
```

Usar o mecanismo de secrets/environment adotado pelo projeto.

---

# OLLAMA

Deve ser o provider padrão do MVP.

O sistema deverá:

1. detectar disponibilidade;
2. executar healthcheck;
3. listar modelos;
4. enviar requests;
5. lidar com timeout;
6. lidar com modelo inexistente.

A aplicação deve continuar funcional mesmo quando Ollama estiver offline.

---

# DEEPSEEK

Adicionar como cloud provider opcional.

Só habilitar quando:

```text
DEEPSEEK_API_KEY
```

estiver configurada.

Ausência de chave não pode impedir o DevCockpit de iniciar.

---

# TESTES

Implementar:

## Unit

```text
router

task classifier

provider registry

model registry

fallback

cost calculation

context builder
```

## Integration

```text
FastAPI

database

mock provider

tool engine
```

Não depender de uma API real para rodar a suíte de testes.

Criar:

```text
FakeLLMProvider
```

---

# MOCK PROVIDER

Deve permitir:

```text
successful response

timeout

rate limit

provider error

malformed response
```

para testar fallback.

---

# DOCKER

Preservar o Docker Compose atual.

Adicionar serviços apenas quando necessário.

Se Ollama já estiver instalado no host, suportar comunicação host → container.

Documentar claramente.

---

# LOGGING

Nunca registrar:

* secrets;
* API keys;
* passwords.

Cuidado com prompts contendo informações confidenciais.

Criar opção para mascaramento.

---

# RAG

Não implementar RAG completo no primeiro commit.

Preparar interfaces.

Primeiro estabilizar:

```text
provider
router
agents
context
observability
```

Posteriormente:

```text
RAG
memory
multi-agent
judge
```

---

# ORDEM DE IMPLEMENTAÇÃO

## Fase 0

Auditoria do projeto.

## Fase 1

Documentação e ADRs.

## Fase 2

Provider abstraction.

## Fase 3

Ollama.

## Fase 4

Model/Provider Registry.

## Fase 5

Task Classifier.

## Fase 6

Model Router.

## Fase 7

Fallback.

## Fase 8

Context Engine.

## Fase 9

Agents.

## Fase 10

API.

## Fase 11

Frontend.

## Fase 12

Observability.

## Fase 13

DeepSeek.

## Fase 14

QA completo.

---

# EM CADA FASE

Antes:

```text
PLAN
```

Depois:

```text
IMPLEMENT
```

Depois:

```text
TEST
```

Depois:

```text
REVIEW
```

Depois:

```text
DOCUMENT
```

Não continuar se a etapa anterior introduzir falhas relevantes.

---

# PROIBIÇÕES

NÃO:

* reescrever o DevCockpit;
* trocar stack sem justificativa;
* criar microserviços desnecessários;
* adicionar frameworks por entusiasmo;
* acoplar código à OpenAI;
* acoplar código à Anthropic;
* colocar API key no frontend;
* criar agentes autônomos sem limites;
* executar comandos destrutivos;
* remover features existentes;
* duplicar serviços existentes;
* criar abstrações desnecessariamente complexas.

---

# YAGNI

Não implemente uma infraestrutura gigantesca para recursos ainda não necessários.

Prepare contratos.

Implemente apenas o necessário para o estágio atual.

---

# SOLID + CLEAN ARCHITECTURE

Aplicar quando realmente melhorar:

* testabilidade;
* modularidade;
* substituição de providers;
* manutenção.

Evitar arquitetura cerimonial.

---

# PRIMEIRA RESPOSTA ESPERADA

NÃO comece alterando arquivos.

Primeiro apresente:

## 1. Current System Analysis

O que existe hoje.

## 2. Integration Points

Onde o Harness deverá entrar.

## 3. Risks

O que pode quebrar.

## 4. Proposed Architecture

Arquitetura recomendada.

## 5. Files To Create

Novos arquivos.

## 6. Files To Modify

Arquivos existentes.

## 7. Database Impact

Impactos de dados.

## 8. Dependency Impact

Novas dependências.

## 9. Implementation Sequence

Ordem de implementação.

## 10. Acceptance Criteria

Como saberemos que funcionou.

Após isso:

crie as especificações dentro de:

```text
docs/ai-harness/
```

e somente então inicie a implementação incremental.

---

# DEFINIÇÃO DE SUCESSO

A implementação estará correta quando for possível entrar no DevCockpit e executar:

```text
"Revise este projeto e encontre problemas."
```

e o sistema:

1. identificar o projeto;
2. coletar contexto;
3. identificar a tarefa;
4. selecionar agente;
5. selecionar modelo;
6. selecionar provider;
7. executar ferramentas necessárias;
8. chamar a LLM;
9. lidar com fallback;
10. retornar resultado;
11. registrar execução;
12. registrar custo;
13. não expor secrets.

---

# NORTE DO PROJETO

Não estamos construindo:

> um chat que chama várias APIs.

Estamos construindo:

> uma camada própria de inteligência e orquestração para o DevCockpit, capaz de operar diferentes modelos, agentes e ferramentas com contexto de projeto, baixo custo, observabilidade e independência de fornecedor.

Preserve esse princípio em todas as decisões de arquitetura.

