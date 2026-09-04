## 2026-08-22 — Sessão 6: Varredura de bugs, descoberta de porta e ligar sem terminal

**Pedido de partida:** "vamos dar uma varredura pra achar bugs e organizar toda
a parte do sistema". Ao longo da sessão o pedido cresceu com o que foi
aparecendo na tela: o ZAPBOT que não desligava, a barra de ativos que só
fechava, projeto novo que parecia não ser escaneado, e o ponto central — não
precisar abrir o terminal para subir cada projeto.

### A varredura

Leitura de `app/`, `frontend/` e `tests/` inteiros. Oito defeitos reais, todos
com teste de regressão em `tests/unit/test_regressoes_varredura.py`.

**1. URL de serviço aceitava destino externo.** `validate_local_http_url` achava
o host cortando a string no primeiro `:`. Em `http://localhost:3000@evil.com/`,
`localhost:3000` é *userinfo* e o host real é `evil.com`: a URL passava, virava
`health_url` de um serviço e o poller passava a bater num host externo a cada
ciclo. O host agora sai de `urlparse`. De brinde, `http://[::1]:8080` passou a
ser aceito — o parser antigo rejeitava IPv6 com porta.

**2. Console de job congelava depois do primeiro truncamento.** `revision`
conta tudo que já saiu e nunca retrocede; `lines` encolhe a cada corte. O
código fatiava `lines[after:]` com um índice absoluto, então a partir do
primeiro truncamento o SSE entregava listas vazias para sempre. `Job` ganhou
`dropped` e `lines_since`, e o marcador de truncamento saiu da lista — linha
sintética no meio dos dados desalinha qualquer cursor.

**3. Terminal abria e era morto pelo timeout.** Terminal, editor e explorador
rodavam com `capture_output` e timeout de 10 s. `powershell -NoExit` e
`alacritty` só terminam quando o usuário fecha a janela: o timeout matava a
janela recém-aberta, e o pipe de captura impedia console próprio. `CommandSpec`
ganhou `detached`, e o runner dispara sem esperar. Vale para as três
plataformas.

**4. `serve.ps1` morria antes de subir o uvicorn.** O alembic escreve as linhas
`INFO` dele em stderr mesmo quando dá certo. Com `ErrorActionPreference` em
`Stop`, o PowerShell 5.1 empacota cada linha num ErrorRecord e o script termina
ali — sem mensagem que apontasse para migração. O sintoma era "o servidor não
sobe". Quem decide agora é o código de saída.

**5. Serviço desligado aparecia como erro.** `_check_http` mapeava qualquer
timeout para ERROR. No Windows, tentar uma porta sem ninguém escutando pendura
até o timeout em vez de recusar na hora, então o caso mais banal que existe —
o serviço não foi ligado — chegava na tela como "erro". Vermelho que aparece
sempre para de significar alguma coisa. `httpx` separa os dois casos e o código
não usava a distinção: `ConnectTimeout` é não ter conectado (OFFLINE), qualquer
outro timeout é ter conectado e não ter respondido (ERROR).

Mais três de menor porte: `compose_file` do manifesto era gravado e nunca lido;
`FORBIDDEN_FLAGS` estava declarado e nunca conferido, então a barreira contra
`down -v` no registro era só documentação; e o ramo de timeout do check TCP era
código morto, porque desde o Python 3.10 `TimeoutError` é subclasse de
`OSError` e o `except` vinha depois.

### Descoberta de porta

O painel só sabia o que alguém tinha digitado no cadastro. Quando o número
ficava velho — e fica, porque ninguém volta no painel depois de mudar a porta no
`.env` — o projeto aparecia parado com o servidor no ar. O caso desta máquina: o
próprio DevCockpit estava cadastrado em 3003 e rodando em 8765.

`app/adapters/system/ports.py` enumera as portas em escuta e, para cada uma, o
processo que a abriu. `app/services/port_discovery_service.py` atribui cada
porta a um projeto, nesta ordem: diretório de trabalho do processo dentro do
projeto, caminho do projeto na linha de comando, runtime de container (marcado,
não atribuído), e sem dono. A comparação de path é por componente, não por
texto — `/dev/app-antigo` não pode casar com `/dev/app`, o mesmo bug que
`app/core/paths.py` existe para não ter.

**Por que `psutil` e não `netstat`.** A pergunta não é "que portas estão
abertas" e sim "de quem é o processo que abriu". Só o diretório de trabalho
responde isso. Medido: `psutil` faz a varredura inteira em ~5 ms;
`Get-NetTCPConnection` mais `Get-Process` levava ~1,4 s e ainda assim não dava o
`cwd`.

A tela de Ports ganhou o aviso de divergência com um botão que adota a porta
observada, a marca "no ar" nas portas que realmente respondem, e a lista
recolhida das portas de terceiros — que é a resposta para o `up` que falha com
*address already in use*.

Três limites deliberados: descoberta não corrige declaração sozinha; projeto sem
nada escutando não vira divergência (silêncio é o estado esperado de projeto
parado, e alerta que aparece para todo mundo não alerta ninguém); e varredura
recusada por privilégio marca `observation_available: false`, para a tela dizer
"não consegui olhar" em vez de "nada escutando".

### Ligar sem abrir terminal

O pedido central da sessão. Até aqui "ligar" só existia para projeto com
Compose; projeto de `npm run dev` ou `uvicorn` — a maioria — exigia abrir um
terminal e digitar o comando toda vez.

**O que muda no ADR-003.** Não muda: nenhum valor vindo do cliente HTTP entra em
argv; o cliente manda o id do projeto e nada mais. Muda: o argv deixa de ser
exclusivamente literal no código e passa a poder vir do bloco `run:` do
`devcockpit.yml` ou da detecção sobre `package.json` e `pyproject.toml` —
sempre arquivos dentro de um root permitido.

É aceitável porque quem escreve esses arquivos já executa o que quiser na
máquina por caminhos mais curtos: `scripts` do `package.json` roda em `npm
install`, hook do Git roda em `git commit`. A superfície que o modelo de
segurança fecha é a remota (D1, D5, D10), e essa continua inteira.

Ainda assim há guarda, porque comando lido de arquivo erra sem ser malicioso:
string no lugar de lista é recusada, `cwd` que escapa do projeto é recusado, e
os fragmentos destrutivos que o registro fixo já recusava também — o `run:`
copiado de outro projeto trazendo um `down -v` apagaria o volume do banco no
primeiro clique.

**Por que não é job.** Job é "faça isto e termine": timeout, cancelamento no
encerramento da aplicação, descarte por retenção. As três coisas matam um `npm
run dev`. O processo nasce ao lado do `JobManager`, sem timeout, em grupo
próprio, com o PID no banco. Sobreviver ao painel só não vira órfão porque a
descoberta de porta existe: na volta, o processo é reencontrado pelo PID gravado
e confirmado pela porta em escuta.

### Os dois detalhes que só apareceram rodando

Nenhum dos dois é visível na leitura do código, e os dois custaram uma volta
inteira de teste no browser real.

`npm` no Windows é `npm.CMD`. Sem shell, `CreateProcess` recebe "npm", não acha
arquivo com esse nome exato e devolve "o sistema não pode encontrar o arquivo
especificado" — com o npm instalado. Falta a extensão, que só o `PATHEXT`
conhece. `shutil.which` resolve, e era a mesma solução que
`WindowsOSAdapter.open_in_editor` já usava para o `code`.

`DETACHED_PROCESS` custava o log. O `.CMD` roda por dentro do `cmd.exe`, que sem
console nenhum alocava um por conta própria e mandava a saída para lá: o
servidor subia certo e o log aparecia vazio, que é a pior combinação possível
para depurar uma queda. `CREATE_NO_WINDOW` esconde a janela sem quebrar o
redirecionamento e também não amarra o filho ao nosso tempo de vida.

### Os três relatos de tela, e o que cada um era de verdade

**"O ZAPBOT não desliga."** Desligava: os seis containers paravam. O que não
parava era a porta 5433, e a porta 5433 não é do container — é de um Postgres
nativo rodando na máquina. O verificador batia nela, achava resposta, e trinta
segundos depois devolvia o botão para "Ligado". A causa de fundo era o botão
declarar o estado a partir do código de saída do comando; parar container não é
o mesmo que a porta ficar livre. Agora a tela reverifica depois da ação e, se
os containers pararam mas a porta continua atendendo, diz isso em vez de fingir.

**"A barra de Ativos só fecha."** O toggle sempre funcionou. O botão da topbar
era um ícone sem rótulo: fechar é óbvio, o X mora dentro da própria barra;
reabrir dependia de adivinhar que aquele ícone era o caminho de volta. Virou
chave rotulada com nome, contagem de quantos estão no ar e estado marcado, mais
Ctrl+Alt+B. A contagem sobrevive à barra fechada, o que dá ao botão utilidade
mesmo para quem prefere trabalhar sem a barra aberta.

**"Projeto novo não é escaneado."** Não reproduziu: criei um projeto pela API e
a detecção rodou e persistiu. O `smartdash` estava mesmo sem stack, mas era
registro antigo — rodar a detecção nele preencheu tudo na hora. O que a
investigação achou foi a fragilidade que produziria exatamente esse sintoma: o
registry só continha `OSError`, e detector lê arquivo de projeto alheio, que vem
torto de dez jeitos com exceção de tipo próprio cada um. A que escapasse
derrubava o cadastro do projeto junto. A varredura do fallback não tinha
proteção nenhuma. Endurecido, e card sem stack passou a oferecer "Detectar
stack" num clique.

### Números

395 testes passando, 1 pulado. `ruff check` limpo. 44 arquivos,
+3476 e −127 linhas. Dependência nova: `psutil`.

| Commit | Entrega |
|--------|---------|
| `877ad5f` | Seis defeitos da varredura, com regressão para cada um |
| `74fd474` | Serviço desligado lia como erro; `serve.ps1` abortava na migração |
| `d7b80c6` | Descoberta de porta e o aviso de declarado contra observado |
| `84ab027` | Chave rotulada da barra de ativos; desligar confirmado por verificação |
| `a290e31` | Servidor de desenvolvimento pelo painel, sem terminal |

### A lição do dia

Três dos oito defeitos eram **código morto que parecia proteção**: o ramo de
timeout do TCP, a lista `FORBIDDEN_FLAGS` e o `compose_file` do manifesto. Os
três liam como se o cuidado estivesse tomado — havia constante, havia `except`,
havia coluna no banco — e nenhum dos três era executado alguma vez. Documentação
que mente é ruim; código que mente é pior, porque ninguém revisa duas vezes uma
guarda que já está lá.

O antídoto que funcionou foi banal: procurar por nome cada constante e cada
ramo, e conferir se alguém os alcança. `FORBIDDEN_FLAGS` aparecia uma vez no
repositório inteiro — na própria definição.

### Continuação: a orquestração Docker + app

A decisão que a seção anterior deixou aberta foi respondida no meio da sessão:
**o Docker abre os ambientes, o sistema pega os ambientes já construídos e
continua o processo.** Banco e fila em container; a aplicação nativa, com hot
reload, falando com eles.

**Quem é aplicação e quem é ambiente.** O bloco `run:` do manifesto decide.
Havendo `run:`, a aplicação é o comando dele e o Compose inteiro vira ambiente.
Não havendo, a aplicação é o próprio Compose.

Declaração explícita compõe; inferência não. O ZAPBOT tem `api`, `nginx` e
`worker` dentro do Compose: inferir "além dos containers, roda também o `npm run
dev`" subiria a aplicação duas vezes na mesma porta. Escrever quatro linhas no
manifesto é barato; desfazer um duplo start não é.

**A ordem, e a espera.** `compose up -d` primeiro, sempre — é idempotente, então
com tudo de pé retorna rápido e não mexe em nada. Depois a espera, depois a
aplicação. A ordem inversa quebra: aplicação antes do banco morre no primeiro
`connect`.

Esperar tempo fixo seria chute — um Postgres com banco vazio abre em dois
segundos, com trinta giga em vinte. Espera-se as portas dos serviços declarados
**que não são a aplicação**, com teto de 30 s. A porta do próprio app fica fora
por definição: ele ainda não subiu, e incluí-la estouraria o teto em toda
subida. Passado o teto, a aplicação sobe assim mesmo com aviso: travar o clique
para sempre é pior que deixá-la reclamar, que é o que ela faria no terminal.

**A assimetria do desligar.** "Desligar" para a aplicação; os containers ficam.
Banco e fila são caros de subir e não mudam entre uma execução e outra do
backend — derrubá-los a cada parada trocaria um ciclo de dois segundos por um de
trinta. Shift+clique derruba tudo, e o chip do Docker no card também. Quando o
projeto não tem aplicação separada, "Desligar" para o Compose, senão o botão não
faria nada.

**O chip do Docker existe por causa disso.** Com o botão falando só da
aplicação, parar o app deixaria o painel dizendo "Desligado" com o Postgres
atendendo na porta — a mesma confusão que o caso do ZAPBOT expôs. Pelo mesmo
motivo `ProjectSummary.app_running` é `None`, e não `false`, quando o projeto não
tem aplicação separada: `false` diria "parado" com a stack inteira no ar.

### O que o smartdash ensinou, rodando

Três defeitos que a leitura do código não pegaria, um a cada tentativa:

1. **Interpretador.** `plan_from_python` emitia `python` puro, que é o do PATH e
   tem as dependências de outra pessoa. Deu `ModuleNotFoundError: No module
   named 'duckdb'` — de uma biblioteca instalada, só que no `.venv` do projeto.
   Agora o `.venv` local é procurado primeiro.
2. **Caminho relativo de programa.** `CreateProcess` resolve caminho relativo
   contra o diretório do processo que **chama**, não contra o `cwd` do filho, e
   `.venv/Scripts/python.exe` no manifesto apontava para o lugar errado.
3. **Já estar no ar virava falha.** `up` com a aplicação rodando levantava
   `ServerAlreadyRunning` e marcava o job inteiro de vermelho — incluindo a
   etapa do Compose que tinha dado certo. Subir é idempotente por decisão.

Depois disso a sequência inteira funcionou:

    Subindo os containers (docker-compose.yml)…
     Container smartdash-db-1 Healthy
     Container smartdash-backend-1 Started
    Containers no ar.
    Esperando as dependências responderem: Database…
      Database respondeu.
    Dependências prontas.
    Aplicação no ar: .venv/Scripts/python.exe -m uvicorn backend.app.main:app --reload …

### Rede de proteção nova nos testes

Escrever `test_environment.py` subiu um `node` de verdade num diretório
temporário do pytest — e ele **sobreviveria ao pytest**, que é o que o
`CREATE_NEW_PROCESS_GROUP` garante de propósito. O `conftest` já barrava execução
real em job; o servidor de desenvolvimento não passa pelo `JobManager` e escapava
da rede. Agora `start_background` também é barrado fora de teste `integration`.

### A bateria no browser, e os três defeitos que ela achou

Doze testes: ligar e desligar pelo botão, o "Abrir", o chip do Docker nos dois
estados, o trilho por clique e por Ctrl+Alt+B, as seis telas, e o "Detectar
stack" num projeto sem nada reconhecível e depois com `package.json`. Nenhum erro
de console.

**A sugestão de porta podia criar o conflito que ela existe para apontar.**
`_mismatches` sugeria a mesma porta observada para todos os serviços divergentes
do projeto. Com o SmartDash declarando 3004 e 3005 e uma só porta sua no ar, a
tela oferecia "Usar 8000" nas duas linhas — inclusive na do banco. Agora uma
porta observada só pode ser sugerida a um serviço, e com ambiguidade a
divergência aparece sem sugestão, com um botão "Corrigir". Dizer "está errado"
sem chutar o certo é honesto; chutar errado custa uma porta trocada à toa.

**Porta de container não era atribuída a projeto nenhum.** O `cwd` do Docker
aponta para a instalação dele, então nenhuma regra de atribuição casava. O banco
do SmartDash aparecia como "sem dono" e o serviço declarado virava divergência —
alarme falso justamente na configuração que o painel recomenda. Sobra o número:
se um único projeto declara aquela porta, foi o Compose dele que a publicou.
Declarada por dois, ninguém é atribuído.

**O card sabia ligar e não sabia abrir.** Depois de ligar, a próxima coisa que se
quer é ver, e "Abrir" só existia na página do projeto. O card ganhou o botão, com
a **chave** do serviço e nunca a URL — quem abre é o backend, e aceitar URL do
cliente reabriria o vetor que a decisão D-13 fecha.

### Um susto que não era bug

Durante a verificação, um `python.exe` com o caminho do interpretador global
aparecia segurando a porta 8000, e por um momento pareceu processo órfão dos
testes anteriores. Não era: o pid era filho do processo do `.venv`, e no Windows
o `python.exe` de um ambiente virtual é um redirecionamento para o base — as
dependências do venv estavam lá, tanto que o `duckdb` importou. Árvore só,
saudável.

Vale registrar porque o caminho no `cmdline` de um processo em venv no Windows
**não** identifica o ambiente que ele está usando, e concluir o contrário custou
uma investigação.

### Números finais da sessão

413 testes passando, 1 pulado. `ruff check` limpo. 50 arquivos, +5067 e −146
linhas. Dependência nova: `psutil`.

| Commit | Entrega |
|--------|---------|
| `877ad5f` | Seis defeitos da varredura, com regressão para cada um |
| `74fd474` | Serviço desligado lia como erro; `serve.ps1` abortava na migração |
| `d7b80c6` | Descoberta de porta e o aviso de declarado contra observado |
| `84ab027` | Chave rotulada da barra de ativos; desligar confirmado por verificação |
| `a290e31` | Servidor de desenvolvimento pelo painel, sem terminal |
| `72d8895` | Orquestração: um clique sobe ambiente e app, na ordem |
| `0e6d8df` | Sugestão de porta criava conflito; card ganhou "Abrir" |

### A segunda lição do dia

A primeira foi sobre código morto que parece proteção. A segunda é sobre onde os
defeitos moram: dos onze problemas desta sessão, **seis só apareceram rodando** —
`npm.CMD` e `PATHEXT`, `DETACHED_PROCESS` engolindo o log, caminho relativo
resolvido contra o diretório errado, interpretador do venv, sugestão de porta
duplicada, card sem botão de abrir. Nenhum deles é visível lendo o código, e
quatro deles o teste unitário também não pegaria, porque o defeito estava na
fronteira com o sistema operacional ou no que a tela oferece.

O que os pegou foi sempre a mesma coisa: subir o servidor de verdade, clicar no
browser de verdade, e olhar o que aconteceu.

---

