## 2026-08-26 (tarde) — Sessão 26: a chave que existia sem fechadura

Sessão curta, um item só, e ele fecha um buraco antigo.

### O interruptor da defesa D-A1

A coluna `ai_enabled` existe na tabela `project` desde a Fase 2, e o modelo de
segurança diz com todas as letras que tirar um projeto do Cockpit AI é decisão
da pessoa — projeto a projeto, porque cliente, contrato ou dado sensível é ela
quem sabe onde estão.

Só que **não havia como decidir**. O campo nascia `true` e ficava `true`: uma
defesa cuja chave ninguém alcançava. Na sessão anterior a rota `PATCH` passou a
aceitar o campo; nesta ele ganhou botão, na aba Overview, com o significado
escrito ao lado — "participa: o contexto deste projeto pode ser enviado ao
provedor" ou "fora: nada deste projeto entra em contexto, nem por engano".

Decisão pequena que vale registrar: **sem cor de perigo no botão**. Tirar um
projeto da IA é proteção, não estrago, e pintar de vermelho ensinaria o
contrário.

Junto fechou o critério de aceite que o MVP 2 do HyperBrain tinha deixado
pendente: o painel lateral do nó avisa quem está fora **antes** de alguém
perguntar. Sem isso, a resposta viria sem contexto e ninguém entenderia por quê.

### Verificação executada

Em banco separado, com dois projetos cadastrados só para isso:

| O que | Resultado |
|---|---|
| `pytest -q` | **649 passaram**, 1 pulado, 3 desmarcados |
| `ruff check .` | limpo |
| Clique no interruptor | rótulo e explicação trocam; aviso na tela |
| Estado no servidor | `ai_enabled: false` gravado |
| Painel do HyperBrain | passa a dizer "Fora do Cockpit AI" |
| Efeito colateral | nenhum: nome, caminho, status, fixado e trava de detecção intactos (teste dedicado) |

### Situação ao encerrar

Branch `main`, árvore limpa, publicado em `410c11c`. Nenhum servidor no ar — o
de verificação usava banco próprio em pasta temporária e foi derrubado.

Do Cockpit AI faltam **3.2, 3.3 e 3.5**. Do HyperBrain, os MVPs 3 a 5.

### Próximo passo

**3.2 + 3.3 juntos**, e a sessão parou exatamente na leitura do
`docs/ai/AGENT_ORCHESTRATION.md`. O desenho já está escrito lá: especialista é
**perfil** (instrução de sistema + ferramentas permitidas + camadas de contexto
preferidas), não agente autônomo; sete perfis; no máximo dois por pergunta; e
regra primeiro, modelo no empate — a mesma doutrina do orquestrador de ações.

Três decisões precisam do usuário antes de escrever código:

1. **Quantos perfis no primeiro corte.** Os sete do documento, ou os três que
   cobrem o uso diário deste painel (DevOps, Full Stack, QA)?
2. **Escolha manual.** A pessoa pode fixar o especialista, ou o roteamento é
   sempre automático?
3. **Onde registrar quem respondeu.** `ai_message` não tem coluna para isso —
   entra por migração `009`, ou vai junto do `context_summary`?

---

