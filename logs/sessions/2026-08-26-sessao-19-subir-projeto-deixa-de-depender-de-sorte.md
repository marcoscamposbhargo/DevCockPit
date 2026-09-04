## 2026-08-26 — Sessão 19: subir projeto deixa de depender de sorte

Sua queixa: "dificuldade pra abrir novos projetos e subir os projetos, alguns
terminais está com conflito". Fui ao registro antes de opinar, e o log de
auditoria não tinha **nenhuma** falha — o que já dizia algo: o problema não era
erro, era impedimento silencioso.

### O que a medição mostrou

Sete de dezenove projetos sem forma conhecida de subir. E o mais importante: as
causas eram três, não uma.

Também me enganei no meio do caminho. Primeiro medi `can_start` pelo endpoint
do servidor de desenvolvimento e concluí que sete projetos não subiam; o card
usa a lista, que já considera Compose, e ali eram três. Corrigi antes de virar
afirmação — e a diferença entre os dois números era exatamente Docker.

### As três causas

**Flask num arquivo só.** `app.py` com `from flask import Flask` e sem
`requirements.txt`. A detecção olhava apenas arquivo de dependência, então o
painel se declarava incapaz de subir algo explícito na primeira linha do
arquivo. Import no código é evidência mais forte que uma linha em requirements:
é o uso, não a intenção. Declaração continua vencendo quando existe.

**Monorepo.** `backend/` e `frontend/` sem nada na raiz. O painel agora olha um
nível abaixo — um só, porque dois já seria varredura, e varredura tem tela
própria. Backend antes de frontend: subir o front contra uma API morta produz
tela que carrega e não funciona, que é pior que não subir.

**Site estático.** `index.html` sem build. Precisa de servidor porque `file://`
quebra fetch, módulo ES e rota. `http.server` da biblioteca padrão não instala
nada e não serve para produção — que é exatamente por que serve aqui.

Depois: **zero projetos sem botão de ligar.**

### O conflito de porta

Não havia conflito nenhum no momento em que medi. Ele aparece **na hora de
subir** — e você descobria pelo erro do Compose, no meio da espera, com uma
informação que o verificador já tinha desde o primeiro ciclo.

Agora existe pré-voo: a página do projeto avisa antes do clique, e o botão
recusa oferecendo as três saídas reais — encerrar quem está na porta (só
processo que o painel pode encerrar, dentro de root permitido), trocar a porta,
ou subir mesmo assim. Porta ocupada por processo **do próprio projeto** não é
impedimento: é ele já estar no ar.

### A última milha

Subi um Flask pelo painel para conferir. Ele subiu — e o painel não sabia onde:
o framework escolheu a 5000, nenhum serviço declarava esse número, e sem isso
não há estado nem botão de abrir. A aba Server passa a mostrar a porta que a
descoberta viu com prova de dono e oferece cadastrá-la num clique. Não grava
sozinho: configuração que muda sem ninguém pedir destrói a confiança.

589 testes (17 novos), `ruff` limpo, aplicativo reempacotado.

### Continua com você

- [ ] tentar subir os projetos que não subiam — OperaLaby, crossperformance e
      os leves — e dizer o que ainda atrapalha
- [ ] o pré-voo aparece na página do projeto; confira se o texto ajuda
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão

---

