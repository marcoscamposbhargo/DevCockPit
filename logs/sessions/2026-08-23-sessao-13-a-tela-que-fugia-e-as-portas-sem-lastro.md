## 2026-08-23 (tarde) — Sessão 13: a tela que fugia e as portas sem lastro

### A tela pulando para Ports

Relato: "a página atualiza e vai direto pro módulo de Ports". Bug meu, e do tipo
que a arquitetura convidava.

O `<main id="view">` é o **mesmo elemento** em todas as rotas — só o conteúdo
dele é trocado. A tela Ports protegia seu timer de recarga com
`container.isConnected`, que por isso nunca é falso. O timer sobrevivia à
navegação e, a cada seis segundos, redesenhava Ports por cima da tela aberta.
A assinatura estava no log do painel: 146 chamadas a `/api/services/ports`.

Corrigido no roteador, não na página: `aoSairDaRota()` registra o que precisa
parar, e o roteador limpa antes de renderizar a próxima rota. A página que sabia
o que criar não tinha como saber que a rota mudou; quem sabe é quem troca.

Vale como regra para esta base: **`isConnected` não é sinal de tela ativa quando
o container é reaproveitado.** Qualquer timer, observador ou relógio de página
passa pelo roteador.

### "Dificuldade de abrir o ambiente"

O ambiente estava inteiro no ar. O painel é que olhava para as portas erradas.

No PLATAFORMA DE INGRESSOS: `db` cadastrado em 3010 e `web` em 3019, enquanto o
projeto declara 5434 e 8000 no `docker-compose.yml` e no `.env`. O painel subiu
o Django certo em 3002, e ainda assim mostrava o projeto meio desligado — com o
"Abrir" do web levando a uma porta onde nunca houve nada.

A varredura geral achou o mesmo padrão em mais cinco serviços, todos na faixa
3007–3018 — a assinatura do "Sugerir livre" antigo, corrigido na sessão 6, cujos
números errados continuaram gravados:

```
kiteasy            app        3018 -> 3000
ZapCRM             zap-crm    3015 -> 5000
MonitorHub System  postgres   3013 -> 5433
ZAPBOT             db         3012 -> 5433
Dashboard-contabil dashboard  3007 -> 8000
```

Mais um serviço duplicado: `kiteasy` tinha `app` e `frontend` na mesma 3000, e o
painel contava isso como conflito de porta — tecnicamente certo, praticamente
ruído, porque era o mesmo projeto consigo mesmo.

Depois da correção: zero divergência entre cadastro e arquivo, zero divergência
entre cadastro e o que está escutando, e três conflitos que são reais e
esperados (5000, 5433 e 8000 declarados por dois projetos cada — só doem se os
dois subirem juntos).

### A lição

Um defeito corrigido no código não desfaz o que ele gravou. O "Sugerir livre"
parou de errar em 21/08; os números que ele errou ficaram no banco por dois
dias, e apareceram como "não consigo abrir o ambiente". **Correção de bug de
escrita pede varredura do que já foi escrito.**

### Continua com você

- [ ] abrir o painel e confirmar que a tela não pula mais para Ports
- [ ] os três conflitos restantes (5000, 5433, 8000) são reais: decidir se
      renumera algum, lembrando que isso mexe no arquivo do projeto
- [ ] zero teste de frontend — este bug seria pego por um teste de rota
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

