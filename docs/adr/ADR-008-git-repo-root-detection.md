# ADR-008 — Um projeto só é repositório Git se for a raiz dele

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 2
- **Origem:** bug encontrado por teste durante a implementação

## Contexto

A implementação inicial do `GitAdapter` perguntava ao Git a coisa óbvia:

```
git rev-parse --is-inside-work-tree
```

Um teste de contrato falhou apontando `is_repo: true` para um diretório
temporário que não tinha nenhum `.git`. Não era falha do teste.

`git` **sobe a árvore de diretórios** procurando um repositório. Na máquina de
desenvolvimento alvo existe um repositório em `C:/Users/User` — o perfil
inteiro do usuário sob controle de versão, coisa mais comum do que parece.
Verificado em um projeto real:

```
$ cd C:/Users/User/Desktop/Projetos/ZAPBOT
$ git rev-parse --is-inside-work-tree
true
$ git rev-parse --show-toplevel
C:/Users/User
```

A consequência para o produto seria grave. Todo projeto abaixo do perfil
apareceria como repositório, exibindo a branch do repositório pai e os seus
milhares de arquivos sujos. Trinta projetos mostrariam **o mesmo estado, todo
ele errado**, e o dashboard de "alterações pendentes" — uma das telas centrais
do MVP — viraria ruído puro.

Isto é exatamente o risco registrado como o mais perigoso do projeto: dado
errado exibido com confiança destrói a utilidade da ferramenta. O usuário
confere uma vez, vê que está errado, volta para o terminal e não abre mais.

## Decisão

A pergunta certa não é *"estou dentro de um repositório?"* e sim
**"a raiz do repositório é este diretório?"**.

`GitAdapter.locate_repo` executa `git rev-parse --show-toplevel` e compara o
resultado com o diretório do projeto, respeitando a caixa da plataforma. Daí
saem três estados honestos:

| Situação | `is_repo` | `inside_other_repo` | `repo_root` |
|----------|-----------|---------------------|-------------|
| o diretório é a raiz do repositório | `true` | `false` | a própria raiz |
| está dentro de um repositório cuja raiz é outra | `false` | `true` | a raiz do pai |
| não há repositório algum acima | `false` | `false` | `null` |

No segundo caso, **nenhum `git status` chega a ser executado** e a interface
diz textualmente: "esta pasta está dentro do repositório X; o estado dele não
é mostrado aqui porque seria o mesmo para todos os projetos abaixo".

Repositório aninhado com `.git` próprio continua sendo reconhecido como seu:
a comparação é com a raiz efetiva, não com a existência de um pai.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Testar `(project_dir / ".git").exists()`** | mais simples, mas erra em worktree e em submódulo, onde `.git` é arquivo apontando para outro lugar. Perguntar ao Git e comparar cobre os dois casos |
| **Aceitar o repositório do pai e exibi-lo** | é o comportamento que causou o problema. Para um subdiretório escolhido de propósito pode até fazer sentido, mas o custo — trinta projetos com estado idêntico e errado — não compensa o ganho |
| **`GIT_CEILING_DIRECTORIES`** | limitaria a subida, mas exigiria escolher o teto certo por projeto; a comparação com `--show-toplevel` resolve sem configuração |
| **Deixar o usuário marcar "usar repositório pai"** | opção plausível no futuro, com o dado já disponível em `repo_root`. Não entra agora: o padrão precisa estar certo antes de existir exceção |

## Consequências

Positivas:
- o dashboard de pendências Git passa a mostrar apenas alteração real de cada
  projeto
- a interface tem uma informação nova e útil: "este projeto ainda não tem
  repositório próprio", que é acionável
- `repo_root` fica disponível para uma futura opção de herdar o repositório do
  pai, se ela se justificar

Negativas:
- uma execução extra de `git rev-parse` por consulta de status. Custo
  desprezível e absorvido pelo cache com TTL
- projeto que é legitimamente um subdiretório de um monorepo não mostra estado
  Git. É a troca certa: melhor não mostrar do que mostrar errado

## Verificação

`tests/integration/test_git_real.py` cobre o caso com Git real:

- `test_subdiretorio_nao_herda_o_repo_do_pai` — subdiretório de repositório
  devolve `is_repo: false`, `inside_other_repo: true`, sem branch e sem
  contagem de arquivos
- `test_repo_aninhado_e_reconhecido_como_proprio` — repositório com `.git`
  próprio dentro de outro é reconhecido como seu

E em `tests/unit/test_git_adapter.py`, com runner fake, verifica-se que
**nenhum `git status` é executado** quando a raiz é outra.
