# ADR-007 — OSAdapter com Windows como plataforma primária

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O prompt descreve as ações de sistema em sintaxe POSIX (`code caminho-do-projeto`,
"abrir terminal"), como se a plataforma fosse neutra. Ela não é. A máquina alvo
é Windows 11, e quase toda ação de SO difere:

| Ação | Windows | Linux | macOS |
|------|---------|-------|-------|
| VS Code | `code.cmd` (é um `.cmd`, não binário) | `code` | `code` |
| Abrir pasta | `explorer.exe` | `xdg-open` | `open` |
| Abrir terminal no diretório | `wt.exe -d <path>`, com fallback para `powershell.exe -NoExit -Command "Set-Location ..."` | varia por ambiente de desktop | `open -a Terminal <path>` |
| Abrir URL | `start` é comando interno do shell, não executável | `xdg-open` | `open` |
| Encerrar árvore de processos | job object / `taskkill /T` | grupo de processo + sinal | grupo de processo + sinal |

Além disso, no Windows: paths são case-insensitive mas case-preserving, o
separador é `\`, há limite histórico de comprimento de path, e existem paths UNC
(`\\wsl$\...`).

Espalhar `if platform == "win32"` pelos serviços produziria justamente o
acoplamento entre camada de aplicação e sistema operacional que a arquitetura
proíbe.

## Decisão

Uma interface **`OSAdapter`** com implementação por plataforma. Toda diferença
de sistema operacional vive exclusivamente ali.

```
OSAdapter (interface)
  open_in_editor(path)      -> CommandSpec
  open_folder(path)         -> CommandSpec
  open_terminal(path)       -> CommandSpec
  open_url(url)             -> CommandSpec
  detect_tool(name)         -> bool
  kill_process_tree(pid)    -> None

WindowsOSAdapter · LinuxOSAdapter · MacOSAdapter
```

O adapter **monta e devolve `CommandSpec`**; quem executa continua sendo o
`CommandRunner` (ADR-003). O adapter não executa nada por conta própria — assim
a auditoria e o timeout continuam inescapáveis.

Regras associadas:

1. Windows é a plataforma de referência. Linux e macOS são suportados e devem
   funcionar, mas Windows é onde se valida primeiro.
2. Nenhum separador de path escrito à mão. `pathlib` obrigatório (NFR-041).
3. Comparação de path no Windows normaliza a caixa; em POSIX, não.
4. Abrir URL nunca usa `start`, que é comando interno de shell e exigiria
   `shell=True`. Usa-se a API do sistema por meio do módulo `webbrowser` do
   Python, que não invoca shell.
5. Ferramenta ausente é detectada antes: `GET /api/health` informa
   disponibilidade de `git`, `docker` e `code`, e a UI desabilita as ações
   correspondentes com o motivo, em vez de deixar o usuário clicar e falhar.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Só POSIX, e Windows "depois"** | a máquina alvo é Windows; entregaria uma ferramenta que não funciona onde vai ser usada |
| **`if platform` dentro de cada service** | espalha conhecimento de SO pela camada de aplicação, quebra a testabilidade e contraria NFR-020 |
| **Depender de WSL para uniformizar** | forçaria o usuário a um ambiente específico e não resolveria abrir VS Code ou Explorer no host |
| **Biblioteca de terceiro para abrir aplicativos** | dependência a mais para envolver três chamadas; e as diferenças de terminal continuariam por conta própria |
| **Adapter que executa diretamente** | perderia auditoria e timeout centralizados; violaria ADR-003 |

## Consequências

Positivas:
- diferença de plataforma isolada em um único módulo, com testes por plataforma
  verificando o argv produzido
- portar para Linux e macOS é escrever uma classe, sem tocar em service
- teste de `OSAdapter` não precisa executar nada: basta asserção sobre o
  `CommandSpec` devolvido

Negativas:
- três implementações para manter; só uma exercitada no dia a dia. Mitigação:
  os testes de argv rodam para todas, independente da plataforma da execução
- fallback de terminal no Windows (`wt.exe` ausente em instalações antigas)
  exige detecção em tempo de execução

## Questão em aberto

Projeto localizado em path UNC de WSL (`\\wsl$\Ubuntu\home\user\projeto`) é
caso a tratar: `code` e Git funcionam, `explorer` funciona, mas a validação de
path e a resolução de symlink se comportam de forma diferente. Decidir na Fase 2
(Q-06 em `12-decisions.md`).
