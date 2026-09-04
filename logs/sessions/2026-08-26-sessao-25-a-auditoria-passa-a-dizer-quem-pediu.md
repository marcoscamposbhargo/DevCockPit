## 2026-08-26 — Sessão 25: a auditoria passa a dizer quem pediu

Sessão curta e fechada: três pendências que estavam abertas há dias, e uma fase
inteira do Cockpit AI.

### O executável e os Docker

O painel instalado subiu com o núcleo batendo — rebuild, `robocopy` com o mesmo
contorno da `VCRUNTIME140.dll` travada pelo VS Code, 321 arquivos conferidos por
hash contra o build.

`Dockerfile`, `docker-compose.yml` e `.dockerignore` ficam **versionados, com
aviso no topo**. A decisão pedia honestidade mais que gosto: dentro de um
container o painel perde abrir editor, pasta e terminal (nenhum dos três existe
lá), a varredura (os caminhos de `roots.yml` são do host), o servidor de projeto
e a verificação de porta — `localhost` ali é o do container, então todo serviço
do host apareceria offline. Sobra cadastro, Git, leitura de Docker com o socket
montado, portas declaradas e o Cockpit AI. Serve ao cenário de rodar num
servidor Linux contra projetos do próprio servidor, e a nada além disso.

Junto saiu `DEVCOCKPIT_HOST` do compose: não afeta o bind (quem manda é o `CMD`)
nem a validação de origem, que usa **só a porta**. Eu havia afirmado antes que a
divergência daria 403 em todo botão — fui verificar `self_origins` e estava
errado. Variável que não faz nada confunde mais do que ajuda, e por isso saiu.

### Fase 3.6 — o que ela realmente resolve

Não é funcionalidade, é honestidade do log. Até aqui, ação que o agente propôs e
a pessoa confirmou era gravada como **ação da pessoa**.

A saída óbvia — o cliente mandar um cabeçalho dizendo "isto veio da IA" — foi
descartada logo: seria o cliente **afirmando** autoria, e um log de auditoria
que confia no auditado não audita. É a mesma razão que proibiu o cliente de
mandar URL na decisão D-13.

O que ficou: o servidor emite um bilhete ao propor (`app/services/ai/propostas.py`)
e só reconhece autoria se ele voltar para a **mesma rota e o mesmo método**.
Bilhete inventado, vencido, já usado ou apontando para outra rota não marca nada
— e a ação segue, gravada como o que ela é. Uso único, porque bilhete
reutilizável transformaria uma confirmação em quantas execuções o cliente
quisesse.

O registro vive em memória de propósito: proposta é objeto de segundos, e
sobreviver a um reinício não é qualidade nenhuma para ela.

A autoria chega ao `ActivityService` por `ContextVar`, ao lado do
`correlation_id` — quem grava a auditoria é o serviço lá no fundo, e passar isso
por parâmetro obrigaria a atravessar rota, serviço, adapter e runner com um
argumento que só a última linha usa.

### Achados

- **Ação de leitura não gera auditoria nenhuma** no painel (`git.status`,
  `ports.map`, `docker.ps`), e isso é anterior à 3.6. Descoberto ao ver a
  verificação ao vivo dar `actor=ai: 0` — o caminho estava certo, a ação
  escolhida é que não deixava rastro. Consequência: "o que o agente **fez**
  ontem?" tem resposta; "o que ele **leu**?" não. Mudar é decisão de produto.
- **A poda do registro deixava TETO + 1.** `_podar` rodava antes da inserção,
  sobre um registro já cheio. Achado por teste, não por leitura.
- **Os primeiros testes abriam o Explorer de verdade** a cada rodada da suíte,
  porque `open/folder` executa comando real. Trocados por `PATCH /projects/{id}`,
  que passa pelo mesmo caminho de auditoria sem tocar na máquina.

### Verificação executada

| O que | Resultado |
|---|---|
| `pytest -q` | **647 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend/*.test.mjs` | **42 passaram** |
| `ruff check .` | limpo |
| Ao vivo, painel real, Ollama ligado | "abre o devcockpit no vscode" virou proposta em **0,01 s** pela regra |
| Confirmação com bilhete | `actor=ai`, `agent=open.vscode`, motivo nomeando quem decidiu |
| Mesmo bilhete de novo | gravado como **ação do usuário** — uma confirmação, uma execução |

### Situação ao encerrar

Branch `main`, árvore limpa, tudo publicado (`e81a002`). Painel instalado de pé
na **8765**, com o núcleo batendo. Nenhum servidor de desenvolvimento no ar.

Do Cockpit AI faltam **3.2, 3.3 e 3.5**. Do HyperBrain, os MVPs 3 a 5 — e o
combinado continua: usar a tela antes de empilhar camada nova.

### Próximo passo

**O interruptor do `ai_enabled` na tela do projeto.** A defesa D-A1 diz que
excluir um projeto do Cockpit AI é decisão da pessoa, projeto a projeto — e hoje
isso só muda por `PATCH`. É pequeno e fecha o último buraco de honestidade
aberto. Depois 3.2 + 3.3 juntos, e 3.5 quase de graça em cima deles.

---

