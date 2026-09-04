## 2026-08-22 — Sessão 8: o painel para de afirmar o que não sabe

Continuação direta da sessão 7. Abriu com "as portas do servidor estão
confusas" e terminou com um projeto que não subia nem desligava funcionando.
Nove commits, 456 testes, cobertura em 88%.

O fio que costura tudo: **o painel afirmava coisas que não tinha como provar.**
Não por lógica errada — por nunca ter distinguido evidência de palpite.

### "no ar" afirmava dono sem prova

A tela dizia `8000 · SmartDash · Backend · no ar`. O uvicorn do SmartDash tinha
morrido, os dois containers dele estavam `exited`, e quem ocupava a 8000 era
`plataformadeingressos-web-1` — container de outro projeto inteiro.

A causa foi uma regra da sessão anterior. Porta publicada por container não casa
por diretório: o `cwd` do Docker aponta para a instalação dele. Para não gerar
alarme falso, a atribuição passou a usar o número — um único projeto declarando
aquela porta seria o dono. Resolveu o alarme falso e criou um pior: **inferência
apresentada como fato.**

A distinção que faltava: `cwd` e `cmdline` **provam**; o número declarado
**infere**. Quem afirma "está no ar" precisa de prova. Quem mostra "ocupada por
alguém" pode se contentar com palpite, porque não afirma dono. Duas marcas, não
uma. Das quatro portas verdes na máquina, só uma tinha prova.

Essa distinção reapareceu três vezes depois, em lugares diferentes. Era o
defeito de fundo da sessão inteira.

### Comando e cadastro discordando da porta

O `devcockpit.yml` do SmartDash mandava `--port 8000`; o serviço estava
cadastrado em 3001. O painel subia em 8000 e verificava 3001 — encontrava
silêncio e dizia "fora do ar" para algo que estava no ar. O log do projeto tinha
a prova a cada tentativa: `Uvicorn running on http://127.0.0.1:8000`.

O sintoma não aponta para a causa. O servidor sobe, o log não acusa erro, os dois
números estão certos cada um no seu arquivo — só não são o mesmo número. E os
planos detectados não caem nisso: `plan_from_python` recebe a porta declarada e a
injeta. Só o `run:` escrito à mão é literal.

`RunPlan.port` lê a porta do argv nas três formas que aparecem na prática e
compara com a porta do serviço que `run.service` declara fornecer. Onde o painel
se cala, de propósito: comando sem porta legível (`npm run dev` decide dentro do
script), manifesto sem `run.service` (não há contra o que comparar), `-p` fora da
lista de bandeiras (em muito comando ele é outra coisa).

### "Sugerir livre" sugeria porta ocupada

O rastro no banco: `db` da PLATAFORMA em 3004, `dashdate` em 3005, `backend` do
Dashdate em 3006. Três sequenciais logo após as declaradas 3000–3003 — a
assinatura de "Sugerir livre" clicado três vezes.

O botão prometia a menor porta livre e entregava a menor que **nenhum projeto do
painel declarava**. Postgres nativo, container de outro projeto: invisível para
ele. Pior que conflito comum, porque conflito comum aparece — este só na falha do
próximo `up`, ou nunca, com o serviço offline para sempre numa porta onde jamais
esteve. Era a "confusão das portas" relatada.

A tela também recarregava só no botão, sendo metade dela estado vivo. Passou a
reler a cada 6 s, calando-se com edição aberta (redesenhar apagaria o número
digitado), aba escondida e tela trocada.

### Importar `app.main` subia a aplicação de produção inteira

`app = create_app()` no corpo do módulo. Um `import app.main` — o que toda a
suíte faz — apontava o logging para `logs/devcockpit.log`, lia os roots reais e
abria o banco de produção.

Isso atrapalhou a própria investigação: procurei a causa da queixa numa lista de
erros que em boa parte era ficção da suíte, com tracebacks encenados no mesmo
formato dos reais. A construção passou para o acesso ao atributo (PEP 562);
`uvicorn app.main:app` não muda, porque o uvicorn faz `getattr`.

### A detecção não contava o que sabia

Duas falhas encadeadas, e a segunda escondia a primeira.

`parse_published_port` lia `"5432:5432"` e desistia de uma porta escrita como
variável. A PLATAFORMA escreve as duas portas assim, então a detecção devolvia
zero serviços para ela sem dizer que não soube ler — indistinguível de um projeto
sem Compose. Agora resolve como o Compose resolve: `.env` primeiro, valor de
reserva depois.

E `_apply_services` pulava serviço já cadastrado — calado. "Edição manual vence
sempre" está certo e continua valendo; faltava o outro lado: **não sobrescrever
não é motivo para não contar**. `port_drift` relata sem aplicar.

A primeira versão dessa checagem acusou os três projetos da máquina de uma vez,
todos com `detected: 8000` — o padrão do uvicorn, não leitura de arquivo nenhum.
`SuggestedService.port_source` separa `"file"` de `"convention"`; só arquivo
contradiz cadastro. Mesmo erro da manhã, cometido de novo em outro lugar.

### "Desligar" decidia pelo plano, não pelo estado

Relatado no Dashdate. `down()` perguntava se o projeto *tem* aplicação separada
e, tendo, parava a aplicação — inclusive quando ela já estava parada. O Dashdate
tem plano de `uvicorn`, o `uvicorn` estava parado, e quem atendia era o
container. O clique parava algo já parado e respondia sucesso.

E o modo Docker era pior: `down()` devolvia a string `"docker"`, **ninguém
executava `compose down`**, e o cliente anunciava "ambiente derrubado". Uma
resposta de sucesso descrevendo algo que não aconteceu é pior que um erro — o
erro pelo menos manda olhar.

Agora decide pelo estado, executa o que decide (job, como o `/up`), e responde
`"nothing"` quando não havia nada — que é diferente de "o botão não funcionou".

### Encerrar processo que o painel não subiu

A tela de Ports já encerrava órfãos. Faltava o vizinho: processo em root
permitido, numa porta que um projeto **declara**, que o painel não subiu. O
"Desligar" do card não alcança esses, porque desligar é encerrar o que o painel
iniciou.

Duas guardas que só apareceram rodando na máquina. **O painel se oferecia para
ser encerrado** — roda em root permitido, na porta que declara, e não foi ele que
se subiu. **Porta efêmera não é serviço** — a primeira execução ofereceu matar um
`node.exe` na 18663 e um `bun.exe` na 58176, ferramentas rodando dentro da pasta.
Estar no diretório não faz de um processo o servidor do projeto.

### "online" dizia que alguém respondeu, nunca quem

Relatado no SmartDash: tentar desligar várias vezes e o card insistir em
"1/2 online". O SmartDash já estava desligado — containers removidos, `uvicorn`
parado. Quem respondia na 5432 era o `ecommerce_postgres`, container de um
projeto nem cadastrado aqui.

A verificação de saúde abre um socket e pergunta "tem alguém aí?". Nunca soube
perguntar "quem?" — e as duas perguntas divergem assim que dois projetos
compartilham um número. Era o mesmo defeito da manhã sobrevivendo na coluna de
estado dos serviços.

O primeiro corte mirou largo demais: porta de container nunca casa por diretório,
então **todo** serviço em Compose virava suspeito. Num fluxo baseado em Docker
isso é ruído puro — um aviso que aparece sempre não avisa nada. Faltava a
pergunta que o Docker responde de graça: existe container **deste projeto**
publicando esta porta? Se existe, é prova.

### O SmartDash, ponta a ponta

O compose dele publicava 5432 (ocupada pelo `ecommerce_postgres`) e 8000
(ocupada pela PLATAFORMA). Dois containers não publicam o mesmo número — por isso
não subiam. Passou a publicar em 5435 e 3001, por variável, com a porta interna
intacta.

Com os containers subindo, apareceu o defeito seguinte, do projeto e não do
painel: `docker/Dockerfile.backend` copiava só `backend/` e `frontend/`, e o
startup roda `alembic upgrade head` lendo `alembic.ini` da raiz e
`database/migrations`. O container morria em `CommandError: Path does not
exist`, e o `compose up` **reportava sucesso** — o container é criado antes de o
processo falhar.

Resultado: **SmartDash · 2/2 online · Ligado**, de um projeto que não subia nem
desligava.

### Erros meus nesta sessão

- suspeitei de vazamento do painel ao ver 17 processos `runserver`; as cadeias
  extras tinham `powershell.exe` como pai — subidas manuais. Corrigido antes de
  virar afirmação;
- `git add -A` levou `Dockerfile`, `docker-compose.yml` e `.dockerignore` do
  usuário para dois commits. Removidos com `--amend` nas duas vezes;
- `ruff format app/services/` reformatou seis arquivos não relacionados que
  entraram num commit de feature;
- o falso positivo do `port_drift` (todos os projetos acusados) e o do
  `unmanaged` (portas efêmeras) foram **o mesmo erro** que eu tinha acabado de
  corrigir, cometido de novo. Só apareceram porque rodei na máquina real.

### A lição do dia

A sessão 7 foi sobre informação represada por falta de caminho. Esta é sobre o
oposto: **informação afirmada sem lastro**. "No ar", "online", "ambiente
derrubado", "nada mudou" — quatro afirmações que a interface fazia sem ter como
sustentar, e cada uma custou ao usuário a confiança na tela seguinte.

O padrão da correção foi sempre o mesmo, e vale guardar: separar o que se
**prova** do que se **infere**, e deixar cada um dizer só o que aguenta. Prova
afirma; inferência sugere; ausência de dado se cala. As três vezes em que errei
foram por esquecer a terceira — transformar "não sei" em acusação.

E o corolário: **um aviso que aparece sempre não avisa nada.** O `port_drift`
acusando os três projetos e o `unmanaged` oferecendo matar ferramentas eram
tecnicamente corretos e praticamente inúteis. Precisão importa tanto quanto
correção.

### Continua com você

- [ ] duas tabelas sem escrita nem leitura (`HealthSnapshot`, `GitRepository`) e
      duas configurações nunca consultadas (`activity_retention_days`,
      `timeout_scan`). A primeira significa log de atividade crescendo sem
      limite. Implementar ou apagar; manter é o pior dos três
- [ ] `git_service` a 47%, o menor do projeto (total em 88%)
- [ ] zero teste de frontend, contra ~5000 linhas de Python testadas — e os
      defeitos de interface continuam sendo a maioria
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` do DevCockpit estão
      untracked na raiz; decidir se entram
- [ ] o SmartDash usa SQLite no `.env` local e sobe um Postgres no Compose que a
      aplicação local ignora — o serviço `db` cadastrado pode ser ruído
- [ ] as três edições no SmartDash (compose, Dockerfile, cadastro) não foram
      commitadas: o projeto vive dentro de um repo maior com 24 arquivos de
      outros projetos modificados
- [ ] a branch `varredura/bugs-e-organizacao` está com 30 commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

