## 2026-08-25 (madrugada) — Sessão 24: o 3D que não vingou, e o núcleo que passou a bater

Sessão longa, com uma reversão no meio. O que ficou de pé: o mapa 2D com
rótulos que não se atropelam e um núcleo com batimento. O que caiu: o 3D
inteiro, por decisão sua depois de ele travar duas vezes na sua máquina.

### Rótulos: o problema que a força não resolve

A simulação cuida dos **nós**; o rótulo é um retângulo largo pendurado num
deles. "QRCODE_GENERATION" ocupa oito vezes a largura do próprio círculo, e dois
nós confortavelmente separados podem ter nomes que se cruzam.

`labels.js` escolhe, para cada rótulo, o primeiro lugar livre em volta do nó —
abaixo, acima, direita, esquerda — com os nós e o núcleo contando como
obstáculo. Quem não acha lugar some e volta no hover. Roda **só quando o grafo
para**: medir texto obriga o navegador a calcular layout.

Medido na tela real: **0 pares sobrepostos**, 1 escondido de 30.

### A tentativa de 3D, e por que ela foi revertida

Você pediu o 3D depois de eu recomendar contra. Foi implementado: three.js r170
vendorizado (sem npm, sem CDN, com mapa de importação), terceiro eixo na
simulação, luz no núcleo, rótulos continuando no DOM, oclusão por raio, anel de
seleção, neblina e poeira para paralaxe.

Você aprovou uma versão ("ficou incrível") e pediu refino. Depois disso a tela
**travou**, e não voltou a ser usável. Decisão sua: voltar ao mapa plano.

**A causa do travamento não era o WebGL.** Eram dois defeitos meus no código em
volta dele, e os dois valem ficar escritos porque qualquer tentativa futura vai
esbarrar neles:

1. **Eu media `offsetWidth` de cada rótulo a cada quadro.** Ler essa propriedade
   força o navegador a recalcular o layout na hora — trinta vezes por quadro,
   logo depois de escrever os `transform`. É *layout thrashing* clássico: o
   quadro para e espera.
2. **A oclusão testava triângulo a triângulo.** Um `Raycaster` por nó contra a
   geometria real: 31 nós × ~1.100 triângulos × 31 raios ≈ um milhão de testes a
   cada oito quadros. Vira conta de esfera em trinta multiplicações.

Os dois foram corrigidos antes da reversão, e a correção está no histórico
(66a6b3c, e5f87e2). Reverti com `revert`, não com `reset`: os commits continuam
recuperáveis com um revert do revert.

Fica também o achado de plataforma: quando o navegador bloqueia a GPU, o WebGL
**continua existindo**, emulado na CPU pelo SwiftShader. A tela não fica lenta,
fica travada — e `getContext('webgl')` devolvendo um contexto não prova nada. O
teste que presta é ler `WEBGL_debug_renderer_info` e recusar quando o nome bate
com swiftshader/llvmpipe/software.

### Outros dois defeitos achados clicando

- **O botão Cancelar do cartão de ação não fazia nada.** O estado do núcleo
  passava pelo mesmo observável do painel lateral, então cada `thinking` ou
  `success` remontava o painel — e o `blur` do campo de pergunta chegava junto
  com o clique. O cartão saía e voltava no meio do gesto, e o clique se perdia.
  Quem fosse **recusar** uma ação apertava Cancelar e não acontecia nada.
- **`transform-origin: center` em elemento SVG** se refere ao centro do
  *viewBox*, não ao do elemento. O anel do núcleo girava numa órbita de centenas
  de pixels, aparecendo como um aro solto no canto da tela. `transform-box:
  fill-box` resolve.

### O núcleo passou a bater

O disco ganhou batimento em vez de respiração — contrai rápido e solta devagar,
com contragolpe. A curva simétrica lê como pulsação de aparelho; esta lê como
algo vivo. Junto: um arco curto girando em 3,6 s, três pulsos defasados, poeira
quase duas vezes mais rápida.

O ritmo é informação: pronto 3,2 s, ouvindo 2,2 s, **pensando 1,5 s**,
desligado **parado**. Tudo em CSS, sem um quadro de JavaScript, e desliga junto
em `prefers-reduced-motion`.

### Verificação executada

| O que | Resultado |
|---|---|
| `pytest -q` | **636 passaram**, 1 pulado, 3 desmarcados |
| `node --test tests/frontend/*.test.mjs` | **42 passaram** |
| `ruff check .` | limpo |
| Mapa ao vivo, 19 projetos reais | 31 nós, **0 rótulos sobrepostos**, console limpo |
| Filtro `mostre os projetos em python` | responde com **zero chamada de IA** |
| Executável reconstruído e instalado | 321 arquivos, **idêntico ao build** |

### Situação ao encerrar

Branch `main`, árvore limpa, tudo publicado (`378c14d`). O app instalado roda na
**8765** — e não na 8790: a 8790 vinha do ambiente de quem lançou o app antes, e
não está gravada em configuração nenhuma.

Aceito como está, não pendente: o HyperBrain é 2D. A decisão foi sua, depois de
ver o 3D falhar.

Pendente de verdade:

- `ai_enabled` tem rota, mas **não tem botão**: só muda por `PATCH`
- `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- Cockpit AI: faltam 3.2, 3.3, 3.5 e 3.6; MVPs 3 a 5 do HyperBrain não começaram

### Próximo passo

**Usar a tela por alguns dias antes de mexer nela de novo.** O MVP 3 (tarefas,
sessões e decisões como nós) só faz sentido depois de o mapa provar que serve
para alguma coisa no dia a dia — e esta sessão mostrou o custo de empilhar
camada visual sem esse teste.

---

