## 2026-08-25 (continuação) — Sessão 23: o mapa passa a responder

MVP 2 do HyperBrain: a barra "Ask HyperBrain" dentro do palco, ligada à IA que
já existia. Nenhum agente novo, nenhum provedor novo — só um caminho novo até os
mesmos.

### Três caminhos, e um porteiro

O que se digita segue nesta ordem: filtro de visão (regra local), ação (proposta
com confirmação) e, por último, pergunta.

O filtro é o que mais surpreende: "mostre os projetos em python" não precisa de
IA nenhuma. É filtro sobre dado que o navegador já tem, resolvido em
milissegundos, **com zero chamada de rede** — verificado contando as requisições
durante o gesto. Funciona com o Cockpit AI desligado.

O porteiro do passo 2 existe por causa do relógio. Pedir proposta custa 0,1 s
quando a regra do servidor decide, e de 3 a 26 s quando cai no modelo local. Se
toda frase pagasse esse pedágio, "onde paramos ontem?" começaria a ser respondida
meio minuto depois de escrita.

### O que a medição mostrou sobre os dois modelos

| Frase | 7b | 3b |
|---|---|---|
| `sobe o devcockpit` | 0,1 s — regra | 0,1 s — regra |
| `faz o deploy em produção` | 25,8 s — **recusou** | 3,1 s — propôs `environment.up` |
| `apaga o banco do devcockpit` | 5,5 s — **recusou** | 4,2 s — propôs `server.stop` |

É a mesma diferença medida na Fase 3.4, agora vista da tela do grafo. E a
contenção não depende do modelo: com o 3b propondo `server.stop` para "apaga o
banco", o log de atividade ficou em **7 antes e 7 depois**. Nada executa sem o
clique.

Os verbos destrutivos entraram na lista de propósito, embora nenhum exista no
registro fechado — justamente por isso. Mandados para o servidor, voltam como
recusa explícita. "Apaga o banco" merece "não faço isso", não um modelo
divagando sobre como apagar um banco.

### Um interruptor que não tinha interruptor

`ai_enabled` existe na tabela `project` desde a Fase 2, e a defesa D-A1 diz que
excluir um projeto da IA é decisão da pessoa, projeto a projeto. Só que não
havia rota para mudar o campo: ele nascia `true` e ficava `true` para sempre.
Agora está em `ProjectUpdate` e em `ProjectSummary` — a segunda porque uma tela
que mostra todos os projetos de uma vez precisa sinalizar quem está fora
**antes** de qualquer requisição.

Verificado ao vivo: com `ai_enabled = false`, perguntar com o projeto
selecionado não chama a rota de chat. Aparece só `ai/ask` na rede, e a tela
avisa que perguntou sem o contexto dele.

### O defeito, e ele era bom

O botão Cancelar do cartão de ação não fazia nada.

O estado do núcleo passava pelo mesmo observável do painel lateral, então cada
`thinking` ou `success` remontava o painel inteiro. O `blur` do campo de
pergunta chegava junto com o clique: o cartão era removido e recolocado no meio
do gesto, e o clique se perdia no vão. Quem fosse **recusar** uma ação apertava
Cancelar e não acontecia nada.

O conserto foi tirar o estado do núcleo do observável — ele é atributo de um
elemento, não estado de tela. Achado clicando, não lendo.

### Verificação ao vivo, em banco separado

A primeira tentativa rodou contra o banco do app instalado e deu `database is
locked`: dois servidores escrevendo no mesmo SQLite. O resto da verificação
passou a rodar em banco próprio, com cinco projetos cadastrados só para isso.

### Rótulos, e a vida do núcleo

Com os 19 projetos na tela, dois problemas de layout ficaram óbvios:
"QRCODE_GENERATION" cruzando "DEVCOCKPIT", e nomes cinzas cortados pelas
arestas que passavam por baixo.

`labels.js` escolhe, para cada rótulo, o primeiro lugar livre em volta do nó —
abaixo, acima, direita, esquerda —, com os nós e o núcleo contando como
obstáculo. Quem não acha lugar some, e volta no hover. Roda **só quando o grafo
para**: medir texto obriga o navegador a calcular layout, e por quadro custaria
mais que a simulação inteira. Medido na tela: **0 pares sobrepostos**, 1
escondido de 30.

E o pedido de "movimento, pulsante, com cores" virou regra: cada coisa que se
mexe carrega informação. Halo respirando, dois anéis em sentidos opostos, trinta
partículas orbitando, dois pulsos defasados — e o que importa mais: **nó de
projeto respirando em verde significa que ele está no ar agora**. Cada
tecnologia ganhou matiz derivada do hash do nome, aplicada como `hue-rotate`
sobre o token: cor literal continua morando só no `tokens.css`.

Tudo desliga junto em `prefers-reduced-motion`, no botão de movimento e acima de
150 nós. Nenhuma animação roda em JavaScript.

42 testes de frontend (18 novos), 636 no `pytest`, `ruff` limpo.

### O executável, e uma porta que ninguém tinha declarado

Empacotado e instalado, com o mesmo contorno da sessão 21 para a
`VCRUNTIME140.dll` travada — desta vez pelo VS Code, com o painel já parado.
Hash conferido, `robocopy` no resto, e verificação arquivo por arquivo: 320
arquivos idênticos ao build.

Ao reabrir, o painel subiu na **8765** e não na 8790. Descoberta: a 8790 não
está gravada em lugar nenhum — nem em `configs/defaults.yml`, nem em variável de
usuário. Ela vinha do ambiente de quem tinha lançado o app da última vez. 8765 é
o padrão do código.

### Continua com você

- [ ] **usar a tela.** O MVP 3 (tarefas, sessões, decisões e serviços como nós)
      só faz sentido depois de o mapa provar que serve para alguma coisa
- [ ] `ai_enabled` tem rota, mas **não tem botão**: hoje só muda por `PATCH`.
      Um interruptor na tela do projeto fecharia a defesa D-A1 de verdade
- [ ] o seletor de modelo (7b/3b) não existe no HyperBrain; a pergunta rápida
      tem. Com a diferença de tempo medida acima, pode valer
- [ ] as pendências das sessões 21 e 22 seguem de pé

---

