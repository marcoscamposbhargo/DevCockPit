# HyperBrain — Neural Core

> **Status: MVPs 1 e 2 entregues em 2026-08-25, e o mapa passou a ser 3D no
> mesmo dia.** As três decisões que travavam o início foram tomadas (seção 14);
> a de renderização foi revisada a pedido do usuário — ver seção 17 e a revisão
> do ADR-009. Os MVPs 3 a 5 seguem propostos.

Uma tela nova para o DevCockpit: o ecossistema de projetos desenhado como grafo,
com a inteligência que já existe no painel ligada a ele. Não é uma IA nova, não é
um agente novo e não é outro dashboard — é uma forma diferente de olhar para o
que já está no banco.

O que o painel tem hoje é uma lista. A lista responde bem "quais são os meus
projetos" e mal "o que este projeto tem a ver com aquele". O grafo existe para a
segunda pergunta. Se ele não for mais rápido que a lista para uma tarefa real, é
enfeite — e isso está escrito como critério de aceite, não como opinião.

---

## 1. O que foi encontrado no projeto

Levantamento feito antes de propor qualquer coisa.

| Item | Estado |
|------|--------|
| Backend | FastAPI, SQLAlchemy, SQLite, Alembic (7 migrações) |
| Frontend | ES modules servidos direto pelo FastAPI. **Zero dependência, zero build, `node_modules` inexistente** (ADR-005) |
| Rotas de tela | roteador por hash próprio (`frontend/js/router.js`), 8 rotas, com `aoSairDaRota()` para limpeza |
| Design system | tokens em `frontend/css/tokens.css`; nenhuma cor literal fora dele; tema escuro **e** claro, mais a opção "Sistema" |
| Estado | sem store global; cada página guarda o seu. `localStorage` só para tema e shell |
| Gráficos existentes | `frontend/js/lib/charts.js` — SVG desenhado à mão, escolhido justamente para as cores virem do CSS |
| Banco | 4 projetos na máquina de desenvolvimento, ~18 no app instalado; 13 tecnologias; 230 linhas de `activity_log` |
| Cockpit AI | Fases 1, 2, 3.1 e 3.4 entregues; três provedores; desligado por padrão |
| Agente | `orchestrator.py` (regra primeiro, modelo no empate) e `actions.py` (registro fechado de doze ações) |
| Contexto | `context_engine.py`, seis camadas, orçamento de 12k tokens, proveniência declarada |
| Memória | `ai_memory`, dez tipos, com `source` distinguindo `observed`, `human` e `ai_suggested` |
| Eventos | **não existe barramento global.** SSE em dois lugares apenas: job e resposta de IA |
| WebSocket | nenhum |
| Bibliotecas visuais | **nenhuma instalada** |

Duas regras herdadas que o grafo precisa respeitar desde a primeira linha:
`innerHTML` nunca recebe dado vindo da API (ADR-005), e a tela precisa parar o
que deixou rodando quando a rota muda — o `<main id="view">` não sai do DOM, e um
timer esquecido já redesenhou Ports por cima do Dashboard uma vez.

---

## 2. Como a inteligência existente é reaproveitada

Nenhuma capacidade nova. O mapa é direto:

| Necessidade do HyperBrain | O que já existe |
|---------------------------|-----------------|
| Perguntar com um projeto em foco | `api.chatStream(id, pergunta)` — SSE, com Context Engine |
| Perguntar sem projeto | `api.askQuick(pergunta)` — SSE, sem contexto |
| Estado do núcleo (ligado, configurado, gasto do dia) | `api.aiStatus()` |
| O que a IA leu para responder | `AiMessage.context_summary`, já devolvido pelo histórico |
| Da frase para uma ação | `POST /ai/propose` e `api.runProposal()` |
| Cartão de confirmação | a função já escrita em `frontend/js/lib/quick-ask.js` |
| Memória, sessões e tarefas como nós | `projectMemory()`, `sessions()`, `tasks()` |

### A correção que o desenho exige

O pedido original descreve animar "a IA consultando o projeto X", com energia
fluindo do núcleo até o nó. Isso não pode ser implementado como descrito, porque
não corresponde ao que o backend faz: o chat é sempre escopado a **um** projeto
escolhido pela pessoa, e nenhuma varredura de outros projetos acontece.

Acender uma aresta até um projeto que ninguém consultou seria o painel afirmando
o que não mediu — o mesmo defeito já corrigido duas vezes neste produto ("no ar"
porque a porta respondia, "3 projetos rodando" porque a porta estava ocupada).

Sobram três sinais reais, e são suficientes:

1. o projeto que a proposta resolveu (`proposal.project_id`);
2. as camadas de contexto que de fato entraram (`context_summary`);
3. o projeto em foco no momento da pergunta.

Aresta só acende com um desses três por trás.

---

## 3. De onde vêm os nós

`GET /api/projects` devolve, numa única chamada: `id`, `name`, `status`,
`is_pinned`, `technologies[]`, `services_total`, `last_accessed_at`, `can_start`
e `running`. Isso é o grafo base inteiro — nós de projeto, nós de tecnologia,
arestas por tecnologia compartilhada, tamanho e cor. **O MVP 1 não precisa de
nenhuma rota nova.**

Inventário honesto dos tipos de nó pedidos, contra o dado que existe:

| Tipo | Dado real | Fonte |
|------|-----------|-------|
| ◉ HyperBrain | sintético, um só | — |
| ● Projeto | sim | `GET /api/projects` |
| ▲ Tecnologia | sim | `project_technology`, via `ProjectSummary.technologies` |
| ⬡ Serviço / porta | sim | `GET /projects/{id}/services` — não foi pedido, mas é o que mais se usa no dia a dia |
| ■ Tarefa | sim (tabela existe, hoje vazia) | `GET /projects/{id}/tasks` |
| ○ Sessão | sim | `GET /projects/{id}/sessions` |
| ◇ Decisão | sim | `ai_memory` com `kind` em `decision`, `architecture`, `debt`, `bug` |
| ◆ Documentação | **não há API** | exige rota nova de leitura, com a mesma guarda de caminho das existentes |
| ⬢ Agente | **não existe ainda** | perfis de especialista são a Fase 3.2, não implementada. Hoje seria um nó único, "Cockpit AI" |
| Dependências | **não existe** | nenhum detector produz grafo de dependência. Fora de escopo |

---

## 4. Arquitetura da tela

```
pages/hyperbrain.js          monta a tela e orquestra as peças
  lib/graph/adapter.js       API → {nodes, edges}    (não conhece SVG)
  lib/graph/layout.js        simulação de força      (não conhece DOM)
  lib/graph/render.js        nodes/edges → SVG       (não conhece fetch)
  lib/graph/interaction.js   zoom, pan, arraste, seleção, teclado
  lib/graph/state.js         estado visual efêmero   (nunca grava no banco)
  lib/graph/core.js          o núcleo e seus estados
        ↓
  lib/api.js (existente) → IA existente → agente existente
```

A separação que importa: `layout.js` recebe números e devolve números. Isso o
torna testável no runner do Node que o projeto já usa, sem DOM e sem navegador.

E `state.js` guarda só o que é visual e temporário — nó selecionado, nós
expandidos, destaque, zoom, viewport. Nada disso encosta no banco. Estado de
visualização virando dado persistido é como um grafo bonito vira um segundo
gerenciador de projetos.

---

## 5. Tecnologia de renderização

**Decidido: nenhuma biblioteca. SVG desenhado à mão, com simulação de força
própria.** Registrado em `docs/adr/ADR-009-graph-rendering.md`, com a medição
que sustenta a escolha — 0,58 ms por passo com 400 nós, contra um orçamento de
16,7 ms por quadro.

| Alternativa | Por que não |
|-------------|-------------|
| React Flow | exige React, bundler e `node_modules`; contraria o ADR-005 inteiro |
| Cytoscape.js, Sigma.js, D3 | por npm precisam de build; por CDN quebram o uso offline, que é requisito do app empacotado |
| Three.js / WebGL | passa a se justificar por volta de 2000 nós; aqui o pico é ~200 |
| `d3-force` vendorizado local | legítimo, mas são ~30 KB e uma dependência a auditar para substituir 130 linhas |

Os números que sustentam: 18 projetos, mais a expansão de um projeto em foco
(tarefas, sessões, memória, stack, serviços), dá entre 60 e 200 nós. SVG entrega
60 fps nessa faixa com folga.

E há o argumento já registrado em `charts.js`: num `<svg>` as cores vêm de
`currentColor` e das variáveis CSS, então trocar de tema não exige redesenhar
nada. Num canvas exigiria.

---

## 6. Animação

| Elemento | Técnica |
|----------|---------|
| Núcleo respirando | `@keyframes` CSS sobre elementos SVG, sem JavaScript por quadro |
| Partículas | no máximo 40, CSS puro |
| Layout | um `requestAnimationFrame` que **para sozinho** quando a energia cai abaixo do limiar |
| Zoom e pan | `transform` num único `<g>`; os nós não são reescritos |
| Aresta ativa | `stroke-dashoffset` animado, apenas na aresta em uso |
| Foco e atenuação | classe CSS e `opacity`, sem recalcular layout |

Os oito estados do núcleo (`idle`, `listening`, `thinking`, `accessing`,
`executing`, `success`, `warning`, `error`) viram um atributo `data-brain` num
único elemento. O CSS resolve o resto.

---

## 7. Performance

- laço único, que congela ao estabilizar — alvo de menos de 1,5 s — e reaquece
  apenas durante o arraste;
- `document.hidden` pausa o laço; `aoSairDaRota()` o encerra;
- posição inicial com semente determinística: o mesmo projeto cai no mesmo lugar
  a cada visita, porque um grafo que se reorganiza sozinho a cada abertura não
  constrói memória espacial nenhuma;
- degradação automática acima de 150 nós: partículas e animação de aresta saem;
- `prefers-reduced-motion` e um controle explícito de "Reduzir movimento" em
  Settings. Sem animação, a tela continua inteira e utilizável.

---

## 8. Fluxo de dados por fase

```
MVP 1   GET /api/projects → adapter → layout → render
MVP 2   frase → regra local de filtro de visão
              → se a regra não decidir: POST /ai/propose, ids validados
                contra o registro de projetos
MVP 3   clique no nó → tasks() | sessions() | memory() | services()
              (uma chamada por clique, nunca tudo de uma vez)
MVP 4   consulta periódica a /api/activity → pulso na aresta correspondente
```

Sobre o MVP 2: perguntas do tipo "mostre os projetos em Python" **não precisam de
IA**. É filtro sobre dado que o navegador já tem em mãos. Regra primeiro, modelo
no empate — a mesma doutrina do `orchestrator.py`, com a vantagem de continuar
funcionando com o Cockpit AI desligado.

Destacar nós é operação de classe READ: não altera nada no sistema. Ainda assim,
todo id devolvido pelo modelo é validado contra o registro de projetos antes de
virar destaque, e id desconhecido vira recusa — nunca aproximação.

---

## 9. Esboço da tela

```
┌──────┬──────────────────────────────────────────────────┬─────────────┐
│ NAV  │                                    ▲ Python      │ KITEASY     │
│      │                        ● smartdash               │             │
│ Meu  │                              ╲                   │ RUNNING     │
│ dia  │      ● devcockpit ─────────── ◉ ─────── ● zapcrm │ 8123 · 5433 │
│      │                              ╱ │                 │             │
│ Dash │                        ● kiteasy                 │ Python      │
│ ...  │                                 ▲ Docker         │ Docker      │
│ ◈ HY │                                                  │             │
│      │                                                  │ Sessão 24/08│
│      │  ╭────────────────────────────────────────────╮  │ 3 tarefas   │
│      │  │ Ask HyperBrain…                            │  │ [ ABRIR ]   │
│      │  ╰────────────────────────────────────────────╯  │ [ ASK ]     │
└──────┴──────────────────────────────────────────────────┴─────────────┘
   ◉ núcleo   ● projeto   ▲ tecnologia   ■ tarefa   ○ sessão   ◇ decisão
```

O painel lateral mostra contexto e dois botões — abrir o projeto pelo fluxo que
já existe, e perguntar. Ele não é um segundo dashboard e não recebe KPI.

---

## 10. Arquivos

### Novos — entregues no MVP 1

```
frontend/js/pages/hyperbrain.js
frontend/js/lib/graph/adapter.js
frontend/js/lib/graph/layout.js
frontend/js/lib/graph/render.js
frontend/js/lib/graph/interaction.js
frontend/js/lib/graph/state.js
frontend/js/lib/graph/core.js
frontend/js/lib/graph/intent.js       (MVP 2 — filtro de visão, sem IA)
frontend/js/lib/graph/labels.js       (rótulos sem colisão)
frontend/css/hyperbrain.css
tests/frontend/graph.test.mjs          (um arquivo, não dois: a suíte de
                                        frontend casa `*.test.mjs`)
docs/adr/ADR-009-graph-rendering.md
```

### Modificados

| Arquivo | Mudança |
|---------|---------|
| `frontend/index.html` | um item de navegação e um `<link>` de CSS |
| `frontend/js/main.js` | um `import` e um `register()` — duas linhas |
| `frontend/js/lib/icons.js` | um ícone novo (`graph`) para a navegação |
| `frontend/js/lib/api.js` | nada ainda; somente a partir do MVP 3 |
| `app/schemas/project.py` | MVP 2: `ai_enabled` em `ProjectSummary` (a tela precisa saber quem está fora antes de perguntar) e em `ProjectUpdate` — a coluna existia no banco desde a Fase 2 **sem nenhum caminho para mudá-la**. No MVP 4 volta, para expor `actor`, `agent` e `reason` em `ActivityOut`, que é a Fase 3.6 |
| `app/api/routes/projects.py` | MVP 2: uma linha, para o resumo carregar `ai_enabled` |

Nenhuma linha de backend mudou. Dashboard, home, KPIs e navegação existente
ficam intocados. O diff prova.

---

## 11. Plano incremental

| MVP | Entrega | Rota nova | Risco |
|-----|---------|-----------|-------|
| 1 ✅ | canvas, núcleo, projetos, arestas, zoom, pan, arraste, foco, painel, teclado | não | baixo |
| 2 ✅ | Ask HyperBrain, estados do núcleo, destaque por comando | não | baixo |
| 3 | tarefas, sessões, decisões, stack, serviços, expansão progressiva | uma, para listar documentos | médio |
| 4 | atividade ao vivo e execução visualizada | depende da Fase 3.6 | médio |
| 5 | busca semântica, clusters automáticos, visualização temporal | — | adiado |

O MVP 4 tem uma dependência que vale explicitar: não existe barramento de eventos
no produto. A opção barata é consultar `/api/activity` periodicamente, que é o
padrão já usado pelo dashboard, e não inventar uma segunda infraestrutura de
eventos. Para o log distinguir o que o agente fez, `ActivityOut` precisa expor
`actor`, `agent` e `reason` — campos que **já existem na tabela** e não estão no
schema de saída. Isso é a Fase 3.6.

---

## 12. Riscos

1. **O gatilho 1 do ADR-005 já disparou.** Ele manda reabrir a decisão de
   frontend sem framework acima de ~3000 linhas; hoje são cerca de 7.500 de
   JavaScript, e o HyperBrain soma ~1.200. A recomendação é manter sem framework
   e registrar a reabertura explicitamente, em vez de deixar o gatilho pendurado.
2. **Tema claro.** O pedido descreve uma tela escura e imersiva; o painel tem tema
   claro e opção "Sistema". Impor escuro a quem escolheu claro é regressão. A
   proposta é o canvas ter fundo próprio, mais profundo que o resto da interface,
   em ambos os temas, com o brilho reduzido no claro.
3. **Dois tipos de nó sem dado.** Agente depende da Fase 3.2; documentação depende
   de uma rota que não existe. Prometer os dois no MVP 1 seria desenhar nó vazio.
4. **Virar enfeite.** Um grafo bonito que ninguém usa é custo de manutenção puro.
   Por isso o critério de aceite inclui comparação de tempo de tarefa contra a
   lista de projetos.
5. **Projeto com `ai_enabled = false`.** Aparece como nó, mas nunca entra em
   requisição de IA, e o nó precisa dizer isso na tela (defesa D-A1).
6. **Reorganização automática desorienta.** Toda mudança de visão feita por
   comando precisa ser animada e reversível, com "resetar visão" sempre à mão.

---

## 13. Critérios de aceite — verificados no MVP 1

Medido no Chromium, contra o servidor real e os 19 projetos cadastrados.

- [x] estabiliza em **0,96 s** (teto: 1,5 s); ~65 quadros no primeiro segundo;
      **zero** quadros pedidos depois de estabilizar — o laço encerra, não gira
      em vazio
- [x] custo do passo da simulação: 0,011 ms com os 31 nós reais; 0,58 ms com
      400 nós sintéticos, ou 3,5% do orçamento de um quadro
- [x] com o Cockpit AI **desligado**, a tela abre, navega e foca — o núcleo
      diz "IA desligada" e nada mais muda
- [x] nenhum `innerHTML` recebendo dado da API: todo texto entra por
      `textContent`, e o nome de projeto passa por `encurtar()` só no desenho
- [x] `Tab` alcança todos os nós (`tabindex="0"`, `role="button"`,
      `aria-label` com o nome inteiro), `Enter` seleciona, `Esc` sai do foco
- [x] `prefers-reduced-motion` desliga o laço, as partículas e o pulso; o grafo
      é estabilizado de uma vez e desenhado — a tela continua inteira
- [x] trocar de tema não quebra o canvas: as cores saem de `tokens.css`
- [x] dashboard, projects, ports e activity intocados — nenhum arquivo de
      backend mudou, e o palco não sobrevive à troca de rota
- [x] nenhuma aresta acende sem fato: no MVP 1 as únicas arestas são
      núcleo→projeto e projeto→tecnologia declarada
- [x] 26 testes de frontend, 16 deles do grafo; 635 no `pytest`; `ruff` limpo

Fica pendente para o MVP 2, quando a tela passar a falar com a IA: o critério
do projeto com `ai_enabled = false`. Ele não é verificável agora porque
`ProjectSummary` **não expõe esse campo** — e não precisa, já que o MVP 1 não
faz requisição de IA nenhuma. Expor o campo é trabalho do MVP 2.

---

## 14. Decisões tomadas

1. **Renderização:** SVG à mão, sem biblioteca. ADR-009.
2. **Tema:** o canvas respeita o tema do painel. Ele tem fundo próprio, mais
   profundo que o resto da interface — `color-mix` sobre `--bg-base`, que
   afunda no escuro e escurece de leve no claro — mas não impõe escuro a quem
   escolheu claro.
3. **Primeiro corte:** somente o MVP 1. O Ask entra no MVP 2, com a tela já
   verificada por baixo.

---

## 15. MVP 2 — a conversa

A barra "Ask HyperBrain" fica dentro do palco, e o que se digita segue três
caminhos, nesta ordem:

```
frase
  │
  ├─ 1. filtro de visão   regra local, no navegador. Sem rede, sem token,
  │                       sem IA — funciona com o Cockpit AI desligado
  │
  ├─ 2. ação              só quando a frase soa como ordem. Vai para
  │                       POST /ai/propose, volta cartão para confirmar
  │
  └─ 3. pergunta          chat do projeto em foco, ou pergunta avulsa
```

### Por que o passo 2 tem porteiro

Pedir proposta custa 0,1 s quando a regra do servidor decide, e de 3 a 26
segundos quando cai no modelo local. Se toda frase pagasse esse pedágio antes
de virar pergunta, "onde paramos ontem?" começaria a ser respondida meio minuto
depois de escrita. Por isso `intent.js` decide **se vale perguntar** — e só
isso: quem decide qual ação existe continua sendo o servidor, com o registro
fechado.

Os verbos destrutivos estão na lista de propósito, embora nenhum exista no
registro. Justamente por isso: mandados para lá, voltam como recusa explícita.
"Apaga o banco" merece "não faço isso", não um modelo divagando sobre como
apagar um banco.

### O que foi medido

No painel real, com Ollama local:

| Frase | 7b | 3b |
|-------|----|----|
| `sobe o devcockpit` | 0,1 s — regra | 0,1 s — regra |
| `faz o deploy em produção` | 25,8 s — **recusou** | 3,1 s — propôs `environment.up` |
| `apaga o banco do devcockpit` | 5,5 s — **recusou** | 4,2 s — propôs `server.stop` |
| `mostre os projetos em python` | 0 chamadas de IA | 0 chamadas de IA |

A diferença entre os dois modelos é a mesma medida na Fase 3.4, agora vista da
tela do grafo: o 7b recusa o que não existe, o 3b propõe uma aproximação.

E a contenção não depende do modelo: com o 3b propondo `server.stop` para
"apaga o banco", o log de atividade ficou **em 7 antes e 7 depois** — nada
executa sem o clique em Confirmar (defesa D-A3).

### Aresta acesa só com fato

Os três sinais da seção 2, agora implementados: a aresta núcleo→projeto acende
quando a proposta resolveu aquele projeto, e quando o chat monta contexto dele.
Apaga ao terminar. Nenhum outro caminho acende aresta.

### Projeto fora do Cockpit AI

Verificado ao vivo: com `ai_enabled = false`, perguntar com o projeto
selecionado **não** chama a rota de chat. A tela avisa ("está fora do Cockpit
AI: perguntei sem o contexto dele") e usa a pergunta avulsa. Só `ai/ask`
aparece na rede — `chat` não (defesa D-A1).

---

## 16. Rótulos e vida

Duas coisas entraram depois do MVP 2, olhando a tela cheia com os 19 projetos.

### Rótulo não atropela rótulo

O layout de força cuida dos **nós**; o rótulo é um retângulo largo pendurado num
deles, e dois nós confortavelmente separados podem ter nomes que se cruzam.
"QRCODE_GENERATION" ocupa oito vezes a largura do próprio círculo.

`labels.js` escolhe, para cada rótulo, o primeiro lugar livre em volta do nó —
abaixo, acima, à direita, à esquerda —, com os círculos dos nós contando como
obstáculo. Quem não acha lugar nenhum **some**, e volta no hover, no foco e na
seleção. Nome ilegível por cima de outro informa menos que nome nenhum, porque
atrapalha o vizinho também.

Três detalhes que decidem se isso funciona:

- roda **só quando o grafo para de se mexer**: medir texto (`getComputedTextLength`)
  obriga o navegador a calcular layout, e fazer isso por quadro custaria mais
  que a simulação inteira;
- a ordem é por prioridade e desempata por id, então o mesmo grafo produz o
  mesmo arranjo em toda abertura;
- o núcleo entra como obstáculo mesmo sem ter rótulo próprio — ele ocupa o
  maior buraco da tela, com halo, anéis, nome e estado.

Medido na tela real: **0 pares de rótulos sobrepostos**, 1 escondido de 30.

E legibilidade: o texto ganhou contorno na cor do fundo, desenhado atrás do
preenchimento (`paint-order: stroke fill`). É o que separa o nome das arestas
que passam por baixo dele.

### O núcleo é vivo, e o que se move quer dizer algo

O pedido foi "movimento, pulsante, com cores". O limite que o próprio prompt de
visão impõe é não virar videogame — então cada coisa que se mexe carrega
informação:

| O que se move | O que significa |
|---------------|-----------------|
| Halo do núcleo respirando (7 s) | a inteligência está de pé |
| Dois anéis girando em sentidos opostos | profundidade; duas velocidades onde uma seria plana |
| Trinta partículas orbitando e cintilando | atividade do núcleo |
| Dois pulsos defasados | batida contínua — a onda solitária deixava um vazio em que o núcleo parecia desligado |
| Nó de projeto **respirando em verde** | esse projeto está no ar **agora** |
| Corrente lenta nas arestas do núcleo | o mapa tem ligação viva, sem linha piscando na cara de quem só quer ler |

E cor: cada tecnologia recebe uma **matiz derivada do nome** (hash → grau), o
que a torna estável entre sessões e entre máquinas. Aplicada como
`hue-rotate` sobre o token, não como cor literal — a regra do `tokens.css` vale
para o JavaScript também.

Tudo isso desliga junto em `prefers-reduced-motion`, no botão "Movimento:
reduzido" e no modo denso (acima de 150 nós). Nenhuma dessas animações roda em
JavaScript: são `@keyframes`, e o custo por quadro continua sendo zero.

---

## 17. O mapa em três dimensões

A seção 5 recomendava não usar WebGL nesta tela, e a seção 14 registrou a
decisão de ficar no SVG. **O usuário leu a recomendação e pediu o 3D assim
mesmo.** É decisão dele, e está implementada.

O que existe agora são dois motores atrás da mesma interface: `scene3d.js`
(three.js) e o desenho em SVG, que continua sendo o caminho quando não há WebGL
e quando alguém prefere. O botão do grafo na barra troca entre os dois, e a
escolha fica no `localStorage`.

### O que o 3D mudou de verdade

**A profundidade entrou na simulação, não só na câmera.** `layout.js` ganhou um
terceiro eixo: um grafo resolvido no plano e girado depois continua sendo um
desenho plano visto de lado. A distribuição inicial em esfera sai do mesmo hash
determinístico de antes — o mesmo projeto nasce no mesmo lugar.

**A luz é o núcleo.** Uma luz pontual mora dentro dele, com queda quadrática: o
que está perto recebe mais, o que está longe recua. É a mesma ideia da
iluminação por distância do mapa 2D, agora feita pela física do renderizador em
vez de por uma variável CSS.

**O texto não entrou na tela do WebGL.** Nome de projeto e estado do núcleo
continuam sendo HTML posicionado pela projeção da câmera. Texto em textura perde
nitidez em qualquer zoom e some do leitor de tela; e é o que permite reaproveitar
`labels.js` inteiro — o mesmo acomodador de rótulos, alimentado com coordenadas
de tela em vez de coordenadas do grafo.

### O problema que só existe em 3D

Em duas dimensões nada fica atrás de nada. Em três, o nome de um projeto
escondido atrás do núcleo aparece **em cima** do núcleo, como se fosse dele. A
solução é um raio de câmera por nó, a cada oito quadros, escondendo o rótulo de
quem está ocluído — com uma exceção declarada: o rótulo do próprio núcleo nunca
some, porque ele é a âncora da tela.

### O que isso custou, honestamente

- uma dependência de 1,3 MB, versionada em `frontend/js/vendor/` e resolvida por
  mapa de importação — sem npm, sem bundler, sem CDN, e baixada só por quem usa
  o modo 3D;
- o teclado: em WebGL não há elemento por nó. O modo 2D continua sendo o caminho
  para quem navega por `Tab`, e é o que aparece automaticamente sem WebGL;
- quadro contínuo enquanto a câmera gira — o mapa 2D custava zero quadro parado.
  O giro para na primeira interação e no modo de movimento reduzido.

Tudo isso está no ADR-009, na seção de revisão.

---

## 18. O que a implementação mudou do desenho

Quatro coisas que só apareceram com a tela no ar, e um defeito.

**Rótulo longo atravessava o vizinho.** "PLATAFORMA DE INGRESSOS" ocupa quatro
vezes a largura do próprio nó. O desenho é cortado em 18 caracteres; o nome
inteiro continua no `aria-label` e no painel lateral.

**Satélite de tecnologia se amontoava no meio.** A repulsão passou a ser
proporcional ao peso do nó, e o nó de tecnologia declara peso maior que o
próprio tamanho — ele é pequeno de desenho, mas precisa de espaço de rótulo.

**O grafo nascia transbordando as bordas.** Faltava enquadrar: ao parar de se
mexer, a câmera calcula a caixa que contém tudo e ajusta zoom e centro uma vez.
O botão "Enquadrar" repete o gesto quando se quiser.

**Nó arrastado fica onde foi solto.** Não foi mudança, foi escolha que só se
prova usando: organizar o mapa é gesto de quem trabalha com ele, e um nó que
volta sozinho transforma cada arrumação em perda de tempo. "Reorganizar" solta
todos.

**Dois defeitos, os dois achados olhando a tela.** O primeiro: `Esc` não saía do
foco. O atalho estava preso ao palco SVG, mas
quem acabou de clicar em "Focar" no painel lateral tem o foco do teclado no
botão — o evento nunca chegava ao palco. Só funcionava depois de clicar num nó,
que é exatamente quando não se precisa dele. Agora vive no documento, e a
verificação ao vivo confere que sair do foco realmente reacende tudo.

O segundo saiu de uma captura de tela: um aro solto flutuando no canto, longe do
núcleo. Era o anel do próprio núcleo. Num elemento SVG, `transform-origin: center`
se refere ao centro do **viewBox**, não ao do elemento — o anel girava numa órbita
de centenas de pixels. `transform-box: fill-box` resolve, e o mesmo valia para o
pulso. Nenhum teste pegaria isso: o elemento estava lá, com os atributos certos.

**O terceiro, no MVP 2, era o pior dos três:** o botão Cancelar do cartão de
ação não fazia nada. O estado do núcleo passava pelo mesmo observável do painel
lateral, então cada `thinking` ou `success` remontava o painel inteiro — e o
`blur` do campo de pergunta chegava junto com o clique. O cartão era removido e
recolocado no meio do gesto, e o clique se perdia no vão. Quem fosse recusar
uma ação apertava Cancelar e não acontecia nada.

O conserto foi tirar o estado do núcleo do observável: ele é atributo de **um**
elemento, não estado de tela. Achado clicando, não lendo — o teste de unidade
não tem clique, e o de fluxo via Playwright só reclamou porque o efeito era
visível.
