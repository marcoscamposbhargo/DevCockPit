## 2026-08-22 — Sessão 7: o painel deixa de só informar e passa a operar

Continuação direta da sessão 6, no mesmo dia. A pergunta que abriu foi "o que
podemos melhorar?", e a resposta veio de olhar o estado real em vez de opinar:
cobertura em 90%, 420 testes, e três buracos que o uso já tinha mostrado.

### O console que faltava

O painel sabia subir `npm run dev` e `uvicorn` desde a sessão 6, e a saída ia
para arquivo — mas **nenhuma tela mostrava esse arquivo**. Quando um servidor não
subia, o painel dizia "desligado" e a razão (`ModuleNotFoundError: No module
named 'duckdb'`, em texto claro, no disco) não tinha caminho até os olhos de
ninguém. Aconteceu de verdade, e a resposta exigiu um `curl`.

A aba Server mostra três coisas, nesta ordem de importância: o **comando antes
do clique**, com de onde ele veio ("declarado no devcockpit.yml", "deduzido do
package.json"); a **saída**, ao vivo e também depois da queda; e os controles,
que são consequência das duas primeiras. Vem antes de Docker na barra de abas
porque é a aba do dia a dia.

**Por que polling e não stream.** O backend lê o fim do arquivo sob demanda.
Fazer SSE custaria acompanhar o arquivo no servidor, e o ganho seria o atraso
cair de um segundo para zero — num texto que se lê em dezenas de segundos.

O visor substitui o texto em vez de anexar: a fonte é "as últimas N linhas", não
"o que mudou". Deduzir o delta comparando textos erraria em toda linha repetida,
e log de servidor repete muito. Só toca no DOM quando o texto mudou — senão cada
volta do relógio destruiria a seleção de quem estivesse copiando uma linha de
erro.

Junto vieram **Reiniciar** (o gesto mais repetido de um dia de backend, que
custava dois cliques e uma espera) e a **rotação do log** (o arquivo era aberto
em append e nunca truncado; a leitura já lê só o fim, então ninguém percebia —
o disco percebia).

### Cinco defeitos achados olhando a tela

Nenhum deles apareceria lendo o código.

**A sugestão de porta podia criar o conflito que ela existe para apontar.**
`_mismatches` sugeria a mesma porta observada para todos os serviços divergentes
do projeto: com o SmartDash declarando 3004 e 3005 e uma só porta sua no ar, a
tela oferecia "Usar 8000" nas duas linhas — inclusive na do banco. Aceitar as
duas colocaria backend e Database na mesma porta. Agora uma porta observada só
pode ser sugerida a um serviço, e com ambiguidade a divergência aparece **sem**
sugestão, com um botão "Corrigir". Dizer "está errado" sem chutar o certo é
honesto; chutar errado custa uma porta trocada à toa.

**Aplicação parada virava "porta errada".** A regra dizia: se o projeto tem
alguma porta escutando, todo serviço fora dela está com o número errado. Isso
ficou falso assim que porta de container passou a ser atribuída ao projeto — um
projeto com o banco em container e a aplicação desligada acusava o backend, que
só estava parado. Metade dos projetos está assim em qualquer momento do dia.
Agora só há divergência quando alguma porta do projeto escuta **sem que serviço
declarado nenhum a explique**.

**Porta de container não era atribuída a ninguém.** O `cwd` do Docker aponta
para a instalação dele, então nenhuma regra casava. Sobra o número: se um único
projeto declara aquela porta, foi o Compose dele que a publicou.

**"Port is already allocated" não dizia por quem.** A falha mais comum do
`compose up` e a mais inútil como o Docker a entrega. O painel agora nomeia o
culpado, usando o que a descoberta de porta já sabia.

**O card sabia ligar e não sabia abrir.** Depois de ligar, a próxima coisa que
se quer é ver, e "Abrir" só existia na página do projeto.

E o botão "Abrir" que eu acabara de adicionar **quebrou o rodapé do card**:
itens demais para uma fileira, o `flex-wrap` quebrava onde dava e o carimbo de
tempo ficava órfão no meio. Viraram duas fileiras de propósito — estado em cima,
ferramentas embaixo. De quebra, `.card__actions` mantinha `align-items: center`
de quando era uma linha só; virando coluna, aquilo passou a centralizar as
fileiras inteiras.

### O trilho abria o serviço com a chave vazia

`service_key: Field required`, num botão perfeitamente clicável. O trilho manda
a **chave** do serviço — contrato da rota, nunca a URL (decisão D-13) —, mas o
dashboard, que alimenta o trilho, devolvia `label`, `url`, `port` e não a chave.
Ia `undefined`.

Rótulo não serve no lugar: é texto para humano e pode repetir entre serviços do
mesmo projeto.

### Remover projeto deixava o servidor órfão

O processo sobrevive ao painel de propósito, e a linha em `dev_server` é o único
lugar onde o PID existe. Apagar o projeto apagava esse PID: sobrava um `uvicorn`
segurando a porta, alcançável só pelo Gerenciador de Tarefas, e sem caminho de
volta porque o projeto já tinha sumido da tela.

Falha em encerrar **não** trava a remoção: travar por um processo teimoso
deixaria o usuário com um projeto que ele não consegue tirar da tela — trocar um
problema por um pior.

### As três telas revisadas

**Activity era um muro.** Cento e sessenta e cinco linhas em ordem cronológica,
sem filtro, com `system.browser` repetindo dezenas de vezes e as falhas perdidas
no meio. A API aceitava `project_id`, `action` e `status` desde sempre — a tela é
que não perguntava. Ganhou filtros com "Só problemas" em primeiro lugar (é o
motivo número um de abrir a tela), agrupamento por dia, e falha com faixa na
borda. A ação virou português, com o nome técnico no tooltip.

**Settings não mostrava o que estava rodando.** Saber isso exigia abrir projeto
por projeto — e, no fim do dia, lembrar quais foram. Como o processo sobrevive a
um reinício do painel, esquecer um significa deixá-lo de pé até alguém notar.

**Dashboard respondia "quantos" e nunca "quais".** "2 Parados" era informação sem
saída. Agora cada número leva à lista já recortada; zero não vira link, porque
link para lista vazia é promessa quebrada. E o painel "Alterações pendentes: 0 —
nenhuma alteração conhecida" saiu da tela: o cache de Git só enche quando alguém
abre a aba Git, então ele ficava permanentemente ocupando um quarto da tela para
dizer "não sei".

### O dashboard deixa de ser só leitura

O gesto da manhã — "ligar o que vou usar hoje" — obrigava a sair da tela, ir a
Projects e procurar na grade. Um painel de operação sem operação é um relatório.
"Retomar trabalho" lista os que **não** estão no ar, com a chave de ligar na
frente.

### Gráficos, e o que a máquina deixa medir

Quatro medidores — processador, memória, disco, temperatura — e duas linhas de
três minutos. Um número responde "agora"; a linha responde "e antes?". Oitenta
por cento de memória constante há uma hora é rotina; subindo há cinco minutos é
aviso.

A tabela por servidor é o que só este painel sabe responder: o Gerenciador de
Tarefas mostra dezoito `node.exe` sem dono, e aqui cada árvore tem projeto,
porque foi o painel que a subiu. A medição soma a árvore inteira — `npm run dev`
é um `cmd.exe` que gasta zero e um `node` que gasta tudo, e medir só o pai
mostraria 0% num servidor fritando a máquina.

**Sobre a temperatura, com honestidade.** `MSAcpi_ThermalZoneTemperature`
responde "Acesso negado" sem privilégio administrativo, e o painel não pede
privilégio para nada. O que sobra é
`Win32_PerfFormattedData_Counters_ThermalZoneInformation`: a zona térmica ACPI,
que é a placa e não o núcleo. Marca bem menos que um HWMonitor, e chamá-la de
"CPU" seria mentira — o rótulo diz "zona térmica". Máquina sem zona exposta
mostra "—", nunca zero.

Duas cadências, porque os custos diferem por ordens de grandeza: `psutil`
responde processador, memória e disco em milissegundos; a temperatura exige
subir um `powershell.exe`, medido em **341 ms**, e por isso tem cache de trinta
segundos. Misturar faria a leitura barata pagar o preço da cara.

Gráficos em SVG escritos à mão. O painel não tem nenhuma dependência de
frontend, e trazer uma para desenhar uma linha e um arco seria caro. SVG e não
canvas porque as cores vêm do tema: trocar claro para escuro não exige
redesenhar nada.

### O conserto que quebrou o que consertava

O relógio do painel da máquina continuava batendo depois de sair do dashboard,
consultando a máquina a cada três segundos para desenhar num container fora do
DOM. Passou a perguntar ao próprio elemento se ainda está na página.

O conserto quebrou o painel: a primeira leitura acontece **antes** de o elemento
ser montado — quem chama monta a tela depois de pedir o painel —, então ele se
desligava na partida e a tela ficava para sempre em "Lendo o estado da
máquina…". Daí a ressalva de só desligar depois de ter estado montado alguma vez.

Verificado interceptando as requisições: três chamadas em oito segundos no
dashboard, zero em doze segundos fora dele.

### Números

426 testes passando, 1 pulado. `ruff check` limpo. Desde o log da sessão 6:
31 arquivos, +2974 e −130 linhas. Na branch inteira: 65 arquivos, +8162 e −252.

| Commit | Entrega |
|--------|---------|
| `41918fc` | Aplicação parada virava divergência; porta ocupada não dizia por quem |
| `a659df1` | Aba Server, com log ao vivo, Reiniciar e rotação |
| `8f5886b` | Atalhos descobríveis com `?`; portas do dashboard com estado |
| `4da6ebd` | Rodapé do card em duas fileiras, alinhado à esquerda |
| `dd0df42` | Abrir pelo trilho falhava por falta da chave do serviço |
| `794dc51` | Remover projeto deixava o servidor órfão |
| `1e0fc87` | Activity com filtros, por dia, falha em destaque |
| `918bce7` | Capturas de verificação fora do repositório |
| `eeb2e9c` | Settings mostra os servidores no ar |
| `2461e24` | Números do dashboard levam à lista; painel vazio saiu |
| `aa7d923` | Dashboard opera, e mostra o estado da máquina |

### Três correções que precisei fazer no meio do caminho

Vale registrar porque são o tipo de erro que se repete:

1. **Afirmei que havia processo órfão** segurando a porta 8000. Não havia: o pid
   com caminho do Python global era filho do processo do `.venv`, e no Windows o
   `python.exe` de um ambiente virtual é um redirecionamento para o base. O
   `cmdline` de um processo em venv **não** identifica o ambiente que ele usa.
2. **Afirmei que `localhost:8137` no dashboard era texto morto.** Era link com
   `target="_blank"` desde antes.
3. **Commitei capturas de tela** junto com a Activity, por um `git add -A`
   descuidado.

Os três têm a mesma raiz: concluir antes de conferir. Nos três, conferir custava
menos de um minuto.

### A lição do dia

A das sessões anteriores foi sobre onde os defeitos moram. Esta é sobre o que os
esconde: **quase todo defeito desta sessão era a tela sabendo de algo e não
dizendo**. A API aceitava filtros e a Activity não perguntava. A descoberta de
porta sabia quem ocupava a porta e o erro do Compose não usava. O log existia em
disco e nenhuma tela o abria. Os atalhos funcionavam e nada os anunciava. Os
números do dashboard sabiam a resposta e não levavam a ela.

Nenhum desses é bug de lógica. São informação represada por falta de um caminho
— e o custo de abrir cada caminho foi pequeno perto do que ele destrava.

### Continua com você

- [ ] `git_service` está com 47% de cobertura, o menor do projeto — `commits`,
      `branches` e `remotes` não são exercitados
- [ ] duas tabelas com migração que nada escreve nem lê (`HealthSnapshot`,
      `GitRepository`) e duas configurações nunca consultadas
      (`activity_retention_days`, `timeout_scan`). Implementar ou apagar;
      manter é o pior dos três
- [ ] zero teste de frontend, contra 4600 linhas de Python a 90% — e os últimos
      defeitos foram todos de frontend
- [ ] declarar `run:` no `devcockpit.yml` do `zapcrm`
- [ ] a porta declarada do `Dashdate · Backend` é 3002 e ele está no ar em 8123
- [ ] clicar em VS Code e confirmar que a janela vem para frente (pendente
      desde 22)
- [ ] conferir a aba Docker com o Docker Desktop desligado (pendente desde 21)
- [ ] decidir se a branch `varredura/bugs-e-organizacao` entra na `main` — são
      21 commits fora dela

---

