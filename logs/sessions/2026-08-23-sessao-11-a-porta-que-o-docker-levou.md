## 2026-08-23 (manhã) — Sessão 11: a porta que o Docker levou

O painel não subia. O log dizia tudo, e nada:

```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8765)
```

Quem estava escutando na 8765 era o `com.docker.backend.exe`. Ele tomou a porta
durante a noite, com o DevCockpit parado — nenhuma configuração mudou de lado
nenhum. Foi o mesmo padrão de sempre neste projeto: a máquina é compartilhada, e
o que estava livre ontem pode não estar hoje.

### O defeito que apareceu enquanto eu contornava

Subi em 8766 para destravar. A tela carregou, e o primeiro POST devolveu **403
`Origin não autorizado`**.

`serve.ps1 -Port` passava a porta ao uvicorn e não às `Settings`. A porta não é
só onde o servidor escuta: ela compõe a lista de origens aceitas em requisição
que altera estado (defesa D5). Subir em 8766 com as `Settings` dizendo 8765
carrega a tela inteira e recusa todo botão.

É **exatamente** o mesmo defeito que o executável teve ontem, corrigido ontem,
no arquivo ao lado. Eu consertei o launcher e não olhei para os dois scripts que
faziam a mesma coisa. Anotado como padrão: quando a correção for "propagar a
porta escolhida", procurar todos os pontos que escolhem porta — hoje são três.

### Ceder em vez de disputar

Decisão sua: fallback automático nos dois scripts. `serve.ps1` e `dev.ps1`
procuram a primeira porta livre a partir da 8765, exportam `DEVCOCKPIT_PORT` e
imprimem qual usaram.

Um efeito colateral precisou de conserto junto: `Get-ServerProcesses` casava por
`--port 8765` na linha de comando. Com fallback, o servidor podendo estar em
8766 faria `-Status` responder PARADO e `-Stop` não parar nada — com o painel de
pé o tempo todo. A busca passou a ignorar a porta, e a porta real é lida da
linha de comando do processo encontrado.

Verificado: `-Status` achou o servidor em 8766 sem receber a porta, `-Stop`
parou, a subida sem argumento caiu sozinha na 8766 avisando, e o POST que antes
dava 403 devolveu 409 `PROJECT_ALREADY_EXISTS` — passou pelo guard.

### Continua com você

- [ ] o painel de hoje está em **http://127.0.0.1:8766** (8765 é do Docker)
- [ ] Ctrl+F5 e conferir os três painéis de análise
- [ ] abrir `dist/DevCockpit/DevCockpit.exe` com dois cliques
- [ ] decidir se a porta padrão muda de vez (hoje: 8765 com fallback)
- [ ] zero teste de frontend continua sendo o maior buraco
- [ ] `git_service` a 47%
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

