## 2026-08-23 (tarde, parte 2) — Sessão 14: "quem está nessa porta?"

Relato: "subiu 3 projetos ativos sem eu pedir" e "não quer desligar".

Primeiro o que **não** aconteceu: nada subiu. Os processos vivos eram o Django
que você mesmo ligou às 11:43 e os containers da PLATAFORMA, de pé desde as
08:03. O que mudou foi o painel passar a **enxergar** — e a enxergar errado.

Foi a minha varredura de portas que expôs isso. Ao alinhar os cadastros aos
arquivos dos projetos, três serviços passaram a declarar portas que outra coisa
já ocupava: 8000 (container da PLATAFORMA) e 5433 (Postgres nativo). A
verificação de saúde abre um socket e pergunta "tem alguém aí?" — nunca soube
perguntar "quem?". Resultado: MonitorHub, ZAPBOT e Dashboard-contabil apareceram
rodando sem nunca terem subido.

Troquei um sinal errado por outro. O primeiro dizia "desligado" com o projeto de
pé; o segundo dizia "ligado" com o projeto parado. O segundo é pior: leva a
pessoa a tentar desligar o que nunca ligou — e nada acontece, porque não há o
que parar.

### A causa de fundo, e o conserto

A atribuição de porta de container era um palpite: *se um único projeto declara
este número, é dele*. A regra se cala exatamente quando dois projetos declaram a
mesma porta padrão — 8000, 3000, 5432 —, que é o caso comum.

O Compose grava o diretório do projeto em cada container
(`com.docker.compose.project.working_dir`). Perguntar ao Docker troca palpite
por fato:

* `ContainerPortsService` lê `docker ps --format '{{json .}}'` uma vez a cada
  vinte segundos e monta `porta publicada -> diretório do projeto`;
* a descoberta ganhou `matched_by="container-label"`, que conta como **prova**
  — diferente de `container`, que segue sendo dedução pelo número;
* o poller alimenta a descoberta com esse mapa.

E o dashboard deixou de afirmar o que não sabe: cada serviço que responde vem
com `proven` e, quando não há prova, com a explicação de quem está na porta. A
contagem "Rodando" conta só os provados; o card do projeto e o trilho lateral
seguem a mesma regra; a linha da tabela mostra "porta ocupada" no lugar do
selo verde.

Na máquina real, depois do conserto: **1 rodando** em vez de 5, com
"Dashboard-contabil: quem ocupa a porta é wslrelay.exe, do PLATAFORMA DE
INGRESSOS" escrito na tela em vez de um selo verde mentindo.

### O outro "não desliga"

Ligar e desligar mudavam o banco e o processo, mas não o cache do dashboard, que
dura mais que a paciência de quem clicou: o botão respondia sucesso e a tela
seguia dizendo o contrário. Agora `start`, `stop` e `restart` invalidam o cache
do dashboard e o health do projeto.

### A lição

A sessão 8 estabeleceu a regra — prova afirma, inferência sugere, ausência se
cala — e a aplicou na tela de Ports e na de Serviços. O dashboard ficou de fora,
e foi por ali que o mesmo defeito voltou dois dias depois. **Regra aplicada em
três telas de quatro é regra que ainda não existe.**

### Continua com você

- [ ] o painel foi reempacotado e reaberto na 8790; confira o dashboard
- [ ] os projetos com "porta ocupada" continuam listados de propósito: o painel
      não finge que a porta está muda, só para de dizer que é sua
- [ ] zero teste de frontend — a tela que fugia para Ports seria pega por um
      teste de rota
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

