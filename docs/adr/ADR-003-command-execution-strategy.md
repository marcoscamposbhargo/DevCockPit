# ADR-003 — Execução de comandos: CommandRunner com allowlist e sem shell

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

Esta é a decisão de maior risco do projeto. O DevCockpit executa `git`,
`docker`, `code`, `explorer` e emuladores de terminal na máquina do
desenvolvedor, disparado por requisições HTTP que a interface envia — e que
**qualquer página aberta no browser do usuário também consegue enviar**, porque
o browser alcança `127.0.0.1`.

Um erro aqui não é bug funcional: é execução remota de código na estação de
trabalho.

O prompt original já veta `POST /execute-command` com conteúdo livre. Isso é
necessário, mas insuficiente: falta definir como um comando legítimo é montado,
quem autoriza, e o que impede um valor do cliente de virar flag.

## Decisão

Três regras, todas obrigatórias e verificadas por teste automatizado.

**1. Camada única de execução.** Todo comando externo passa por
`app/runner/command_runner.py`. `subprocess` só pode ser importado dentro de
`app/runner/`. Um teste varre o código-fonte e reprova se isso for violado.

**2. Allowlist de ações, não de comandos.** O cliente envia um identificador de
ação (`docker.up`, `git.status`). A tradução para argv é uma tabela fixa no
código. Ação fora da tabela retorna `403 ACTION_NOT_ALLOWED` e grava `DENIED`
na auditoria.

Os únicos valores do cliente que entram em argv são:

| Tipo | Validação |
|------|-----------|
| path | canonicalizado e dentro de root permitido (`core/paths.py`) |
| inteiro | faixa fechada (por exemplo, `limit` entre 1 e 200) |
| enumerado | valor pertencente a conjunto fechado conhecido |
| nome de serviço Compose | precisa existir no arquivo Compose daquele projeto |

Nenhum valor do cliente ocupa posição de flag. `--algo` vindo do cliente é
impossível por construção, não por filtro de string.

**3. Sem shell, com timeout obrigatório.** Argv é sempre lista, execução sempre
com `shell=False`. `CommandSpec` exige `timeout_s`. Estourado o timeout, a
árvore de processos é encerrada e o job vira `TIMEOUT`.

```
CommandSpec(argv, cwd, timeout_s, env_extra, label)
  -> CommandRunner
  -> CommandResult(exit_code, stdout, stderr, duration_ms, timed_out)
  -> ActivityLog (argv redigido)
```

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Endpoint genérico de comando com blocklist** | blocklist de shell é uma corrida perdida: `;`, `&&`, backtick, `$()`, `%`, `^`, encoding, alias. Uma omissão é execução arbitrária |
| **`shell=True` com escaping cuidadoso** | `shlex.quote` não vale no Windows, onde as regras de quoting variam por programa. Não existe escaping correto e portável |
| **Bibliotecas nativas em vez de CLI (GitPython, docker SDK)** | reduz a superfície, mas: GitPython adiciona dependência e ainda usa o CLI em vários caminhos; o docker SDK não cobre Compose v2, que é o contrato real. E o CLI mantém um único caminho de auditoria para tudo |
| **Sandbox / usuário separado** | a ferramenta existe justamente para agir na conta do usuário; sandbox eliminaria a função |

Sobre a alternativa das bibliotecas: ela não é rejeitada em definitivo. Se um
dia o `docker` SDK cobrir Compose v2 de forma estável, migrar o
`DockerAdapter` é local — o resto do sistema não percebe. É esse o ganho de ter
adapter.

## Consequências

Positivas:
- superfície de execução enumerável: dá para ler a tabela inteira de comandos
  possíveis em uma tela
- auditoria, timeout e medição de duração são inescapáveis, porque estão no
  único caminho
- `FakeCommandRunner` torna quase todo o sistema testável sem tocar no SO
  (`10-testing-strategy.md`)
- `DENIED` na auditoria dá visibilidade de tentativa de ação não prevista

Negativas:
- adicionar funcionalidade nova exige alterar a tabela de ações: mais atrito por
  feature. Isso é o preço, e é deliberado
- parse de saída de CLI é frágil entre versões. Mitigação: exigir formato
  estável (`--porcelain=v2`, `--format json`), fixtures capturadas de saída real
  com versão anotada, e detecção de versão em `GET /api/health`
- encerrar árvore de processos no Windows exige tratamento específico
  (job object / grupo de processo), com teste dedicado

## Verificação

Testes que reprovam a entrega se falharem:

1. nenhuma ocorrência de `shell=True` no código-fonte
2. `subprocess` importado somente em `app/runner/`
3. ação desconhecida retorna 403 e grava `DENIED`
4. nome de serviço Compose inexistente retorna 422 sem executar comando
5. valor de cliente iniciando com `-` é rejeitado na validação
6. nome de projeto com metacaractere de shell chega intacto ao argv, sem efeito
   colateral
7. `CommandSpec` sem timeout é erro de construção
8. allowlist não contém `git commit`, `reset`, `clean`, `checkout`, `push`, nem
   `docker compose down -v`, `system prune`, `volume rm`
