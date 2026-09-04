## 2026-08-23 (manhã, parte 2) — Sessão 12: o painel vira aplicativo

Três pedidos numa linha: atalho no Desktop, porta estável e "uma janela
flutuante, como um sistema interno mesmo". O terceiro mudou o que o executável é.

### Antes de tudo: tirar o programa de dentro de `dist`

Você estava rodando o executável de `dist/DevCockpit`, e o banco com os 36
projetos varridos vivia lá dentro. `build_exe.ps1 -Clean` apaga essa pasta.
Um rebuild teria levado o cadastro inteiro junto, sem aviso.

O programa foi para `%USERPROFILE%\DevCockpit`, e o script ganhou `-Install`:
substitui só o `.exe` e o `_internal/`, nunca `data/`, `logs/` e `configs/`.
Atualizar não pode custar o que o usuário cadastrou.

### Dois painéis, dois bancos

A tela de Ports que você mandou não era do servidor de desenvolvimento: era do
executável, com 36 projetos. O do repositório tinha 3. Consequência direta de
"dados ao lado do executável" — desenho correto, efeito confuso quando os dois
rodam ao mesmo tempo. Ficou um só de pé: o instalado, na 8790.

### Janela nativa

WebView2 via `pywebview`. Sem barra de endereço, sem abas, ícone próprio na
barra de tarefas, título "DevCockpit". Fechar a janela encerra o servidor — um
programa que continua rodando invisível depois de fechado é a receita da segunda
instância brigando pela porta, que é exatamente o problema que passamos a manhã
resolvendo.

O servidor mudou de thread: o laço de mensagens do Windows exige a thread
principal para a janela, então o uvicorn foi para uma secundária, com
`install_signal_handlers` desligado (`signal.signal` só funciona na principal).

### O preço do console, cobrado na hora

Empacotei com `console=False` e o app subiu... sem servidor. Janela abrindo
contra o nada, e **nenhuma mensagem em lugar nenhum**.

Causa: sem console, `sys.stdout` é `None`, e a configuração de log padrão do
uvicorn monta um `StreamHandler` sobre `ext://sys.stdout`. Ela levanta antes de
a porta abrir, a thread morre, e a exceção não tinha para onde ir.

Três correções, e as três são sobre o mesmo tema — não trocar visibilidade por
aparência:

* `log_config=None` quando não há `stdout` (o log da aplicação já vai para
  arquivo, ao lado do executável);
* a thread do servidor guarda a exceção que a matou, em vez de morrer calada;
* `_falhar()` mostra caixa de diálogo do Windows quando não há console, e
  `_dizer()` não escreve em `stdout` inexistente — um `print` solto derrubaria a
  subida por causa da mensagem, não do trabalho.

Eu tinha escrito, ontem, que o console visível era proposital porque "é onde
aparece o motivo quando o servidor não sobe". Trocar isso por uma janela exigia
repor a visibilidade por outro caminho. Custou uma reconstrução para lembrar.

### Ícone

Gerado por código (`scripts/make_icon.py`, Pillow) e não versionado como binário
opaco: arco de gauge nas cores dos tokens do tema, com o ponto verde de "no ar".
Trocar a identidade é trocar duas constantes e rodar de novo.

### Verificado

Atalho no Desktop apontando para `%USERPROFILE%\DevCockpit\DevCockpit.exe
--port 8790`, ícone próprio. Aberto pelo atalho: `health` 200, janela com título
"DevCockpit", 19 processos do WebView2. Fechando a janela: processo encerrado e
porta liberada. 483 testes passando, `ruff` limpo.

### Continua com você

- [ ] abrir pelo atalho e dizer se a janela está no tamanho certo (1360x880)
- [ ] o cadastro do próprio DevCockpit agora aponta para a 8790
- [ ] os 5 "conflitos" de porta da tela Ports são portas padrão declaradas por
      vários projetos; só doem entre projetos que sobem juntos. Decidir se vale
      renumerar (mexe no arquivo de cada projeto, não só no cadastro)
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

