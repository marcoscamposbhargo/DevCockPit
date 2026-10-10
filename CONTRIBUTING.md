# Como contribuir

Obrigado pelo interesse. Este guia existe para você não gastar tempo num PR que
eu teria de recusar por um motivo que dava para saber antes.

## Antes de escrever código

**Abra uma issue primeiro** se a mudança for maior que um conserto pontual.
Feature grande sem conversa prévia é o tipo de PR que fica parado — não por
desinteresse, mas porque decidir escopo depois do código pronto é caro para os
dois lados.

Conserto de bug, correção de texto ou melhoria de teste: pode mandar o PR
direto.

## Rodando o projeto

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1   # cria venv, migra e sobe
copy configs\roots.example.yml configs\roots.yml           # obrigatório
```

Sem `configs/roots.yml` nenhum projeto pode ser cadastrado — é a defesa D4, não
um passo esquecido.

## Antes de abrir o PR

```powershell
.venv\Scripts\python.exe -m pytest -q      # 970 testes, precisam passar
.venv\Scripts\python.exe -m ruff check .   # precisa sair limpo
```

Os dois são obrigatórios. A suíte de frontend roda no runner do próprio Node e
é chamada de dentro do `pytest` — não há comando separado nem `node_modules`.

## As regras que não se negociam

Este projeto tem uma [constituição](docs/constitution.md): sete princípios
vinculantes, destilados das decisões arquiteturais. **Violação é bloqueio, não
sugestão** — e vários deles têm teste que falha o build se forem quebrados.

O resumo do que mais derruba PR:

| | |
|---|---|
| **P-01** | A IA não ganha capacidade que o painel não tenha por botão. Se o modelo precisa fazer algo novo, esse algo vira botão primeiro — com rota e testes próprios. |
| **P-02** | O painel não afirma o que não mediu. Indicador sem dado é "não medido", nunca zero. Zero é uma afirmação. |
| **P-03** | Um processo, um arquivo de banco, sem etapa de build. Serviço novo, banco novo ou bundler precisam derrubar essa regra antes de entrar. |
| **P-04** | Comando externo só por allowlist e sem shell. `subprocess` fora de `app/runner/` reprova num teste que varre o fonte. |
| **P-05** | Segredo vive no ambiente e em nenhum outro lugar. Nunca no banco, no frontend, em log ou versionado. |
| **P-06** | Provider de modelo é substituível. Nenhuma regra de negócio depende de um SDK específico; a suíte roda inteira sem rede e sem chave. |
| **P-07** | Comportamento novo chega com teste, escrito no mesmo ciclo. |

Se a sua ideia esbarra num desses e você acha que o princípio é que está errado,
**abra uma issue propondo alterar a constituição** — ela tem processo próprio
(SemVer e histórico). É uma conversa legítima; só não pode acontecer por
acidente dentro de um PR de outra coisa.

## O que já foi decidido que o projeto não faz

Não são "features futuras": exigiriam refazer o modelo de segurança inteiro.

```
terminal web · editor de código · IDE embutida · CI/CD próprio
Kubernetes · execução remota · multiusuário · escrita destrutiva no Git
agente autônomo sem confirmação · IA escrevendo arquivo em projeto seu
```

## Estilo

- **Código e comentário em português.** O projeto inteiro é assim; manter
  consistência vale mais que preferência individual.
- **Comentário explica *por quê*, não *o quê*.** O código já diz o que faz. O
  que se perde com o tempo é a razão — e a alternativa que foi descartada.
- `ruff` com `line-length = 100` decide formatação. Não discuta com ele.
- Mensagem de commit: uma linha dizendo o que mudou, e corpo dizendo qual
  problema forçou a mudança. Veja o `git log` para o padrão.

## Documentação

Se a mudança altera comportamento, o documento correspondente muda **no mesmo
commit**. Documento atualizado depois é documento que não foi atualizado.

Decisão técnica relevante vira ADR em [`docs/adr/`](docs/adr/) — o formato está
nos nove que já existem.

## Licença

Ao contribuir, você concorda que sua contribuição é licenciada sob a
[AGPL-3.0](LICENSE), a mesma licença do projeto.
