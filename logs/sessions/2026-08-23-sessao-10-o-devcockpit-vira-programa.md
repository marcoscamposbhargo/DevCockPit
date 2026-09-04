## 2026-08-23 — Sessão 10: o DevCockpit vira programa

Pedido: "vamos fazer um executável". Três escolhas definiram o resto — pasta
com `.exe` (não arquivo único), dados ao lado do executável (não em
`%LOCALAPPDATA%`), console visível abrindo o navegador.

### O que o executável precisa fazer que o repositório não precisava

`uvicorn app.main:app` pressupõe repositório clonado, ambiente virtual, `.env`
copiado, `alembic upgrade head` rodado à mão e `configs/roots.yml` editado. Um
programa aberto com dois cliques não tem nada disso. `app/launcher.py` faz cada
um desses passos, nesta ordem: descobre a pasta de dados, semeia a
configuração, migra, escolhe a porta, sobe e abre o navegador.

Dois pontos mereceram cuidado:

* **os recursos e os dados moram em lugares diferentes.** Congelado, o código
  roda de um diretório temporário (`sys._MEIPASS`) que some ao fechar; frontend
  e migrações vivem lá, e banco, log e configuração precisam viver ao lado do
  `.exe`. `PROJECT_ROOT` passou a apontar para os recursos, e o launcher
  entrega os caminhos de dados por variável de ambiente, absolutos, com
  `setdefault` — quem já configurou continua mandando;
* **`roots.yml` não pode ser cópia.** O arquivo do repositório aponta para o
  Desktop de quem desenvolveu. Ele é escrito a partir do perfil de quem está
  executando, e só com as pastas que existem: allowlist para diretório
  inexistente produz erro de varredura em vez de lista vazia honesta.

### O defeito que o teste pegou, e que ninguém veria na primeira tela

A porta 8765 pode estar ocupada, então o launcher pega a próxima livre. Só que
a porta não é apenas onde o servidor escuta: ela entra na lista de origens
aceitas em requisição que altera estado (defesa D5). Subindo em 8801 com as
`Settings` ainda dizendo 8765, a tela carregava perfeitamente e **todo botão
devolvia 403** — o pior jeito de quebrar, porque parece que funciona.

Achado com um POST contra o executável recém-gerado, não lendo código. A
correção é uma linha (`DEVCOCKPIT_PORT` antes de qualquer leitura de settings)
e tem teste que falha sem ela.

### Detalhes que só aparecem rodando

* console do Windows herda codepage 850/1252, e "migrações" saía com
  caracteres trocados. `SetConsoleOutputCP(65001)` mais reconfiguração dos
  fluxos;
* falha na subida fecharia a janela antes de a mensagem ser lida — em erro, e
  só quando há alguém do outro lado, o launcher espera um Enter;
* o build apaga `data/`, `logs/` e `configs/` de dentro de `dist` antes de
  empacotar: um banco esquecido ali viajaria com os projetos da minha máquina
  para quem recebesse a pasta.

### Medições

Pacote de 39,7 MB. Primeira abertura em pasta nova: 3,4 s (inclui migração e a
varredura do antivírus nos arquivos novos). Aberturas seguintes: 1,4 s. Testado
copiando a pasta para fora do repositório e subindo de lá — cadastro de projeto
funcionando, detecção de stack correta, `/api/analytics` respondendo.

483 testes passando (8 novos), `ruff check` limpo.

### Continua com você

- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques e conferir o
      caminho completo: navegador abre sozinho, painel carrega, um botão que
      escreve (fixar projeto, por exemplo) funciona
- [ ] decidir se `dist/` fica fora do Git (está, hoje) ou se as versões viram
      release versionada
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

## 2026-08-23 — Sessão 10, continuação: três ajustes depois de usar

Nada aqui foi planejado; os três vieram de olhar a tela com o que tinha acabado
de ser construído.

### "Falha na requisição (404)" no painel de análise

O arquivo novo estava no disco e a rota existia. O servidor no ar tinha subido
às 23:20 — antes de `/api/analytics` ser escrita — e seguia com o código antigo
em memória. Reiniciar resolveu.

O que ficou do episódio não é a correção, é a mensagem. `Falha na requisição
(404)` mandava procurar no lugar errado: sugere dado ausente, quando o problema
é processo desatualizado. Recarregar a página não resolve, e é a primeira coisa
que qualquer um tenta. O painel agora distingue o 404 e diz o que fazer —
reiniciar o servidor, não recarregar a aba.

Vale como padrão: **erro de rota inexistente num painel novo quase sempre é
servidor velho.** É o modo de falhar mais provável de qualquer feature nova
neste projeto, porque o servidor é de vida longa por decisão (`serve.ps1`).

### Dois painéis saíram do dashboard

A pedido: "Disponibilidade" e "Ações mais executadas". Ficaram três — Atividade,
Horário de trabalho e Stack dos projetos.

Junto foram as funções que só existiam para eles (`disponibilidade`, `acoes`,
o helper `duracao`), o gráfico `lineSeries` de `charts.js` e o CSS `.serie`.
Sobrariam como código morto, e este projeto já tem um item de backlog inteiro
sobre o custo de manter o que ninguém usa.

O que **não** saiu, de propósito: o backend continua calculando `uptime` e
`actions`, e o poller continua gravando `health_snapshot`. Parar a gravação
devolveria a tabela ao estado que a sessão anterior corrigiu — schema sem
escrita — e sem histórico acumulado o painel não teria como voltar.

### O executável estava velho

Empacotado antes da remoção dos painéis. Reempacotado e conferido a partir de
uma cópia fora do repositório: `/api/health`, a página e `/api/analytics`
respondendo 200, e o JS servido pelo `.exe` sem vestígio dos painéis retirados.

A lição é operacional e vale anotar: **o executável não se atualiza sozinho.**
Toda alteração de código exige `scripts/build_exe.ps1` de novo, senão a pasta
`dist` mostra uma versão do painel que não existe mais no repositório.

### Continua com você

- [ ] Ctrl+F5 na aba aberta e conferir os três painéis que sobraram
- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques: navegador abre
      sozinho, painel carrega, um botão que escreve funciona
- [ ] decidir se `dist/` fica fora do Git (está) ou vira release versionada
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

