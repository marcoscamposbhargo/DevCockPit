## 2026-08-25 (continuação) — Sessão 22: o ecossistema vira mapa

Pedido novo, e com uma regra dura no enunciado: **não criar outra IA, não criar
outro agente, não criar outro dashboard.** Dar forma visual ao que já existe.

Antes de escrever código, um levantamento e uma proposta — `docs/ai/HYPERBRAIN.md`,
com estado atual, arquitetura, riscos e critérios de aceite. Três decisões
ficaram travando o início: biblioteca de grafo, tema, e tamanho do primeiro
corte.

### A correção que a proposta precisou fazer

O pedido descrevia animar "a IA consultando o projeto X", com energia fluindo do
núcleo até o nó. Isso não corresponde ao que o backend faz: o chat é sempre
escopado a **um** projeto que a pessoa escolheu, e nenhuma varredura dos outros
acontece. Acender uma aresta até um projeto que ninguém consultou seria o painel
afirmando o que não mediu — o mesmo defeito já corrigido duas vezes aqui ("no
ar" porque a porta respondia, "3 projetos rodando" porque a porta estava
ocupada).

Sobraram três sinais que são fato: o projeto que a proposta resolveu, as camadas
de contexto que de fato entraram, e o projeto em foco. Aresta só acende com um
desses três por trás.

### Nenhuma biblioteca, e o número que decide

React Flow, Cytoscape, Sigma, D3 e Three.js entraram na comparação. Todas caem
no mesmo ponto: por npm trazem build e `node_modules`, contra o ADR-005; por CDN
quebram o uso offline do executável.

Faltava o dado do meio — quantos nós. Com os 19 projetos cadastrados, 31 nós e
72 arestas. Com a expansão prevista para as fases seguintes, 60 a 200.

Medido no Chromium, um passo da simulação:

| Nós | ms por passo |
|-----|--------------|
| 31 (real) | 0,011 |
| 100 | 0,039 |
| 200 | 0,156 |
| 400 | 0,576 |

O orçamento de um quadro a 60 fps é 16,7 ms. Com 400 nós — o dobro do teto
previsto — a simulação usa 3,5% dele. WebGL resolveria um problema que este
projeto não tem. SVG à mão, e ADR-009 registrando por quê.

### O que a tela faz

Núcleo no centro, os projetos ao redor, e as tecnologias **compartilhadas** como
satélites que ligam projeto a projeto. Tecnologia usada por um projeto só não
vira nó: ela não relaciona nada, e o nome já está no painel lateral.

Zoom, deslocamento, arraste, foco (o nó e seus vizinhos ficam nítidos, o resto
atenua), painel de contexto com dois caminhos — abrir o projeto pelo fluxo de
sempre, ou focar. Ligar, parar, portas e Git continuam na tela do projeto.

O núcleo diz o estado da IA, e diz a verdade: com o Cockpit AI desligado, ele
mostra "IA desligada" e o resto da tela funciona igual. **O grafo é dado, não
IA** — nenhuma linha de backend mudou.

Na tela: estabiliza em 0,96 s, ~65 quadros no primeiro segundo, e **zero**
quadros pedidos depois disso. O laço encerra em vez de girar em vazio.

### Quatro ajustes que só apareceram com a tela no ar

- **rótulo longo atravessava o vizinho** — "PLATAFORMA DE INGRESSOS" ocupa
  quatro vezes a largura do nó. Cortado em 18 caracteres no desenho; o nome
  inteiro fica no `aria-label` e no painel;
- **satélites amontoados no meio** — a repulsão passou a ser proporcional ao
  peso do nó, e a tecnologia declara peso maior que o próprio tamanho;
- **o grafo nascia transbordando as bordas** — ao parar de se mexer, a câmera
  calcula a caixa que contém tudo e enquadra uma vez;
- **nó arrastado fica onde foi solto** — organizar o mapa é gesto de quem
  trabalha com ele. "Reorganizar" solta todos.

### Dois defeitos, os dois achados olhando a tela

`Esc` não saía do foco. O atalho estava preso ao palco SVG, mas quem acabou de
clicar em "Focar" no painel lateral tem o foco do teclado no botão — o evento
nunca chegava ao palco. Ou seja: só funcionava depois de clicar num nó, que é
exatamente quando não se precisa dele. Achado pela verificação ao vivo, não por
leitura de código.

O segundo apareceu numa captura de tela: um aro solto flutuando no canto, longe
do núcleo. Era o anel do próprio núcleo. Num elemento SVG, `transform-origin:
center` se refere ao centro do **viewBox**, e não ao do elemento — o anel girava
numa órbita de centenas de pixels. `transform-box: fill-box` resolve. Nenhum
teste pegaria: o elemento estava lá, com os atributos certos. Foi preciso olhar.

16 testes novos no grafo (26 de frontend), 635 no `pytest`, `ruff` limpo.

### Continua com você

- [ ] **usar a tela antes do MVP 2.** O Ask ligado à IA existente é o próximo
      corte, mas o que ele deve destacar depende de o mapa provar que serve
- [ ] o MVP 2 precisa expor `ai_enabled` em `ProjectSummary`: projeto excluído
      da IA tem que aparecer diferente antes de a tela falar com modelo nenhum
- [ ] as três pendências da sessão 21 seguem de pé — modelo padrão do Ollama,
      Fase 3 (3.2, 3.3, 3.5, 3.6) e a decisão sobre `Dockerfile`

---

