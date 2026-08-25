# Cockpit AI — documentação da proposta

Incremento proposto ao DevCockpit: uma camada de contexto, memória e assistência
sobre o painel de operação que já existe.

**Nada aqui está implementado.** São documentos de projeto, escritos antes do
código, aguardando autorização (`AI_IMPLEMENTATION_PLAN.md`).

| Doc | Assunto |
|-----|---------|
| [COCKPIT_AI_OVERVIEW](COCKPIT_AI_OVERVIEW.md) | o que se quer, o que já existe, o que falta |
| [COCKPIT_AI_ARCHITECTURE](COCKPIT_AI_ARCHITECTURE.md) | módulos, integração, provedores, o encontro com o ADR-003 |
| [CONTEXT_ENGINE](CONTEXT_ENGINE.md) | montagem e limitação do contexto |
| [MEMORY_ARCHITECTURE](MEMORY_ARCHITECTURE.md) | memória global, de projeto e de sessão |
| [AGENT_ORCHESTRATION](AGENT_ORCHESTRATION.md) | especialistas, roteamento, comandos |
| [AI_SECURITY](AI_SECURITY.md) | dado que sai da máquina, segredos, classes de operação |
| [AI_DATABASE_SCHEMA](AI_DATABASE_SCHEMA.md) | cinco tabelas novas e três colunas |
| [AI_IMPLEMENTATION_PLAN](AI_IMPLEMENTATION_PLAN.md) | cinco fases, com critério de saída |
| [AI_ROADMAP](AI_ROADMAP.md) | ordem, o que fica fora, sinais de parar |

## Os três achados que moldaram a proposta

1. **A camada de gestão não existe.** O painel sabe de operação (portas,
   Docker, saúde, Git); não sabe de tarefa, backlog, roadmap nem sessão. Sem
   isso, "memória" não teria onde se ancorar.
2. **A IA é um cliente não confiável.** O ADR-003 diz que nenhum comando vem do
   cliente. O agente propõe identificadores de ação que já existem — não ganha
   nenhuma capacidade nova de execução.
3. **Falar com um provedor muda a natureza do produto.** O DevCockpit é
   inteiramente local hoje. Isso passa a não ser verdade, e o tratamento disso
   é explícito: opt-in, redação de segredos, interruptor por projeto, provedor
   local como alternativa.

## Relação com a documentação existente

Estes documentos estendem, não substituem:

- `docs/04-system-architecture.md` — as camadas continuam valendo;
- `docs/05-data-model.md` — as tabelas novas seguem as convenções de lá;
- `docs/07-security-model.md` — as defesas D-A1 a D-A6 continuam a numeração;
- `docs/adr/ADR-003` — a regra de execução é o que dita o desenho do agente.

Se a proposta for aceita, cada decisão estrutural vira ADR próprio
(`ADR-009-ai-provider-abstraction`, `ADR-010-ai-tool-boundary`, …).
