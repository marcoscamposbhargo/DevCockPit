## 2026-08-27 (noite) — Sessão 29: o executável alcança o repositório

Sessão curta, dois itens: levar as correções da tarde para o painel instalado e
desfazer o cadastro torto do AgilContabil.

### Reinstalação, e a armadilha da quarta vez

O painel estava rodando na **8790**, não na 8765: quando ele subiu, a 8765
ainda estava ocupada pela instância da tarde, e ele escolheu outra. Vale saber
disso antes de concluir que o painel está fora do ar.

O `robocopy /MIR` travou por cinco minutos. Causa: **um DevCockpit voltou a
subir** depois que eu parei o anterior, segurando o `_internal` inteiro — e o
robocopy tenta de novo um milhão de vezes, esperando 30 s entre elas, por
padrão. Com `/R:2 /W:1` o problema vira erro em segundos em vez de espera
indefinida.

O `VCRUNTIME140.dll` seguia travado, agora pelo VS Code. Hash idêntico, então
continua fora do espelhamento (`/XF`), com conferência arquivo a arquivo depois:
**0 faltando**, e o `.exe` com hash igual ao do build.

### O cadastro do AgilContabil

O projeto já tinha a verdade escrita em `infra/.env`, e ninguém tinha olhado
lá: `POSTGRES_PORT=5442`, `MINIO_PORT=9010`, `MINIO_CONSOLE_PORT=9011`,
`BACKEND_PORT=8100`.

O cadastro dizia outra coisa — três serviços na porta 3000, rótulos citando
portas que não eram as deles, e o Postgres marcado como **HTTP**, o que sozinho
já garantiria verificação falhada para sempre.

Decisão do usuário: backend em **8100**, a mesma do Compose. Vale para as duas
formas de subir; se o container e o servidor nativo forem ligados juntos, o
segundo não sobe — e esse é o aviso correto, não um defeito.

| | antes | depois |
|---|---|---|
| Backend | `App (5442)` · 3000 · HTTP | `Backend` · 8100 · HTTP |
| Postgres | `App (5442)` · 3000 · HTTP | `Postgres` · 5442 · **TCP** |
| MinIO | `App (9010)` · 3000 · HTTP | `MinIO` · 9010 · HTTP |
| Console | `App (9011)` · 3010 · HTTP | `MinIO Console` · 9011 · HTTP |

### O que os três consertos da tarde provaram valer, no painel real

1. **O comando seguiu o cadastro sozinho:** virou `--port 8100`, e **pulou o
   Postgres** porque agora é TCP. Era exatamente para isso que `_declared_port`
   passou a ignorar serviço TCP — sem isso, mandaria o `uvicorn` subir na porta
   do banco.
2. **A auditoria registrou `services.replace`**, que antes não deixava rastro
   nenhum.
3. **Porta duplicada foi recusada com `422`** e mensagem dizendo de quem é a
   porta, com o cadastro intacto depois da recusa — nada gravado pela metade.

E o fim da linha: `server.start` subiu o backend na 8100, `/docs` respondeu
`200`, e os quatro serviços do projeto ficaram **ONLINE**. É o mesmo projeto que
abria a sessão passada dizendo "0/4 online".

Um susto no caminho: a primeira verificação deu `OFFLINE` nos três containers. O
`docker ps` mostrou `Up Less than a second` — estavam reiniciando naquele
instante. Segunda verificação, todos no ar.

### Situação ao encerrar

Painel instalado **igual ao build**, rodando na 8765 com as correções de hoje.
681 testes, ruff limpo, árvore publicada.

No ar agora: backend do AgilContabil (nativo, 8100), containers `postgres` e
`minio` do mesmo projeto, e `eventos_api`/`eventos_db`, que não são desta sessão.

### Próximo passo

O cadastro de porta dos **outros 18 projetos** nunca foi conferido contra o que
cada um declara em `.env` ou Compose. O AgilContabil só apareceu porque quebrou
na cara. Vale uma varredura que compare cadastro × arquivo do projeto e liste as
divergências — sem corrigir nada sozinha, porque a decisão de qual número vale é
de quem conhece o projeto.

