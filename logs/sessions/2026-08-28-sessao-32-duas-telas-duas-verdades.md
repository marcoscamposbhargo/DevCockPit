## 2026-08-28 (parte 2) — Sessão 32: duas telas, duas verdades

Varredura do **padrão 1** — duas fontes para o mesmo fato, e ninguém checa se
concordam. Dois achados, e o segundo veio no caminho do primeiro.

### O mesmo botão, respostas opostas

`powerToggle` aparece em duas telas, e cada uma decidia o estado dele sozinha:

| Tela | Regra | O que errava |
|---|---|---|
| Projects | `app_running` | "Desligado" para aplicação servida por container |
| Barra lateral | `online > 0` | "Ligado" com só o Postgres de pé — a confusão do ZAPBOT |

Reproduzido no AgilContabil, com a aplicação respondendo na 8100 por container e
sem processo nativo: a lateral dizia "Ligado", o card dizia "Desligado", mesmo
projeto, mesma hora.

`aplicacaoNoAr` passou a responder pelas duas, em ordem de evidência: o que foi
medido sobre a aplicação primeiro, o processo nativo depois, "algum serviço" só
como último recurso.

O detalhe que decide qual das duas estava mais errada: **o botão desliga
aplicação em container também** (`environmentDown` devolve `stopped: 'docker'`).
Dizer "Desligado" ali não era impreciso — era esconder o desligar de quem
queria desligar.

Verificado na tela renderizada: card e lateral dizendo "Ligado · 5 no ar" para
o mesmo projeto.

### Um número que não era daquele chip

O chip do Docker recebia a contagem de **serviços que respondem** e falava de
**containers**. Hoje coincidiam — 5 e 5 —, e coincidência não é acerto: num
projeto com aplicação nativa e um container, ele diria "2 no ar" para um
container só.

Contar container de verdade custaria um `docker ps` por card, que a NFR-010
proíbe na lista. Entre um número preciso e errado e uma afirmação verdadeira sem
número, ficou a segunda: "ambiente no ar". O card já mostra "5/6 online" logo
acima.

### Achado registrado e não consertado

Em `projects.js`, o ramo `'clean'` do chip de Git é **inalcançável**:
`_pending_changes` só inclui projeto com `dirty_count > 0`, então repositório
limpo nunca chega lá. Não é defeito visível — é código morto que promete um
sinal que a tela não dá. Consertar é decidir se repositório limpo merece chip,
e isso é escolha de produto.

### Situação ao encerrar

Publicado até `74a53fe`. 704 testes, 58 no frontend, ruff limpo. Painel
instalado igual ao build, uma instância com janela.

**Estado da máquina:** a aplicação do AgilContabil está no ar **em container**
(`agilcontabil-backend-1` publica a 8100); o servidor nativo dele foi parado
durante a reprodução e não foi religado — subir os dois disputaria a porta.

### Próximo passo

Do prompt, o padrão 4 fora do dashboard segue por varrer. A dívida das três
definições de "qual serviço é a aplicação" continua aberta, e agora tem uma
quarta pergunta parecida respondida em `aplicacaoNoAr` — vale checar se elas
podem convergir num lugar só.

