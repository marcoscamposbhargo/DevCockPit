# Orquestração e especialistas

> **Status: proposta.**

## O que um "especialista" é aqui

Não é um agente autônomo com laço próprio. É um **perfil**: instrução de
sistema + conjunto de ferramentas permitidas + camadas de contexto preferidas.
Um processo, um modelo, vários chapéus.

A escolha é deliberada. Agentes independentes conversando entre si multiplicam
custo, latência e modos de falha — e o ganho, num painel de um usuário só,
aparece bem depois do custo.

```python
@dataclass(frozen=True)
class Specialist:
    key: str                  # "fullstack", "data", "devops", ...
    label: str
    prompt_file: str          # prompts/fullstack.md
    tools: frozenset[str]     # subconjunto do registro de ferramentas
    context_layers: tuple     # o que o Context Engine prioriza
```

## Os sete perfis

| Perfil | Serve para | Ferramentas típicas |
|--------|-----------|--------------------|
| **Full Stack** | arquitetura, API, backend, frontend, integração | git, files.read, project, memory |
| **Data Analyst** | CSV/Excel, exploração, indicadores, gráficos | files.read, analytics |
| **Data Engineering** | pipeline, ETL, schema, qualidade | files.read, docker.status |
| **UX/UI** | interface, hierarquia, responsividade, acessibilidade | files.read |
| **DevOps** | Docker, ambiente, portas, deploy, logs | docker.*, ports.map, health, env.* |
| **QA** | teste, bug, regressão | files.read, git, activity.read |
| **Documentation** | README, ADR, changelog, API | files.read, git.commits, memory.write |

Cada um vive num arquivo de prompt versionado em `services/ai/prompts/`. Prompt
é código: entra em revisão, muda com commit, tem histórico.

## O orquestrador

```
pergunta
   ↓
regras determinísticas          "container", "compose", "porta"   → DevOps
(palavra-chave + contexto)      "planilha", "csv", "gráfico"      → Data
   ↓                            "teste", "falhou", "regressão"    → QA
ambíguo?
   ↓ sim
classificação pelo modelo       chamada curta e barata, só para rotear
   ↓
1 ou 2 especialistas
```

Regra primeiro, modelo depois. A maioria das perguntas de um painel de
desenvolvimento cai em vocabulário estreito, e resolver por regra é instantâneo
e gratuito. O modelo entra onde a regra empata.

**No máximo dois perfis por pergunta.** "Analise esta planilha" chama Data
Analyst + Data Engineering; "meu container não sobe" chama DevOps + Full Stack.
Três ou mais viram resposta longa e sem dono.

Quando dois perfis respondem, a composição é sequencial e não paralela: o
segundo recebe a resposta do primeiro como contexto. Mais barato que duas
chamadas independentes e um merge, e o resultado tem uma voz só.

## Ações propostas

O modelo pode propor ação, nunca executá-la. O formato é fechado:

```json
{
  "action": "docker.up",
  "project_id": "dashboard-contabil",
  "params": { "services": ["db"] },
  "reason": "o backend depende do Postgres e nenhum container está de pé",
  "class": "SENSITIVE_WRITE"
}
```

O servidor:

1. confere se `action` está no registro de ferramentas do especialista ativo;
2. valida `params` com os mesmos validadores de hoje (path, inteiro, enum,
   serviço do Compose);
3. classifica (READ / SAFE WRITE / SENSITIVE WRITE / DESTRUCTIVE);
4. executa direto se READ; pede confirmação nas demais;
5. registra em `activity_log` com `actor="ai"` e `reason`.

Ação fora do registro nunca chega ao passo 4: vira `403 ACTION_NOT_ALLOWED` e
`DENIED` na auditoria — o sinal mais importante do sistema, segundo o
`docs/07-security-model.md`, e agora também o sinal de modelo alucinando.

## Command palette

Os comandos do prompt de visão (`/start-day`, `/plan`, `/find-bugs`…) são
**atalhos para intenção + especialista**, não código separado:

```python
COMMANDS = {
    "start-day":   Command(intent="daily_briefing",  specialist=None),
    "start-session": Command(intent="session_start", specialist=None),
    "status":      Command(intent="project_status",  specialist=None),
    "plan":        Command(intent="planning",        specialist="fullstack"),
    "find-bugs":   Command(intent="bug_hunt",        specialist="qa"),
    "review-code": Command(intent="code_review",     specialist="fullstack"),
    "analyze-data":Command(intent="data_analysis",   specialist="data_analyst"),
    "deploy-check":Command(intent="deploy_readiness",specialist="devops"),
    "end-session": Command(intent="session_end",     specialist=None),
}
```

Um dicionário, não uma hierarquia de classes. Comando novo é uma linha.

Três deles — `start-day`, `start-session`, `status` — **funcionam sem modelo
nenhum**: são consulta e formatação de dado que o painel já tem. É o que
garante valor no dia em que a chave de API não estiver configurada, e é por
isso que eles vêm primeiro no plano de implementação.
