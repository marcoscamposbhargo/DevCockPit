# 07 — Modelo de Segurança

Este é o documento mais importante do projeto. O DevCockpit executa comandos na
máquina do desenvolvedor. Uma falha aqui não é bug: é execução remota de código
na estação de trabalho.

## Modelo de ameaça

O DevCockpit é local e single-user. Isso **não** o torna seguro por padrão. As
ameaças reais:

| # | Ameaça | Vetor | Severidade |
|---|--------|-------|------------|
| T1 | Página web maliciosa aberta no browser dispara ações na API | o browser do usuário alcança `127.0.0.1`; CSRF | Crítica |
| T2 | Exposição na rede local | bind acidental em `0.0.0.0` + firewall permissivo | Crítica |
| T3 | Injeção de comando | argumento do cliente concatenado em string de shell | Crítica |
| T4 | Path traversal | path arbitrário levando ação de SO a diretório fora de escopo | Alta |
| T5 | Escape por symlink | diretório dentro do root apontando para fora | Média |
| T6 | Vazamento de segredo | `.env` do projeto alvo lido e exibido; token no log | Alta |
| T7 | Ação destrutiva acidental | `git reset`, `docker down -v`, remoção de volume | Alta |
| T8 | Exaustão de recurso | varredura de disco ilimitada; processo travado sem timeout | Média |
| T9 | DNS rebinding | domínio do atacante resolvido para `127.0.0.1`; o browser trata a requisição como same-origin e envia cabeçalho customizado sem preflight | Crítica |

T1 é a ameaça subestimada com mais frequência em ferramenta local. Qualquer aba
aberta pode fazer `fetch("http://127.0.0.1:8765/api/projects/x/docker/down")`.
"É localhost" não é defesa.

T9 é a variante que derrota a defesa ingênua contra T1. O atacante aponta
`evil.com` para `127.0.0.1` com TTL curto; a página carrega, o DNS reamarra, e
as requisições seguintes saem para o DevCockpit sendo tratadas pelo browser
como same-origin — sem preflight, com cabeçalho customizado incluído. Checar
apenas `Origin` "quando presente" deixa essa porta aberta. Ver D10.

## Defesas

### D1 — Bind local obrigatório (contra T2)

O host de escuta é fixado em `127.0.0.1` **no código**, não só na configuração.
`main.py` valida no startup e recusa subir se o host resolvido não for
loopback. Não existe flag para expor na rede. Quem quiser isso, altera o código
e assume.

### D2 — Allowlist de ações (contra T3)

Não existe endpoint que receba comando. A relação entre ação HTTP e comando é
uma tabela fixa no código:

```
"git.status"     -> ["git", "status", "--porcelain=v2", "--branch"]
"git.log"        -> ["git", "log", "-n", "{limit}", "--format=..."]
"docker.ps"      -> ["docker", "compose", "-f", "{compose}", "ps", "--format", "json"]
"docker.up"      -> ["docker", "compose", "-f", "{compose}", "up", "-d"]
"system.vscode"  -> ["code", "{path}"]
```

Regras:

1. O cliente envia **identificador de ação**, nunca comando nem fragmento dele.
2. Os únicos placeholders permitidos são valores tipados e validados:
   inteiro com faixa, path validado, ou nome escolhido de um conjunto fechado
   (por exemplo, nome de serviço que exista no Compose do projeto).
3. Nenhum valor do cliente entra em posição de flag. `--{algo}` vindo do
   cliente é impossível por construção.
4. Ação fora da tabela retorna `403 ACTION_NOT_ALLOWED` e grava `DENIED` na
   auditoria.

### D3 — Sem shell, nunca (contra T3)

Toda execução usa argv como lista, com `shell=False`. `shell=True` é proibido
por revisão e por teste automatizado que varre o código-fonte procurando a
string. Não há caso de uso legítimo para ele neste projeto — nem para pipe, que
é resolvido em Python.

### D4 — Validação de path centralizada (contra T4, T5)

Todo path passa por `core/paths.py` antes de qualquer uso:

```
1. rejeita path relativo
2. resolve para caminho absoluto real (resolve symlink)
3. normaliza caixa e separador (Windows)
4. exige que seja diretório existente
5. exige que esteja contido em pelo menos um root permitido
6. rejeita se o path resolvido saiu do root (defesa contra symlink)
```

Roots permitidos ficam em `configs/roots.yml`, editável só no disco — nunca por
API. Se a API pudesse adicionar root, a validação seria decorativa.

```yaml
allowed_roots:
  - C:/Users/User/Desktop
  - C:/Users/User/Documents
  - C:/Users/User/Projetos
```

A comparação é feita entre paths já resolvidos, com verificação de componentes
de diretório — nunca com `startswith` sobre string, que confunde
`C:/Users/User/Desktop-antigo` com `C:/Users/User/Desktop`.

### D5 — Guard de origem (contra T1)

Toda requisição que altera estado (`POST`, `PATCH`, `PUT`, `DELETE`) exige:

1. cabeçalho `X-DevCockpit-Client: web` — um `fetch` cross-origin não consegue
   enviar cabeçalho customizado sem passar por preflight CORS, e o CORS do
   DevCockpit não permite nenhuma origem externa;
2. `Origin` **obrigatório e igual** à origem própria da aplicação. Ausente é
   rejeitado, não tolerado — é essa tolerância que T9 explora;
3. CORS configurado sem wildcard: só a origem local do próprio frontend.

Isso derruba o ataque de página maliciosa, que é o vetor realista.

### D10 — Validação do cabeçalho `Host` (contra T9)

`Origin` sozinho não basta. **Toda** requisição, inclusive `GET`, valida o
cabeçalho `Host` contra um conjunto fechado:

```
localhost | 127.0.0.1 | [::1]      (com a porta configurada)
```

Qualquer outro valor retorna `403` e grava `DENIED` na auditoria.

Por que isso fecha T9: no rebinding, o browser continua enviando
`Host: evil.com`, porque é o nome que ele resolveu. O servidor não tem como
saber que o IP foi reamarrado, mas sabe que ninguém legítimo o alcança por esse
nome. A validação é barata e é a defesa padrão recomendada para serviço
`localhost`.

A checagem é feita em middleware, antes do roteamento, e vale também para os
endpoints SSE — stream de longa duração é justamente o que um atacante
preferiria manter aberto.

### D6 — Ações destrutivas excluídas do MVP (contra T7)

Proibido no MVP, por decisão e não por falta de tempo:

```
git reset / clean / checkout / push --force / commit
docker compose down -v        (remove volume = perde dado)
docker system prune
docker volume rm
rm / del / Remove-Item        em qualquer forma
qualquer escrita em arquivo do projeto alvo
```

`docker compose down` sem `-v` é permitido: para containers e remove a rede,
mas preserva volume nomeado. A flag `-v` não é exposta por nenhum caminho.

Quando ação destrutiva entrar no roadmap, ela precisa de: confirmação
explícita na UI com o nome do projeto digitado, entrada de auditoria antes da
execução, e ADR próprio.

### D7 — Timeout obrigatório (contra T8)

`CommandSpec` sem timeout não compila conceitualmente: o campo é obrigatório.
Padrões:

| Categoria | Timeout |
|-----------|---------|
| leitura Git | 10 s |
| leitura Docker | 15 s |
| `compose up` / `down` | 300 s |
| `compose start` / `stop` / `restart` | 120 s |
| ação de SO (abrir app) | 10 s |
| varredura de disco | 120 s, profundidade máxima 3 |
| health check HTTP/TCP | 2 s |

Estourado o timeout, o processo é encerrado (árvore de processos inteira no
Windows) e o job vira `TIMEOUT`.

### D8 — Higiene de segredo (contra T6)

- O DevCockpit **não lê `.env` dos projetos gerenciados**. Nem para detecção de
  porta. É tentador e é errado.
- `argv` gravado na auditoria passa por filtro de redação por padrão de chave
  (`token`, `secret`, `password`, `key`, `authorization`).
- Variável de ambiente nunca é registrada.
- Token do GitHub (Fase 5) vem só de variável de ambiente, nunca do banco.
- Log de container pode conter segredo: é exibido ao usuário, mas nunca
  persistido pelo DevCockpit.

### D9 — Superfície mínima de leitura

A detecção lê apenas **nome de arquivo** e, quando necessário, campos
específicos de arquivos de manifesto conhecidos (`package.json`,
`docker-compose.yml`). Não existe endpoint que devolva conteúdo arbitrário de
arquivo. `GET /api/files?path=...` não existe e não vai existir.

## Resumo: ameaça x defesa

| Ameaça | Defesas |
|--------|---------|
| T1 CSRF | D5, D1, D10 |
| T2 exposição em rede | D1 |
| T9 DNS rebinding | D10, D5 |
| T3 injeção | D2, D3 |
| T4 traversal | D4, D2 |
| T5 symlink | D4 |
| T6 segredo | D8, D9 |
| T7 destrutivo | D6, auditoria |
| T8 recurso | D7 |

## Testes de segurança obrigatórios

Estes testes fazem parte da definição de pronto, não de um "hardening depois":

1. `POST` sem `X-DevCockpit-Client` → 403.
2. `Origin` externa → 403.
3. Startup com host não-loopback → recusa subir.
4. Cadastro de path fora dos roots → `PATH_NOT_ALLOWED`.
5. Path com `..` que escapa do root → `PATH_NOT_ALLOWED`.
6. Symlink dentro do root apontando para fora → `PATH_NOT_ALLOWED`.
7. `service` inexistente no Compose → 422, e nenhum comando executado.
8. Varredura do código-fonte: nenhuma ocorrência de `shell=True`.
9. Varredura do código-fonte: `subprocess` importado somente em
   `app/runner/`.
10. Nome de projeto com metacaractere de shell → chega intacto ao argv, sem
    efeito colateral.
11. Ação desconhecida → 403 e registro `DENIED`.
12. Redação: `argv` com valor sensível → gravado mascarado.
13. `Host` diferente de `localhost`/`127.0.0.1`/`[::1]` → 403, inclusive em
    `GET` e em endpoint SSE.
14. `POST` sem `Origin` → 403 (ausência não é tolerada).

## Postura de autenticação

Não há login no MVP, e isso é aceitável **apenas** porque D1 + D5 + D10 valem
em conjunto. Se um dia o bind local for relaxado, autenticação passa de opcional a
pré-requisito absoluto. Está registrado aqui para que a decisão não seja
revisitada por engano.
