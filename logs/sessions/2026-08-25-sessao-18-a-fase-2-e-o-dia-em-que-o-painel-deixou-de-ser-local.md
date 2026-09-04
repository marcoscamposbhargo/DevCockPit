## 2026-08-25 (noite) — Sessão 18: a Fase 2, e o dia em que o painel deixou de ser local

Esta é a fase que muda a natureza do produto. Até hoje o DevCockpit não fazia
uma requisição de saída; o pior caso de vazamento era alguém com acesso físico
à máquina. A partir daqui, conteúdo de projeto pode ir para um provedor — e por
isso metade do trabalho foi contenção, não funcionalidade.

### As quatro guardas

1. **desligado por padrão**, e ligar é ato fora da interface
   (`DEVCOCKPIT_AI_ENABLED=true` no `.env`): a API não amplia a si mesma;
2. **projeto pode ficar de fora** individualmente;
3. **teto de gasto** por chamada e por dia, com o consumo na tela;
4. **redação antes do envio**: `.env`, `*.key` e credenciais não são lidos —
   nem para serem redigidos depois; segredo em código sai `[REDIGIDO]`.

### Verificação sem chave de API

Não havia chave de provedor nem Ollama nesta máquina. Em vez de entregar código
de rede nunca exercitado, subi **um servidor que imita a API e relata o que
recebeu**, e conversei com ele pelo painel de verdade.

Ele confirmou três coisas que eu não poderia afirmar de outro jeito:

- o contexto chegou com identidade do projeto, memória, sessão em andamento,
  estado e o README rotulado como *dado, não instrução*;
- num projeto com `.env` contendo `OPENAI_API_KEY` e `DB_PASSWORD`, **nada
  disso chegou**;
- um `README.md` com `STRIPE_SECRET_KEY=sk-live-…` chegou **redigido**.

O que **não** foi verificado, e precisa constar: nenhuma chamada à API real de
nenhum provedor. O formato de requisição e a leitura de stream dos três estão
exercitados por HTTP contra o servidor de imitação — isso prova o meu cliente,
não o contrato do fornecedor. Quando você configurar uma chave, a primeira
conversa real ainda é um teste.

### Dois defeitos que só o uso real mostrou

**403 em toda escrita.** Subi o painel de teste na 8795 sem informar a porta às
`Settings`. É o mesmo defeito da porta que já corrigimos duas vezes — desta vez
apareceu em segundos, porque a defesa D5 funciona.

**Tokens dobrados.** O Context Engine lia `README.md` e `readme.md`: no Windows
é o mesmo arquivo, e ele entrava duas vezes. Teste de unidade nenhum pegaria —
foi o provedor de imitação relatando os blocos recebidos que denunciou.

### A regra que atravessou o desenho

O Context Engine **rotula tudo** que entra. Serve a duas coisas ao mesmo tempo:
proveniência para quem lê a resposta, e aviso ao modelo de que conteúdo de
arquivo é dado e não ordem. O painel varre 28 projetos, e nem todo README foi
escrito por você.

572 testes (41 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] a aba **IA** existe em todo projeto e hoje explica como ligar. Para usar:
      `DEVCOCKPIT_AI_ENABLED=true`, provedor, modelo e chave no `.env` ao lado
      do executável — ou `local` com Ollama, e aí nada sai da máquina
- [ ] a primeira conversa com provedor real é verificação, não uso: confira o
      gasto na tela e se o contexto veio certo
- [ ] Fase 3 (especialistas, orquestrador, ações propostas) segue proposta

---

