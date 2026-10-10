## 2026-10-10 — Sessão 37: o Claude passa a responder pela tela

Ponto de partida: "a API que instalamos não está ativa dentro do DevCockpit". A
sessão 36 tinha conferido as três nuvens, mas rodando do código. No `.exe`
instalado, a Anthropic não aparecia.

### Duas causas, uma escondendo a outra

1. **Chave só no `.env` do repositório.** O app instalado lê
   `C:\Users\User\DevCockpit\.env`, que tinha DeepSeek e Moonshot e não tinha
   `DEVCOCKPIT_AI_KEY_ANTHROPIC`. Provider sem chave sai do roteamento sem
   erro. Linha copiada, com backup `.env.bak-pre-anthropic-2026-10-10`.
2. **`.exe` mais velho que o fix.** Com a chave, a sondagem passou a dar 400. O
   executável era de 2026-09-20 10:08; o fix `3656419` (`x-api-key` e
   `anthropic-version`) entrou às 11:56 do mesmo dia. `build_exe.ps1 -Clean
   -Install` resolveu, e a Anthropic passou a `conectado`.

### O rótulo dizia Gemma, quem respondia era o router

O chat mostrava `DEVCOCKPIT_AI_MODEL` do `.env` (`gemma4:26b`). Mas com
`configs/ai.yml` presente, quem decide é o router, por pergunta: privada vai ao
local, simples ao DeepSeek, complexa ao Claude. E não havia como pedir o Claude
pela tela: o router aceitava `EscolhaManual` desde a T-06, mas o
`chat_service` sempre passava uma vazia.

Fechado em `372358e`:

- `ChatAsk.modelo` com o id lógico do registro; id desconhecido cai no
  automático (P-06), pergunta privada segue só no local.
- `/ai/status` lista os modelos com provider habilitado e chave no ambiente.
- `event: meta` depois do texto, com quem respondeu de fato.
- `<select>` Automático + modelos no chat de projeto e na pergunta rápida,
  com a escolha compartilhada (`lib/modelo-escolhido.js`).

### O bug que só a pergunta real mostrou

A primeira pergunta ao `claude-opus-5-5` voltou 400: "`temperature` is
deprecated for this model". A sondagem de `/v1/models` não manda corpo e por
isso nunca pegaria. Campo removido do `AnthropicProvider` (`984660f`), com
teste de regressão.

Depois disso, `ai_run` id 147: `anthropic`, `decision=manual`, 228/255 tokens,
4 s, US$ 0,006. É o gasto medido que a T-14 deixou pendente.

### Números

975 testes de backend e 96 de frontend passando, `ruff` limpo. `.exe`
reconstruído e reinstalado três vezes; `data\`, `configs\` e `.env`
preservados.

### Para a próxima sessão

- O app instalado subiu na 8765. A 8790 vinha de quem lançava o app antes, e
  `DEVCOCKPIT_PORT` passado no `Start-Process` não pegou — não investigado.
- Ollama estava desligado (`ConnectError`); o local só responde com ele aberto.
- Segue valendo: HyperBrain MVP 4 e Fase 5 do Cockpit AI, ambos esperando
  conversa antes de código.
