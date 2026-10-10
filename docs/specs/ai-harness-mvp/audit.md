# Auditoria — AI Harness MVP

Spec: `spec.md` · Plano: `plan.md` · Tasks: `tasks.md`
Auditado em 2026-09-03, pelo subagent `spec-auditor`, contra o código real (não
contra os relatórios das tasks).

Ambiente verificado: `pytest -q` → 963 passed, 3 skipped, 3 deselected (87,8s).
`ruff check .` → All checks passed. Suíte específica da feature (9 arquivos):
273 passed, 2 skipped (skips por falta de privilégio para `os.symlink` no
Windows nesta máquina — limitação de plataforma, não lacuna de cobertura; a
regra é exercitada por outro caminho, ver REQ-15).

## Constituição

| Princípio | Veredicto | Evidência |
|---|---|---|
| P-01 (sem capacidade nova) | OK | `app/services/ai/actions.py:59-158` — catálogo de 12 ações intacto |
| P-02 (nunca afirma o que não mediu) | OK | `app/services/ai/custo.py:66,93`, `app/repositories/ai_repository.py:303-338`, `app/api/routes/ai.py:876-909` — `null` em todo caminho, inclusive `/usage` com banco vazio |
| P-03 (um processo, sem build) | OK | Nenhum serviço/diretório novo, sem Postgres/Redis/Compose |
| P-05 (segredo só no ambiente) | OK | `registry.py:44-61,376-406`, `routes/ai.py:619-629,713-750`, `settings.js:122-219` — só `api_key_env`, nunca o valor |
| P-06 (provider substituível) | OK | Suíte roda inteira com `FakeProvider`, sem rede |

## Requisitos

| REQ | Veredicto | Evidência |
|---|---|---|
| REQ-01 | Cumprido | `registry.py:120-196,289-303` |
| REQ-02 | Cumprido | `registry.py:82-96,306-325,171-182` — único nome real fora do YAML é `MODELO_PADRAO["openai"]`, explicitamente permitido |
| REQ-03 | Cumprido | `registry.py:376-406` (varredura recursiva por campo e por padrão de valor) |
| REQ-04 | Cumprido | `registry.py:208-209`, `model_router.py:213-216`, `chat_service.py:509-511,533` — suíte inteira roda sem `configs/ai.yml` no disco |
| REQ-05 | Cumprido (com pendência assumida) | `providers.py:282-347` — `OpenAICompatibleProvider` único, DeepSeek/Kimi diferem só por config. Verificação ao vivo com chave real fica para a T-14, como a própria spec já previa (pergunta em aberto 5) |
| REQ-06 | Cumprido | `classifier.py:309-340` — regra pura, sem chamada a modelo |
| REQ-07 | Cumprido | `model_router.py:146-217,222-266` — precedência privacidade > manual > complexidade > padrão |
| REQ-08 | Cumprido | `model_router.py:166-176,259-266` — inclui a desambiguação de 2026-09-03 (manual de nuvem em pergunta `privacy: local` é ignorado) |
| REQ-09 | Cumprido | `runner.py:113-181,504-520` — lista explícita de erro repetível, sem repetir provider já tentado |
| REQ-10 | Cumprido | `runner.py:22-30,439-456,628-658` — grava só no `finally`, depois do stream; teste prova positivo e negativo do bug `fbabea1` |
| REQ-11 | Cumprido | `custo.py:66,93,99-102`, `ai_run.py:92-103` (colunas nuláveis), `routes/ai.py:899-903` (repassa `None`) |
| REQ-12 | Cumprido | `ai_repository.py:278-338` (sem `coalesce` em custo/latência, de propósito) |
| REQ-13 | Cumprido | `routes/ai.py:675-706,776-804` — sonda paralela, 200 mesmo com provider indisponível |
| REQ-14 | Cumprido | `routes/ai.py:713-750`, `settings.js:122-219` — só `api_key_env` |
| REQ-15 | Cumprido | `context_engine.py:39-52,61-75,114-123` — sete arquivos, não segue symlink para fora |

**15 de 15 REQ cumpridos. 0 parciais. 0 não cumpridos. 0 violações de
constituição. 0 escopo indevido** — nem serviço novo, nem provider cloud fora
da lista (Groq/OpenRouter/Gemini), nem ação de IA nova além das 12 do catálogo.

## Desvios entre spec/plano e implementação

**`.env.example` não documentava as quatro variáveis novas** — `plan.md`
prometia `DEVCOCKPIT_AI_KEY_DEEPSEEK`, `DEVCOCKPIT_AI_KEY_MOONSHOT`,
`DEVCOCKPIT_AI_CONFIG_FILE` e `DEVCOCKPIT_AI_MAX_ATTEMPTS`, mas nenhuma das
quatro tasks tocou o arquivo (`Settings` tem default hardcoded, então nada
quebrava em runtime). Severidade baixa — lacuna de documentação, não de
comportamento. **Corrigido nesta sessão**, após a auditoria: as quatro
entradas foram acrescentadas a `.env.example`, com comentário explicando que o
registro é opcional e que `configs/ai.yml` não é versionado. Confirmado sem
regressão (`test_config_and_cache.py`, 15 passed).

Nenhum REQ indicou que a spec estava errada frente à realidade construída — a
única divergência foi de documentação auxiliar, já sanada.

## O que fica para a T-14 (fora desta auditoria, por depender da máquina do usuário)

- Verificação ao vivo do REQ-05 com as chaves reais de DeepSeek e Moonshot.
- Confirmação do identificador exato do modelo Kimi e dos preços em
  `configs/ai.yml` (pergunta em aberto 3 e 4 da spec).
- Migração 010 aplicada no banco de produção
  (`C:/Users/User/DevCockpit/data/devcockpit.db`) e reconstrução/reinstalação
  do executável na mesma sessão.

## Adendo de 2026-10-10 — REQ-08 alcançável pela tela

A auditoria marcou o REQ-08 como cumprido olhando o router, e o router de fato
honrava `EscolhaManual`. Mas nenhuma tela mandava a escolha: `chat_service`
passava sempre `EscolhaManual()` vazia, e o comentário dizia que isso ficava
"para quando a tela mandar um id do registro". Na prática, a pessoa não tinha
como pedir o Claude — e a tela ainda mostrava o modelo do `.env` (Gemma) como
rótulo, embora quem respondesse fosse decidido pelo router.

Fechado nos commits `984660f` e `372358e`: `ChatAsk.modelo`, `modelos` em
`/ai/status`, `event: meta` com quem respondeu, e um `<select>` no chat e na
pergunta rápida. É o mesmo achado da T-13 (tela sem link na sidebar):
"alcançável pelo usuário" faz parte do critério de pronto, mesmo quando a task
lista só arquivos de backend.

A primeira pergunta real ao `claude-opus-5-5` revelou ainda que o
`AnthropicProvider` mandava `temperature`, que o modelo recusa com 400. A
sondagem do REQ-13 não pegava porque `/v1/models` não recebe corpo. Depois da
correção, `ai_run` gravou `decision=manual`, 228/255 tokens e US$ 0,006 — o
gasto medido que faltava desde a T-14.

## Conclusão

Ciclo convergido na primeira rodada de auditoria — não há lacuna que justifique
uma rodada de convergência (fase 6). O único achado (documentação de env vars)
foi corrigido no ato. O MVP está pronto para a T-14.
