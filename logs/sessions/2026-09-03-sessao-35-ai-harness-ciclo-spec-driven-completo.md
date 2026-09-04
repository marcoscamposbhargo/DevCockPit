## 2026-09-03 — Sessão 35: AI Harness, ciclo spec-driven completo

Ponto de partida: dois documentos soltos na raiz do repositório (`PRD —
DEVCOCKPIT AI HARNESS / HYPERBRAIN.MD` e o "Prompt Mestre" de implementação)
pedindo uma infraestrutura de IA com serviço FastAPI separado, PostgreSQL,
Redis, Docker Compose, RAG, múltiplos agentes e Developer Agent que edita
arquivo. O primeiro trabalho da sessão foi medir o que já existia antes de
aceitar esse escopo: `app/services/ai/` já tinha 1.984 linhas rodando —
provider abstraction, três especialistas, catálogo fechado de ações, teto
diário de tokens, auditoria com `actor=ai`. O PRD, ao pé da letra, colidia
frontalmente com ADR-002 (SQLite), ADR-005 (frontend sem build) e a defesa D-A3
(a IA não ganha capacidade nova) — e o app é um `.exe` PyInstaller de um
usuário só, não um produto multiserviço.

Depois de apresentar esse recorte e receber aprovação para seguir só com o
delta dentro da arquitetura existente, rodou o ciclo `/spec-driven` completo:
constituição → spec → plano → tasks → implementação em ondas → auditoria.

### Fase 0 — Constituição

`docs/constitution.md` (v1.0.0), sete princípios destilados dos nove ADRs, do
modelo de segurança e das defesas D-A1/D-A3 — nada inventado, só consolidado.
P-01 (sem capacidade nova), P-02 (nunca afirma o que não mediu), P-03 (um
processo, sem build), P-05 (segredo só no ambiente) foram os que mais
seguraram decisão ao longo da sessão.

### Fases 1-4 — Spec, plano, tasks, implementação

Spec `docs/specs/ai-harness-mvp/spec.md`: 15 requisitos (REQ-01 a REQ-15)
cobrindo registro declarativo de providers/modelos, task classifier por regra,
model router com fallback, custo estimado datado, e `.project-ai/` no
contexto. Fora de escopo explicitamente dividido em "barrado por princípio"
(serviço separado, Developer Agent, chave visível) e "adiado por fase" (RAG,
Judge, multi-agent, roteamento adaptativo).

Decisão que mudou o meio do ciclo: o usuário pediu DeepSeek e Kimi (Moonshot)
como modelos de trabalho em vez do "local first" original do PRD. Medido nesta
máquina — 24 a 32 tok/s no `qwen2.5-coder:7b`, sem GPU — a meta de 70-80% local
do PRD nunca foi realista aqui. A spec registrou isso como premissa corrigida,
não como meta perdida: o local ficou na cadeia só por privacidade (REQ-07 item
1, recusa em vez de promover para nuvem) e como último elo sem internet.

Tasks: 14 tasks em 5 ondas, executadas por `spec-implementer`/`frontend-builder`
em paralelo dentro de cada onda. Concluídas nesta sessão: T-01 a T-13, mais
T-12.1 (adicionada no meio do ciclo, ver achados).

### Achados

**`qa` tinha dois significados no mesmo serviço.** A T-03 (task classifier)
definiu `task_type: qa` como "pergunta e resposta genérica" e o tornou padrão.
Mas `app/services/ai/especialistas.py:104` já define `QA` como quality
assurance (testes, bugs, regressão) — mesmo sentido do PRD §24. Do jeito que
ficou, toda pergunta solta seria roteada para o especialista de testes. É o
mesmo padrão de defeito da sessão 31/32 (quatro definições de "qual serviço é
a aplicação"). Corrigido: `qa` voltou a ser quality assurance com gatilhos
próprios, escopados a frase para não colidir com `debugging`/`testing`
("o que pode quebrar" contém `quebrar`, mas não é debugging); `simple_task`
virou o padrão sem condição.

**Corpo de resposta do provider podia vazar prompt para o banco.**
`_HttpProvider._explicar` incluía até 200 caracteres do corpo bruto da
resposta na mensagem de erro — um provider que ecoasse parte do prompt
("não entendi: <trecho>") levaria isso para `ai_run.error`, violando REQ-10.
A T-09 separou `Falha.motivo` (frase de catálogo, vai pro banco) de
`Falha.detalhe` (mensagem mascarada, só log). Achado da própria agente, não
pedido explícito da task.

**Ambiguidade real entre REQ-07 e REQ-08.** A spec não dizia o que acontece
quando a pessoa escolhe manualmente um modelo de nuvem numa pergunta marcada
como `privacy: local`. A T-06 resolveu para o lado seguro — escolha manual
vence *qual modelo*, nunca *se a pergunta pode sair da máquina* — e a spec foi
desambiguada no ato para registrar isso como regra, não como interpretação de
uma agente.

**Divergência de plano descoberta na T-09, corrigida por agente dedicado.** O
plano previa que `build_provider` em `providers.py` ganhasse o caminho
registry→cliente; por ordem de conclusão das tasks (T-02 fechou antes da T-01
existir), a T-09 duplicou essa lógica em `runner.py`. A agente sinalizou a
divergência em vez de decidir sozinha; um agente à parte unificou em
`providers.py`, com cuidado explícito de import circular (resolvido com
`TYPE_CHECKING`), sem regressão nos 956 testes da época.

**`ask_quick` ficou fora do fallback na primeira passada.** A T-12 ligou só
`ask()` (chat com histórico) ao runner, porque era o alvo explícito dos
critérios de aceite. `ask_quick()` — único chamador real: `POST /api/ai/chat`
— ficou sem fallback nem gravação de `ai_run`. Não era caso teórico: é rota em
produção. Decisão do usuário foi fechar isso na hora, task T-12.1 adicionada
ao ciclo e executada antes de encerrar.

**`chave.txt` solto na raiz, nunca commitado mas não ignorado.** Duas agentes
diferentes tropeçaram nele sem abrir o conteúdo. Confirmado: nunca entrou no
histórico do git (`git log --all -- chave.txt` vazio), mas aparecia como `??`
— um `git add .` distraído o teria versionado. Adicionado ao `.gitignore` na
hora; o arquivo em si fica para o usuário mover o conteúdo para `.env` e
apagar, na T-14.

**Tela de consumo sem link de navegação.** A T-13 construiu `ai-usage.js`
funcional, mas só listou `router.js` nos arquivos da task — a página ficou
alcançável só por URL direta. Adicionado o item "AI Usage" na sidebar
(`frontend/index.html`) com ícone novo (`gauge`, mesmo traço dos demais) fora
do ciclo de tasks, por ser lacuna óbvia de usabilidade.

**Busca web trouxe nomes de modelo não verificáveis.** Ao preparar o passo a
passo da T-14, uma pesquisa automatizada trouxe `deepseek-v4-flash`/`v4-pro` e
`kimi-k3`/`k2.6` como identificadores reais — possivelmente corretos, mas
vistos só por resumo de IA sobre a página, não a documentação crua, e
posteriores ao corte de conhecimento do assistente. Decisão: não escrever isso
em `configs/ai.yml` sem o usuário confirmar direto no painel/billing de cada
fornecedor. Documentado como passo 1 obrigatório da T-14.

### Fase 5 — Auditoria

`docs/specs/ai-harness-mvp/audit.md`: 15 de 15 REQ cumpridos, 0 violações de
constituição, 0 escopo indevido, convergência na primeira rodada — sem
necessidade de fase 6. Único achado: `.env.example` não documentava as quatro
variáveis novas que o plano prometia (`DEVCOCKPIT_AI_KEY_DEEPSEEK`,
`DEVCOCKPIT_AI_KEY_MOONSHOT`, `DEVCOCKPIT_AI_CONFIG_FILE`,
`DEVCOCKPIT_AI_MAX_ATTEMPTS`) — severidade baixa, nada quebrava em runtime.
Corrigido na hora.

### Verificação executada

```
pytest -q                              → 963 passed, 3 skipped, 3 deselected (92s)
ruff check .                           → All checks passed
node --test tests/frontend/*.test.mjs  → 89 passed, 0 failed
```

Os 3 skips são `os.symlink` em `.project-ai/` e `context_engine.py`, que
exigem Modo de Desenvolvedor/administrador no Windows — a regra que eles
testariam foi coberta por caminho alternativo (junction de diretório, testado
à mão pela agente da T-05).

### Situação ao encerrar

Working tree com 43 arquivos alterados/novos, ainda não commitados (checkpoint
desta sessão vai commitar). Nenhum arquivo de segredo staged — conferido
`.env.example` e `.gitignore`, só nome de variável, nenhum valor.

**14 tasks automatizadas concluídas** (T-01 a T-13 + T-12.1). Falta só
**T-14**, exclusivamente manual, documentada passo a passo em
`docs/specs/ai-harness-mvp/t14-passo-a-passo.md`:

1. Confirmar identificador real e preço de DeepSeek e Kimi direto no
   painel/billing de cada fornecedor (não usar os nomes que a busca trouxe
   sem validar).
2. Escrever `configs/ai.yml` a partir do exemplo.
3. Colocar as duas chaves no `.env`; apagar `chave.txt`.
4. Aplicar migração 010 no banco de produção **e** reconstruir/reinstalar o
   `.exe` na mesma sessão (senão o painel instalado quebra com erro de
   revisão).
5. Verificação ao vivo: pergunta real por DeepSeek/Kimi com custo aparecendo;
   Ollama parado + pergunta privada deve recusar, nunca ir pra nuvem; chave
   errada não repete tentativa.

### Próximo passo

T-14, pelo usuário, seguindo o passo a passo. Depois dela, a spec
`ai-harness-mvp` está encerrada de ponta a ponta. O que ficou de fora por
decisão de escopo (RAG, Judge/multi-agent, roteamento adaptativo, Groq/
OpenRouter/Gemini como classes próprias, `write_summary` sem fallback) segue
registrado em "Fora de escopo" da spec para quando fizer sentido reabrir.

Nada do HyperBrain MVP 3/4 nem da Fase 5 do Cockpit AI foi tocado nesta
sessão — seguem exatamente onde a sessão 33 deixou.

## 2026-09-03/04 — Sessão 35 (continuação): T-14 executada, dois defeitos reais

Retomada da mesma sessão para executar a T-14 — a única task manual do ciclo.
Os quatro primeiros passos correram como documentado, mas o passo 5
(verificação ao vivo) encontrou dois defeitos que nenhum teste com registro em
memória teria pego, porque os dois só existem no contato com o `.exe`
empacotado e com as APIs reais.

### Passo 1 — confirmação dos modelos, por busca web

Sem acesso a shell interativo do usuário nem tempo de espera para ele abrir o
painel de billing, usei `WebFetch` repetido (3-4 chamadas por fornecedor) para
tentar confirmar `base_url`, identificador de modelo e preço. Os resultados
foram consistentes entre chamadas independentes, mas dois dos quatro dados
**estavam errados** e só a verificação ao vivo revelou isso:

- **DeepSeek**: `deepseek-v4-flash` — correto. Confirmado por
  `/api/ai/health` listando exatamente esse nome entre os modelos da conta
  real.
- **Kimi (Moonshot)**: a busca trouxe `kimi-k3` de forma consistente em três
  chamadas — **não existe na conta real**. `/api/ai/health` listou
  `kimi-k2.6` e `kimi-k2.7-code`. Corrigido para `kimi-k2.6`, com o preço de
  `kimi-k3` ($3/$15 por 1M) removido da tabela — não fica preço de um modelo
  atribuído a outro (P-02).
- **`base_url` da Moonshot**: `https://api.moonshot.ai/v1` respondia 404 em
  `/v1/models` — a convenção deste projeto (`OpenAICompatibleProvider`) já
  anexa `/v1` sozinho, então `base_url` correto é **sem** o sufixo. O 404 (não
  401/403) foi o que indicou "rota duplicada", não "chave recusada" — chave
  errada dá 401 de verdade, testado depois no item 4 do checklist.

### Passo 4 — migração e rebuild, sem incidente

Banco de produção (`C:/Users/User/DevCockpit/data/devcockpit.db`, 20 projetos,
4,5 MB) migrado para `010_ai_run` com backup prévio
(`devcockpit.db.bak-pre-010-2026-09-03`). Processo parado e confirmado morto
antes de tocar `_internal`; uma tentativa de `rm -rf` bateu em
"Device or resource busy" mesmo sem processo listado — resolvido com
`sleep 3` e nova tentativa, sem precisar investigar mais.

### Defeito 1 — launcher não resolvia `DEVCOCKPIT_AI_CONFIG_FILE`

Depois do primeiro rebuild, `/api/ai/providers` voltava `items: [], ativo:
false` mesmo com `configs/ai.yml` presente e as chaves no `.env`. Causa:
`app/launcher.py::preparar_ambiente` tinha `os.environ.setdefault` para
`DATABASE_URL`, `LOG_FILE`, `ROOTS_FILE` e `DEFAULTS_FILE`, resolvendo cada um
para caminho absoluto ao lado do `.exe` — mas não para
`DEVCOCKPIT_AI_CONFIG_FILE`, que a T-01 introduziu. No `.exe` empacotado,
`"./configs/ai.yml"` relativo resolve contra `sys._MEIPASS` (a pasta temporária
do PyInstaller que some ao fechar), não contra `C:\Users\User\DevCockpit\`.
Sem erro nenhum — o registro simplesmente parecia vazio. Corrigido com a mesma
linha de `setdefault` que os outros três já tinham; teste de regressão em
`test_launcher.py`.

### Defeito 2 — fallback nunca chegava ao modelo local

Mais sério: com as duas contas cloud (DeepSeek e Moonshot) **de fato sem
saldo** — confirmado direto contra a API, fora do DevCockpit — uma pergunta
comum, sem marca de privacidade, falhava com `AI_CHAIN_EXHAUSTED` mesmo com o
Qwen local rodando e saudável. Investigação: `model_router.py::_modelos_de_nuvem`
exclui de propósito o modelo local do critério "mais barato"/"maior janela"
(comportamento correto, documentado desde a T-06 — sem isso o local venceria
toda pergunta simples e devolveria a economia para 24-32 tok/s). O problema é
que ele nunca era **reintroduzido depois**, como último recurso. O comentário
do próprio `ai.yml` ("o local é a rede de segurança sem internet") descrevia
uma garantia que o código não entregava.

Corrigido em `model_router.py`: depois de montar a lista ordenada de nuvem, o
modelo local que declare a mesma capacidade entra ao final da fila — exceto
quando há restrição manual de provider (REQ-08), porque completar por baixo de
um pedido explícito da pessoa seria contrariá-lo. Dois testes de regressão
novos, três testes existentes corrigidos (esperavam a ausência do local, agora
esperam-no como último item).

Um terceiro achado, encontrado no meio da correção: erro **não repetível**
(chave inválida, sem saldo) estava configurado para **parar a cadeia inteira**,
não só pular aquele provider — herança de uma leitura estrita demais do REQ-09
original. Corrigido: `raise` virou `continue`, e só `_exigir_orcamento()`
(antes de qualquer tentativa) continua interrompendo tudo. `spec.md` corrigida
nos dois pontos (REQ-07 e REQ-09), com nota de correção datada.

### Verificação ao vivo, o que fechou e o que não fechou

Contra o painel real, com projeto `app-ingresso`:

- **Item 1 (resposta com custo)**: bloqueado — as duas contas cloud estão sem
  saldo (402 na DeepSeek, 429/quota na Moonshot, confirmados direto na API).
  Não é defeito do sistema; fica para quando o usuário recarregar.
- **Item 2 (fallback avança entre providers)**: confirmado com `ai_run` real —
  chave corrompida de propósito na DeepSeek gerou 1 tentativa (`error`, sem
  repetir), avançou para Kimi (`attempt=2`).
- **Item 3 (privacidade)**: confirmado duas vezes — com Ollama parado (não
  testado até o fim, o usuário subiu o Ollama no meio) e com Ollama de pé:
  pergunta marcada como privada (`.env` no texto) roteou para
  `provider=local, status=ok`, 117s, nunca tentou nuvem.
- **Item novo, não previsto no checklist original**: pergunta comum, nuvem
  inteira sem saldo, cai para o local como rede de segurança — 77s,
  `attempt=2`, confirmado em `ai_run` depois da correção do Defeito 2.
- **Item 5 (painel abre sem erro de revisão)**: confirmado em 3 reinstalações
  desta sessão.

### Situação ao encerrar

968 testes passando (+4 desde o commit anterior: 2 do launcher, 2 do router),
3 pulados, `ruff` limpo. Commit `67b0a68` com as duas correções e a spec
atualizada. `configs/ai.yml` e as chaves reais estão nos dois lugares que
importam — repositório (para versionar o exemplo e rodar teste) e
`C:\Users\User\DevCockpit\` (produção) — nenhum dos dois versionado de
verdade, como o `.gitignore` já garantia.

O ciclo `ai-harness-mvp` está **funcionalmente fechado**: os dois defeitos que
a verificação ao vivo existia para pegar, pegou. O que resta não é código — é
o usuário recarregar saldo em pelo menos uma conta cloud para ver uma resposta
real de DeepSeek ou Kimi com custo na tela de AI Usage.

### Próximo passo

Usuário recarrega DeepSeek ou Moonshot; ao retomar, repetir a pergunta comum
do item 1 e conferir custo aparecendo com a `price_date` certa. Depois disso,
marcar o checkbox de T-14 em `tasks.md` — está pendente porque o item 1 não
fechou nesta sessão.

Como antes: HyperBrain MVP 3/4 e Fase 5 do Cockpit AI seguem intocados.
