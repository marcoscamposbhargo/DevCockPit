# Segurança do Cockpit AI

> **Status: proposta.** Extensão de `docs/07-security-model.md`, não substituição.

## A mudança de natureza

Hoje o DevCockpit é **inteiramente local**: escuta só em `127.0.0.1`, não faz
requisição de saída para lugar nenhum, e o pior caso de vazamento é alguém com
acesso físico à máquina.

Falar com um provedor de IA quebra isso. Passa a existir **dado do usuário
saindo da máquina**: nome de projeto, caminho, trecho de código, log de
container, mensagem de commit. Isso não é uma feature a mais; é uma classe de
risco nova, e precisa ser tratada como tal.

## Defesas novas (numeração continua a de `07-security-model.md`)

### D-A1 — Nada sai sem consentimento explícito

A IA vem **desligada**. Ligar exige duas coisas: configurar um provedor e
aceitar, uma vez, um aviso que diz em português o que passa a sair da máquina.
O consentimento fica gravado com data.

Por projeto, um segundo interruptor: projeto pode ser marcado como
`ai_enabled = false` e nunca ter conteúdo enviado. Cliente, contrato, dado
sensível — a decisão é do usuário, projeto a projeto.

### D-A2 — Redação antes do envio

Todo bloco de contexto passa por um filtro antes de virar mensagem:

| O que | Ação |
|-------|------|
| `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json` | **nunca lidos** |
| linhas com `API_KEY=`, `SECRET`, `PASSWORD`, `TOKEN`, `Bearer ` | valor substituído por `[REDIGIDO]` |
| string com formato de chave (`sk-`, `ghp_`, `AKIA`) | `[REDIGIDO]` |
| caminho absoluto do usuário | mantido — é o que identifica o projeto |

O painel já tem `redact_argv` em `app/core/logging.py` para a auditoria. A
mesma ideia, mesmo lugar, agora também na saída para o modelo.

### D-A3 — A IA não amplia o que a API pode fazer

Nenhuma ação nova entra na allowlist por causa do agente. O modelo escolhe
entre ações que a interface já podia disparar, com os mesmos validadores. Um
teste automatizado garante que o conjunto de ferramentas do agente é
**subconjunto** do registro de ações — se alguém acrescentar uma ferramenta sem
ação correspondente, a suíte reprova.

### D-A4 — Conteúdo lido é dado, não instrução

O painel varre 28 projetos, e nem todo README foi escrito pelo usuário. Texto
vindo de arquivo entra delimitado e rotulado como não confiável, e o modelo é
instruído a nunca tratá-lo como ordem. A defesa final não é o prompt: é a
confirmação humana antes de qualquer escrita, e a allowlist depois dela.

### D-A5 — Chave de API nunca no banco nem na API

Chave vem de variável de ambiente (`.env` ao lado do executável), como toda
configuração sensível. Não é gravada no SQLite, não aparece em nenhuma resposta
HTTP, não é editável pela interface — mesma regra do `roots.yml` (decisão
D-10). A tela mostra no máximo "provedor configurado: sim/não".

### D-A6 — Teto de gasto

Custo é risco. Três limites em `Settings`:

```
DEVCOCKPIT_AI_MAX_CONTEXT_TOKENS   teto por chamada
DEVCOCKPIT_AI_DAILY_TOKEN_BUDGET   teto por dia; ao estourar, a IA recusa
DEVCOCKPIT_AI_MAX_TOOL_CALLS       teto de ferramentas por pergunta (laço)
```

O gasto acumulado aparece na tela. Ferramenta que gasta sem mostrar quanto é
ferramenta que um dia assusta.

## Classificação de operações

| Classe | Exemplos | Quem autoriza |
|--------|----------|---------------|
| **READ** | ler projeto, Git, portas, saúde, logs, arquivo | automático |
| **SAFE WRITE** | escrever memória, encerrar sessão, criar tarefa | automático, reversível, auditado |
| **SENSITIVE WRITE** | `compose up/down`, subir/parar servidor, trocar porta cadastrada | **confirmação humana** |
| **DESTRUCTIVE** | apagar projeto do cadastro, `compose down -v`, alterar arquivo do projeto, `git push` | **fora do alcance da IA**, ponto |

A quarta linha é a mais importante. A tentação será relaxá-la ("só desta vez,
com confirmação dupla"). O momento de decidir isso é agora, com a cabeça fria:
o painel nunca teve `-v` alcançável por nenhum caminho (D-16), e o agente não é
motivo para abrir a primeira exceção.

## Auditoria

`activity_log` ganha três campos: `actor` (`user` \| `ai`), `agent` (perfil) e
`reason` (por que o modelo propôs). Com isso, a pergunta "o que o agente
modificou ontem?" é uma consulta na tela de Atividade que já existe — sem
tabela nova, sem tela nova.

Toda chamada ao provedor é registrada em `ai_message`: modelo, tokens de
entrada e saída, custo estimado, duração, e o resumo do contexto enviado (não o
conteúdo inteiro — que pode ser grande e conter código).

## Modo local

`LocalProvider` (Ollama, LM Studio) existe por um motivo de segurança, não de
economia: para quem não pode mandar código para fora, ele é a única forma de
usar o Cockpit AI. A arquitetura de provedor garante que essa escolha não
mexa em nada além da configuração.

## Testes obrigatórios

Na mesma linha dos testes de segurança que já existem (`test_security_guards.py`):

1. ferramenta do agente fora do registro de ações → reprova o build;
2. `.env` e chaves privadas nunca aparecem no contexto montado;
3. padrão de segredo em arquivo lido sai redigido;
4. ação SENSITIVE proposta pela IA sem confirmação → não executa;
5. ação DESTRUCTIVE proposta pela IA → recusada e auditada como `DENIED`;
6. projeto com `ai_enabled=false` → nada dele entra em contexto nenhum;
7. estouro do orçamento diário → recusa com mensagem, sem chamada ao provedor.
