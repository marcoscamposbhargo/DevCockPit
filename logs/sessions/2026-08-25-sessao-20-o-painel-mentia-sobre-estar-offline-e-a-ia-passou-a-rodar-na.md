## 2026-08-25 — Sessão 20: o painel mentia sobre estar offline, e a IA passou a rodar na sua máquina

Começou olhando os projetos pesados, como você tinha pedido, e terminou em
outro lugar: um defeito no verificador de saúde que corrompia o que o painel
mostrava, e o Cockpit AI saindo do papel para rodar de verdade — local, sem
chave e sem custo.

### O defeito que estava envenenando o painel

O `db:5432` do APP INGRESSO aparecia OFFLINE com o container no ar. Testei o
socket direto: conectava em 0 ms. Então não era o verificador falhando — era o
verificador **mentindo**.

O histórico deu a prova: latências de 3 a 6 segundos registradas num timeout de
2 segundos. Isso é impossível se o `wait_for` estiver cortando. O tempo foi
gasto **na fila**, não na conexão.

Duas causas, ambas medidas:

1. `_check_http` construía um `httpx.AsyncClient` **por verificação**. O
   construtor monta um contexto SSL e, no Windows, isso custa ~225 ms
   **síncronos, em cima do event loop**. Com 18 serviços HTTP num ciclo, o loop
   ficava bloqueado ~5 s e o timeout de 2 s só era atendido bem depois do prazo.
2. `check_many` disparava todas as verificações de uma vez, sem teto.

Agora há um cliente compartilhado e um teto de concorrência. Nas 22 portas
declaradas da sua máquina:

| | estouraram o teto | pior latência |
|---|---|---|
| antes | 16 de 22 | 5983 ms |
| depois | 0 | 2016 ms |

O sintoma para quem usa era o pior possível: **serviço no ar aparecendo
desligado, de forma intermitente, sem nada errado no projeto**. Provavelmente
explica parte da desconfiança que você tinha no painel. D-57 registra.

### O botão do VS Code

Abrir o editor exigia escolher um projeto antes. No começo do dia a ordem é
inversa: liga a máquina, abre o DevCockpit, abre o VS Code — e o editor
restaura a sessão anterior sozinho. Botão na barra superior, sem caminho nenhum
vindo do cliente, que é o que o dispensa de validar root.

### O Cockpit AI saiu do papel

O provedor local existia desde a Fase 2 e **nunca tinha falado com um Ollama de
verdade** — só com servidor de imitação. Falou. Perguntei ao painel sobre o
próprio DEVCOCKPIT e ele respondeu certo, citando as quatro garantias de
segurança do projeto.

Três coisas atrapalhavam:

- **o `.env` era ignorado em silêncio no executável.** `env_file=".env"` é
  relativo ao diretório de trabalho, que num app empacotado é onde quer que o
  atalho tenha sido clicado. "A IA não liga e não diz por quê" é o modo de
  falha que este projeto não aceita;
- **Ollama fechado** dava `[Errno 10061]`. Agora diz o que fazer.
  `ConnectTimeout` entrou junto de `ConnectError` e **antes** de
  `TimeoutException`: no Windows porta fechada pendura em vez de recusar, a
  mesma peculiaridade que o health check já documentava;
- **modelo não baixado** mandava conferir a variável. Agora o painel pergunta ao
  Ollama e lista os instalados na própria mensagem.

### Dois modelos, e a pergunta rápida

Você pediu o Ollama como agente interno de terminal — e o chat da aba IA é o
lugar errado para isso: ele manda memória, sessão, tarefas e README junto. Numa
dúvida de `git reset` isso é pagar o triplo por informação sem relação com a
pergunta.

Nasceu a **pergunta rápida** (`Ctrl+Espaço`, ou o botão de terminal na barra
superior): sem projeto, sem contexto, não persistida — mas o gasto é
contabilizado, porque teto com porta de saída não é teto.

E dois modelos configurados em vez de um, com seletor. O cliente manda
`"default"` ou `"alt"`, nunca o nome de um modelo — mesma doutrina do
`open_service_url` receber a chave do serviço e jamais a URL (D-13).

### Onde eu errei, e a correção

Recomendei o modelo de 3B com base em quatro perguntas de terminal em que ele
acertou 4 de 4. **O teste era fraco demais para a conclusão.** Eram perguntas
que qualquer modelo viu milhares de vezes; os dois acertarem só provava que
ambos decoraram o básico.

Você desconfiou e mandou testar melhor. Quatro perguntas de diagnóstico depois:

| | Fáceis (comando) | Difíceis (causa raiz) |
|---|---|---|
| `qwen2.5-coder:3b` | 4 / 4 | **0 / 4** |
| `qwen2.5-coder:7b` | 4 / 4 | **0 / 4** |

Uma das difíceis era o bug real corrigido nesta sessão — `except OSError` antes
de `except TimeoutError`, que torna o segundo ramo código morto desde o Python
3.10. **Os dois disseram que o código estava correto.**

E o tamanho não corrige o risco: perguntado por que socket TCP pendura no
Windows, o 3b listou palpites e admitiu não saber; o 7b **inventou "delayed
ACK"** com convicção. Errado com convicção é pior que errado com dúvida — o
primeiro você confere, o segundo você acredita.

Você escolheu o 7b como padrão com o dado à vista. Trocado, e o guia registra a
medição ao lado da decisão, para quem revisitar não precisar refazer o teste.

### Velocidade

O que ninguém tinha olhado: **num modelo local o tamanho da resposta é o tempo
de espera**. O texto sai a ~10 tokens/s, e a pergunta rápida herdava o teto de
2.000 tokens do chat — três minutos de digitação para uma dúvida de `netstat`.

Com teto próprio e prompt de formato fixo, a mesma pergunta caiu de **173
tokens / 14,2 s** para **49 tokens / 6,1 s**. Mesmo comando na resposta; sumiu
a explicação de cada parâmetro. Média de quatro perguntas: 3,9 s. De quebra,
perguntado sobre uma ferramenta inexistente ele passou a responder "não sei" em
1,1 s, em vez de inventar o comando.

O que **não** foi resolvido: o 7b descarrega da RAM após 5 min parado, e
recarregar 4,7 GB custa **143,5 s até a primeira palavra**. Quente ele responde
em 8,4 s; o 3b quente responde em 0,7 s.

### Documentação

`docs/ai/LOCAL_MODEL_GUIDE.md` — o décimo documento de `docs/ai/`, e o único de
uso e não de projeto. O índice ainda dizia "nada aqui está implementado", o que
deixou de ser verdade com as Fases 1 e 2 entregues.

611 testes, `ruff` limpo, aplicativo reempacotado e no ar na 8765.

### Continua com você

- [ ] **decidir o modelo padrão.** Ou `setx OLLAMA_KEEP_ALIVE 60m` (segura o 7b
      na RAM, custa 5 GB presos, resolve os 143 s frios mas não os 34 s
      quentes), ou voltar o 3b (0,7 s quente, sem perda de acerto medida). Duas
      linhas no `.env` em `C:\Users\User\DevCockpit\`
- [ ] `ollama rm llama3.2:3b` e `llama3.2:1b` — 3,3 GB parados, dos modelos que
      erraram 3 de 4 no teste
- [ ] **Fase 3**: especialistas, orquestrador e ações propostas com
      confirmação. É onde "o agente sobe o servidor pra mim" passa a existir —
      pela allowlist, com confirmação, nunca comando novo (D-A3)
- [ ] o painel não gerencia o Ollama (lista de modelos, o que está na RAM,
      descarregar). Cabe bem no que ele já é
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- [ ] conferir a aba Docker com o Docker Desktop **desligado** (pendente desde
      21/08)

---

