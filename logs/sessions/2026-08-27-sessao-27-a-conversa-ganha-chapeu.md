## 2026-08-27 — Sessão 27: a conversa ganha chapéu

Fase 3 do Cockpit AI fechada: **3.2 (perfis), 3.3 (seleção) e 3.5 (comandos)**.
O pedido foi "finalize todas as pendências", com três decisões dadas: três
perfis, especialista fixável com botões de um clique, e quem respondeu gravado
em `ai_message` por migração.

### O que um especialista é aqui

Um chapéu, não um agente. Instrução de sistema própria, um punhado de ações do
registro fechado, e nada mais: um processo, um modelo, três chapéus. DevOps
(ambiente, container, porta, log), Full Stack (código, API, integração) e QA
(teste, bug, regressão).

Três e não os sete do `AGENT_ORCHESTRATION.md`. Os sete cobrem o produto
imaginado; três cobrem o que este painel faz hoje. Perfil sem uso é prompt para
manter sem ninguém ler.

### A divergência que vale registrar

O desenho previa o modelo desempatando quando nenhuma regra casasse. **Não há
chamada de modelo no roteamento**, e o motivo é medido: num provedor local uma
classificação curta custa de 3 a 26 s — mais que a resposta inteira em muitos
casos. Roteamento que custa isso não é roteamento, é espera.

A regra decide pela palavra na pergunta; sem casar, o Full Stack atende; e a
escolha da pessoa vence as duas. É a mesma doutrina do orquestrador de ações,
levada até o fim: regra primeiro, e o modelo só onde ele é insubstituível.

### Os botões, que era o pedido de verdade

> "tem como ficar especialista, subir terminal, abrir ambiente com um click,
> subir container com um click, pra nao ficar pedindo ajuda ao claude"

Cada perfil traz uma barra de atalhos. Nenhum deles é caminho novo: apontam para
ações do **mesmo registro fechado** das propostas, com bilhete emitido pelo
servidor — clicar equivale a confirmar uma proposta, e a linha de auditoria sai
com `actor=ai` igual à que veio de uma frase (D-A3 + Fase 3.6).

Um teste percorre os três perfis e falha se algum atalho apontar para fora do
registro. Sem ele, a barra de atalhos seria exatamente o lugar onde uma
capacidade nova entraria sem ninguém notar.

Detalhe que os testes pegaram e eu não tinha visto: `ports.map` **não leva
projeto no caminho** — é da máquina, não do projeto. As duas formas convivem na
mesma barra, e o filtro só remove a ação de projeto quando não há projeto.

### Migração 009

`ai_message.agent` e `ai_message.prompt_versao`. A segunda parece exagero até o
prompt mudar: depois disso, uma resposta guardada sem a versão vira algo que
ninguém consegue explicar, porque o texto que a produziu não existe mais em
lugar nenhum.

Armadilha de ambiente, de novo: `alembic upgrade head` rodou e as colunas não
apareceram em `data/devcockpit.db`. O banco efetivo é
`C:/Users/User/DevCockpit/data/devcockpit.db` — `settings.resolve` reescreve o
caminho relativo. Conferir a versão no arquivo errado dá "não aplicou" quando
aplicou.

### Comandos de barra

`/status`, `/plan`, `/find-bugs`, `/why`, `/review`, `/document`. Cada um é uma
frase pronta com o chapéu certo já escolhido — economia de digitação, não
capacidade nova. Texto depois do comando entra como complemento em vez de ser
descartado: quem digita "/why o banco" tinha algo específico em mente.

### O que foi verificado, e como

| Verificação | Resultado |
|---|---|
| `pytest -q` | **668 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend` | 48 passaram |
| `ruff check app tests` | limpo |
| `GET /ai/specialists?project_id=…` (painel real) | três perfis, atalhos resolvidos, um bilhete por botão |
| Clique num atalho (`git.status`, bilhete real) | `200`, pela mesma rota do botão de sempre |
| Migração `009` no banco efetivo | `agent` e `prompt_versao` presentes, versão `009_ai_especialista` |

**O que não foi verificado ao vivo:** a resposta de chat com chapéu fixado
gravando `agent` na tabela. O provedor local levou mais de 4 minutos e a sessão
foi encerrada antes. O caminho está coberto por teste de unidade
(`test_quem_respondeu_fica_gravado_com_a_versao_do_prompt`), mas a confirmação
no painel real fica para a próxima sessão — é o primeiro item a fazer.

### Situação ao encerrar

Fase 3 inteira entregue. Do Cockpit AI faltam as Fases 4 e 5, e o item 17
(integração com VS Code / Claude Code). Do HyperBrain, os MVPs 3 a 5 — e eles
seguem esperando **uso real da tela**, não código.

### Próximo passo

1. Abrir o painel e mandar uma pergunta com chapéu fixado; conferir que a bolha
   assina "Cockpit AI · QA" e que `ai_message.agent` foi gravado.
2. Usar os atalhos por alguns dias antes de acrescentar perfil ou botão. A
   sessão 24 já cobrou o preço de empilhar camada sem esse teste.

### Correção depois do fechamento — "database is locked" no clique do atalho

O primeiro clique em **Subir o servidor** devolveu "Erro interno" na tela. O log
disse o que era, e não tinha nada a ver com a Fase 3:

```
sqlite3.OperationalError: database is locked
[SQL: INSERT INTO dev_server (project_id, pid, command, ...)]
```

**A causa, que é anterior aos chapéus:** o repositório de mensagens só chama
`flush()`, nunca `commit()`. A pergunta era gravada **antes** do stream começar,
e a transação de escrita ficava aberta até o fim da requisição — com provedor
local, minutos. O SQLite admite um escritor por vez; nessa janela, qualquer
outra escrita falhava. O poller de health caiu junto, no mesmo segundo.

Ou seja: conversar com a IA travava o painel inteiro para escrita enquanto ela
respondia. O sintoma aparecia longe da causa — o erro surgia num botão que não
tem relação nenhuma com o chat, e foi por isso que passou despercebido até
agora.

**O conserto:** `commit()` logo depois de gravar a pergunta, e de novo depois de
gravar a resposta. A pergunta já está completa no primeiro ponto; não havia
razão para segurá-la. Somado a isso, `PRAGMA busy_timeout=15000` — o padrão do
driver são 5 s, e não substitui transação curta: só evita que um pico normal
vire erro na tela.

**O teste vale porque falha sem o conserto**, e isso foi verificado nos dois
sentidos: `test_a_pergunta_e_liberada_antes_do_stream_comecar` consome o
primeiro pedaço do stream e exige `not session.in_transaction()`. A primeira
versão do teste passava com e sem o conserto — olhava `session.dirty`, que fica
vazio depois do `flush`. Teste que passa dos dois jeitos não é teste.

Verificado no painel real: com uma resposta em stream, **seis escritas seguidas
devolveram 200**, e o log não registrou nenhum lock depois disso.

### Armadilha de plataforma, terceira aparição

Reinstalar o executável esbarrou em `VCRUNTIME140.dll` travada — desta vez por
`chrome-native-host.exe`, processo do Claude no Chrome, sem relação com o
projeto. O hash do arquivo instalado e do novo era **idêntico**, então a saída
foi copiar tudo menos ele (`robocopy /XF`) e conferir arquivo por arquivo que
nada faltou. Matar processo alheio para trocar um arquivo que não mudou seria
custo sem ganho.

---

