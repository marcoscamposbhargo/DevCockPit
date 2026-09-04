## 2026-08-28 (parte 3) — Sessão 33: a Fase 4 inteira

Pedido para seguir com Fases 4 e 5 do Cockpit AI e MVPs 3–5 do HyperBrain. Esta
sessão fechou a **Fase 4 inteira** — 4.1, 4.2 e 4.3.

### O Health Score, e a regra que o sustenta

Seis indicadores, todos derivados do que o painel já observa: documentação e
testes do disco, ambiente do histórico de ações, atividade das sessões, tarefas
do quadro, dívida da memória.

A regra que decide tudo o mais: **indicador sem dado não vira zero**. Zero é
afirmação sobre o projeto ("está ruim"); ausência é afirmação sobre o painel
("não sei"). Não medido fica fora da média, cinza na tela, com trilha tracejada
em vez de barra vazia — barra vazia ainda se lê como zero.

Por isso o cabeçalho diz a cobertura junto: 67 com cinco indicadores e 67 com
dois não são a mesma afirmação.

**Média simples, sem peso.** Peso seria a primeira coisa a virar palpite: nada
nesta máquina diz que documentação vale o dobro de teste, e o número inventado
contaminaria o agregado inteiro.

**Duas fontes da tabela do plano ficaram de fora, de propósito.** Git, porque
`dirty_count` alto é trabalho em andamento e não projeto ruim — puniria quem
está no meio de uma tarefa. Cobertura de teste executada, porque rodar a suíte
de um projeto alheio para medir saúde é caro e invasivo; só a existência de
arquivo é lida.

### A próxima ação, sem modelo

A aba abre com o que fazer, e o score é o argumento. A ordem é de força da
evidência:

1. o que a pessoa **escreveu** ao fechar a última sessão;
2. a tarefa que ela mesma abriu, mais prioritária primeiro;
3. uma incoerência medida — o aviso de porta divergente;
4. o indicador medido mais baixo que tenha o que sugerir.

Sem chamada de modelo, e isso é decisão: a única coisa pior que não recomendar
nada é recomendar por cima de uma decisão que o dono do projeto já tomou. Toda
recomendação carrega o fato; sem fato, não há recomendação.

### Três defeitos meus, pegos na verificação

1. **O indicador de testes olhava só a raiz** e deu "Testes 0" para o
   AgilContabil, que tem 33 arquivos em `backend/tests`. É a forma de defeito
   que este painel já produziu quatro vezes — correção que para na raiz — e
   aqui seria pior, porque zero é afirmação forte. Corrigido antes de entrar.
2. **Duas recomendações sobre o mesmo tema**: a tarefa aberta e, logo abaixo, o
   indicador de tarefas repetindo. Cada recomendação passou a marcar o tema que
   cobriu.
3. **Sugestão solta parecendo dica de navegação** — "A aba do projeto lista as
   abertas por prioridade" aparecia como se fosse a ação. Ganhou o rótulo na
   frente e passou a apontar para a aba onde o trabalho acontece.

Também um teste meu com premissa errada, corrigido em vez do código: projeto
vazio **com pasta** não é "sem fato" — "não tem README" é fato apurado e merece
recomendação. Sem fato mesmo é o projeto cuja pasta sumiu.

### Situação ao encerrar

Publicado até `3f56c5b`. 725 testes, 58 no frontend, ruff limpo. Painel
instalado igual ao build, uma instância com janela na 8765.

**Estado da máquina:** a aplicação do AgilContabil segue no ar em container
(`agilcontabil-backend-1` na 8100); o servidor nativo dele continua parado desde
a reprodução da sessão 32, e subir os dois disputaria a porta.

### Próximo passo

**HyperBrain MVP 3** (tarefas, sessões, decisões e serviços como nós, com
expansão progressiva) e **MVP 4** (atividade ao vivo, que depende da 3.6 —
entregue). O MVP 5 está marcado como **adiado no próprio documento**, e a Fase 5
do Cockpit AI é a mais distante do uso diário: as duas merecem conversa antes de
código.

Vale lembrar o que a sessão 24 cobrou: o MVP 3 foi adiado para depois de **uso
real da tela**. Esse teste ainda não aconteceu de propósito, e a decisão de
começar assim mesmo é do usuário.

