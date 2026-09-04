## 2026-09-02 — Sessão 34: o console que piscava

O pedido não veio como bug do DevCockpit: "ainda tá piscando um terminal, veja
se é algum do projeto DevCockpit?". Era.

### O que estava acontecendo

O log entregou a resposta antes de qualquer palpite. `system.temperature`
rodando `powershell.exe` a cada 30 segundos exatos, e `docker.ps.global` junto:
183 e 151 execuções em uma hora e meia. Cada uma abrindo um console.

A causa estava no `command_runner`: os filhos nasciam com
`CREATE_NEW_PROCESS_GROUP` e nada mais. Sem `CREATE_NO_WINDOW`, o Windows aloca
console para cada processo — e o polling nunca para.

O projeto já sabia disso. O `background.py` faz certo desde sempre, com
comentário explicando a escolha. Faltou aplicar nos outros três pontos:
`_run_and_wait`, o `CREATION_FLAGS` do `process.py` e o `taskkill`. O
`_run_detached` ficou intacto de propósito — ali a janela é o produto, é o
terminal que a pessoa mandou abrir.

### As pendências que vieram junto

A investigação descobriu duas coisas que não eram o pedido:

1. **`devcockpit.log` com 57 MB**, sem rotação. O handler era um `FileHandler`
   simples. Virou `RotatingFileHandler`, 10 MB por arquivo e 5 backups — o log
   inteiro cabe em ~60 MB. Ao subir o build novo, os 57 MB rotacionaram sozinhos
   na primeira escrita, o que serviu de prova em produção.
2. **A causa do volume**: `GET /api/system/metrics` a cada 3 segundos era 64% do
   log de acesso; com `/api/health`, mais de 70%. Um filtro passou a descartar
   essas rotas **só quando dão certo** — erro nelas continua gravado, que é
   quando a linha vale alguma coisa.

O `build_exe.ps1 -Install` também quebrou duas vezes, e não por culpa do
projeto: o VS Code mantém `_internal\VCRUNTIME140.dll` mapeada enquanto o
repositório está aberto nele, e `Remove-Item` não apaga arquivo sob lock.
Renomear funciona. O script agora encerra o DevCockpit sozinho e renomeia o que
estiver travado em vez de morrer no meio da instalação.

### Situação ao encerrar

Publicado até `5fa9355` mais o commit desta rodada. 736 testes passando. O
executável instalado é o build corrigido, com `data\`, `logs\` e `configs\`
preservados nas três reinstalações.

Medições que sustentam o fim do problema: 75 segundos de polling com o build
novo e a contagem de `conhost` parada em 13 — antes nasceriam cerca de cinco
janelas nesse intervalo. E no log da instância atual, zero linhas de `metrics`
ou `health`, com `system.temperature` e `docker.ps` seguindo registrados.

O `docker ps` que aparecia falhando no diagnóstico inicial era só o Docker
parado naquele momento; voltou a `SUCCESS` assim que o usuário o abriu.

### Próximo passo

Nada aberto desta linha. O que a sessão 33 deixou continua valendo: **HyperBrain
MVP 3 e MVP 4**, e a conversa sobre o MVP 5 e a Fase 5 do Cockpit AI antes de
qualquer código.

Uma observação para quem voltar aqui: a confirmação visual do fim do piscar é do
usuário, não minha. Eu medi processo e log; quem olha o desktop é ele.

