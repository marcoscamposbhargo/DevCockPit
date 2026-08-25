# Cockpit AI — Arquitetura

> **Status: proposta.**

## Onde o módulo encaixa

O DevCockpit tem camadas fixas (`docs/04-system-architecture.md`):

```
rota HTTP  →  serviço  →  repositório  →  SQLite
                  ↓
              adapter  →  CommandRunner  →  processo externo
```

O Cockpit AI entra como **mais um domínio**, não como uma aplicação paralela:

```
app/
├── api/routes/ai.py            rotas do agente (chat, sessão, ações)
├── schemas/ai.py               contratos
├── models/ai.py                tabelas novas
├── repositories/
│   ├── session_repository.py
│   └── memory_repository.py
└── services/ai/
    ├── orchestrator.py         escolhe especialista e ferramentas
    ├── context_engine.py       monta o contexto (e o limita)
    ├── memory_service.py       lê e escreve memória
    ├── session_service.py      start / end session
    ├── specialists.py          perfis (prompt + ferramentas permitidas)
    ├── tools.py                ponte para os serviços existentes
    ├── providers/
    │   ├── base.py             interface AIProvider
    │   ├── anthropic.py
    │   ├── openai.py
    │   └── local.py            Ollama / LM Studio
    └── prompts/                arquivos .md versionados
```

Nada disso é diretório novo de topo. A estrutura sugerida no prompt de visão
(`cockpit-ai/` com `orchestrator/`, `context/`, `memory/`…) foi **adaptada**:
criar uma segunda árvore ao lado de `app/` duplicaria configuração, sessão de
banco, auditoria e testes.

## O ponto crítico: a IA e o ADR-003

O ADR-003 existe porque o painel executa comandos na máquina do desenvolvedor,
disparados por HTTP. A regra é: **o cliente manda identificador de ação, nunca
comando**. Um modelo de linguagem é, para efeito de segurança, um cliente
não confiável — pior que o browser, porque pode ser induzido pelo conteúdo que
lê (um README malicioso dentro de um projeto varrido é injeção de prompt).

Portanto:

```
        ERRADO                              CERTO
  modelo devolve texto              modelo devolve
  "docker compose up -d"            { "action": "docker.up",
        ↓                             "project_id": "x",
     shell                            "services": ["web"] }
                                            ↓
                                    mesma validação de sempre
                                            ↓
                                    allowlist → CommandRunner
```

O agente **não ganha nenhuma capacidade nova de execução**. Ele ganha o direito
de pedir o que a interface já podia pedir. Ação fora do registro devolve
`403 ACTION_NOT_ALLOWED` e grava `DENIED` — o mesmo caminho de hoje, agora com
`actor="ai"` na auditoria.

## Ferramentas (tools) = serviços que já existem

O agente não fala com o sistema operacional. Ele fala com os serviços do painel:

| Ferramenta | Serviço existente | Classe |
|-----------|-------------------|--------|
| `project.read` | `ProjectService.get` | READ |
| `project.list` | `ProjectService.list` | READ |
| `git.status` / `git.commits` | `GitService` | READ |
| `docker.status` / `docker.logs` | `DockerService` | READ |
| `health.check` | `HealthService` | READ |
| `ports.map` | `PortDiscoveryService` | READ |
| `analytics.read` | `AnalyticsService` | READ |
| `activity.read` | `ActivityService.list` | READ |
| `files.read` | novo, restrito à allowlist de roots | READ |
| `memory.write` | `MemoryService` | SAFE WRITE |
| `session.end` | `SessionService` | SAFE WRITE |
| `env.up` / `env.down` | `EnvironmentService` | SENSITIVE WRITE |
| `docker.down` | `DockerService` | SENSITIVE WRITE |

Escrita em arquivo de projeto, `git push`, migração e deploy **não são
ferramentas**. Ficam fora por decisão, não por falta de tempo: quem edita
código é o VS Code / Claude Code, e o Cockpit é o centro de comando, não o
editor (`docs/00-product-vision.md` já veta editor embutido).

## Fluxo de uma pergunta

```
  usuário pergunta
        ↓
  detecção de intenção        (regra + palavra-chave; modelo só se ambíguo)
        ↓
  seleção de especialista     (orchestrator)
        ↓
  montagem de contexto        (context_engine: memória + fatos + trechos)
        ↓
  chamada ao provedor         (provider abstraction)
        ↓
  resposta ou pedido de ação
        ↓                          ↘
  texto para a tela          ação proposta → confirmação humana → allowlist
        ↓                                                            ↓
  registro em ai_message                                     activity_log
```

## Provider abstraction

```python
class AIProvider(Protocol):
    name: str
    def complete(self, request: AIRequest) -> AIResponse: ...
    def stream(self, request: AIRequest) -> Iterator[AIChunk]: ...
    def count_tokens(self, text: str) -> int: ...
```

`AIRequest` carrega mensagens, ferramentas disponíveis e teto de tokens.
`AIResponse` carrega texto, ações propostas, tokens gastos e custo estimado.

Três implementações previstas: Anthropic, OpenAI e local (Ollama). A escolha
vive em `Settings` (`DEVCOCKPIT_AI_PROVIDER`), como toda configuração —
nenhuma chave em código, nenhuma no banco.

**O painel precisa continuar funcionando com provedor nenhum configurado.** Sem
chave, a aba de IA explica o que falta e o resto do sistema não muda. É a mesma
regra do Docker desligado: ausência de dependência externa nunca vira erro de
tela (NFR-060).

## Streaming e jobs

Resposta de modelo demora segundos. O painel já tem duas peças para isso:

- **SSE**, usado pelo console de job (`app/api/routes/jobs.py`) — serve para o
  chat token a token;
- **JobManager**, para trabalho longo com exclusão mútua por chave — serve para
  "analisar projeto inteiro", que pode levar minutos e não pode rodar duas
  vezes em paralelo no mesmo projeto.

Nada novo precisa ser inventado para nenhum dos dois.

## Frontend

Uma página nova (`frontend/js/pages/ai.js`) e um painel dentro do projeto
(`ai-panel.js`), seguindo o que já existe: ES modules, sem build, `el()` para
DOM, `api.js` como único ponto de acesso. O chat reusa o padrão de stream do
console de job.

## O que muda no sistema atual

| Arquivo | Mudança | Risco |
|---------|---------|-------|
| `app/main.py` | registra rotas de IA | baixo |
| `app/core/config.py` | chaves de provedor, teto de tokens, custo | baixo |
| `app/runner/allowlist.py` | nenhuma ação nova; só `actor` na auditoria | baixo |
| `app/models/` | tabelas novas, migração aditiva | baixo |
| `app/services/activity_service.py` | campo `actor` (`user` \| `ai`) | médio — toca o que já funciona |
| `frontend/` | página e painel novos | baixo |

Nenhuma tabela existente perde coluna. Nenhuma rota existente muda de contrato.
