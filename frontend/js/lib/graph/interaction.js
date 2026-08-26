// Zoom, deslocamento, arraste e teclado.
//
// Um detalhe que decide se o grafo é usável: **arrastar um nó o prende onde
// foi solto.** Organizar o mapa é um gesto de quem trabalha com ele, e um nó
// que volta sozinho para o lugar anterior transforma cada arrumação em perda
// de tempo. "Reorganizar" solta todos de novo.
//
// Todo o zoom e todo o deslocamento acontecem num único `transform` do grupo
// viewport. Os nós não são reescritos, e é por isso que a tela aguenta o
// gesto contínuo sem engasgar.

const ESCALA_MINIMA = 0.3;
const ESCALA_MAXIMA = 2.6;
//: Abaixo disto o ponteiro andou por tremor de mão, não por intenção de
//: arrastar — e o gesto deve valer como clique.
const ARRASTE_MINIMO = 4;

export function ligarInteracao({ svg, viewport, layout, palco }, acoes = {}) {
  const camera = { x: 0, y: 0, escala: 1 };
  const descartar = [];

  function aplicarCamera() {
    viewport.setAttribute(
      'transform',
      `translate(${camera.x.toFixed(2)} ${camera.y.toFixed(2)}) scale(${camera.escala.toFixed(3)})`
    );
  }

  function tamanho() {
    const caixa = svg.getBoundingClientRect();
    return { largura: caixa.width, altura: caixa.height, caixa };
  }

  function paraGrafo(evento) {
    const { caixa } = tamanho();
    return {
      x: (evento.clientX - caixa.left - camera.x) / camera.escala,
      y: (evento.clientY - caixa.top - camera.y) / camera.escala,
    };
  }

  function centralizar() {
    const { largura, altura } = tamanho();
    camera.x = largura / 2;
    camera.y = altura / 2;
    aplicarCamera();
  }

  /** Ajusta zoom e centro para o grafo inteiro caber na tela.
   *
   * Sem isto, um ecossistema com muitos projetos nasce transbordando as
   * bordas: os nós existem, mas metade fica fora da viewport e a pessoa
   * precisa descobrir sozinha que aquilo se arrasta. Enquadrar é o gesto que
   * um mapa faz por quem o abre.
   */
  function enquadrar(posicoes, { margem = 72 } = {}) {
    const pontos = [...posicoes.values()];
    if (!pontos.length) return;

    const xs = pontos.map((p) => p.x);
    const ys = pontos.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const { largura, altura } = tamanho();
    if (!largura || !altura) return;

    const escala = Math.min(
      ESCALA_MAXIMA,
      Math.max(
        ESCALA_MINIMA,
        Math.min(
          (largura - margem * 2) / Math.max(maxX - minX, 1),
          (altura - margem * 2) / Math.max(maxY - minY, 1),
          // Nunca amplia além do tamanho natural: um grafo de três nós
          // ocupando a tela inteira parece defeito, não destaque.
          1
        )
      )
    );

    camera.escala = escala;
    camera.x = largura / 2 - ((minX + maxX) / 2) * escala;
    camera.y = altura / 2 - ((minY + maxY) / 2) * escala;
    aplicarCamera();
  }

  function zoomEm(fator, ancoraX, ancoraY) {
    const anterior = camera.escala;
    const nova = Math.min(ESCALA_MAXIMA, Math.max(ESCALA_MINIMA, anterior * fator));
    if (nova === anterior) return;

    // Mantém sob o ponteiro o mesmo ponto do grafo: sem isto, aproximar joga
    // para fora da tela justamente o que se queria olhar de perto.
    camera.x = ancoraX - ((ancoraX - camera.x) * nova) / anterior;
    camera.y = ancoraY - ((ancoraY - camera.y) * nova) / anterior;
    camera.escala = nova;
    aplicarCamera();
  }

  function ouvir(alvo, tipo, fn, opcoes) {
    alvo.addEventListener(tipo, fn, opcoes);
    descartar.push(() => alvo.removeEventListener(tipo, fn, opcoes));
  }

  // --- roda: zoom ---------------------------------------------------------

  ouvir(
    svg,
    'wheel',
    (evento) => {
      evento.preventDefault();
      const { caixa } = tamanho();
      zoomEm(
        evento.deltaY < 0 ? 1.12 : 1 / 1.12,
        evento.clientX - caixa.left,
        evento.clientY - caixa.top
      );
    },
    { passive: false }
  );

  // --- ponteiro: arrastar nó ou deslocar o fundo ---------------------------

  let gesto = null;

  ouvir(svg, 'pointerdown', (evento) => {
    if (evento.button !== 0) return;
    const grupo = evento.target.closest?.('.hb-node');

    gesto = {
      no: grupo?.dataset.id ?? null,
      partidaX: evento.clientX,
      partidaY: evento.clientY,
      cameraX: camera.x,
      cameraY: camera.y,
      moveu: false,
    };

    svg.setPointerCapture?.(evento.pointerId);
    svg.dataset.arrastando = gesto.no ? 'no' : 'fundo';
  });

  ouvir(svg, 'pointermove', (evento) => {
    if (!gesto) return;

    const dx = evento.clientX - gesto.partidaX;
    const dy = evento.clientY - gesto.partidaY;
    if (!gesto.moveu && Math.hypot(dx, dy) < ARRASTE_MINIMO) return;
    gesto.moveu = true;

    if (gesto.no) {
      const { x, y } = paraGrafo(evento);
      layout.fixar(gesto.no, x, y);
      layout.reaquecer(0.3);
      acoes.aoMover?.();
    } else {
      camera.x = gesto.cameraX + dx;
      camera.y = gesto.cameraY + dy;
      aplicarCamera();
    }
  });

  function encerrarGesto(evento) {
    if (!gesto) return;
    const { no, moveu } = gesto;
    gesto = null;
    delete svg.dataset.arrastando;
    svg.releasePointerCapture?.(evento.pointerId);

    // Clique é arraste que não andou. Tratar os dois no mesmo lugar evita o
    // clássico "selecionou sozinho ao terminar de arrastar".
    if (!moveu) acoes.aoSelecionar?.(no);
  }

  ouvir(svg, 'pointerup', encerrarGesto);
  ouvir(svg, 'pointercancel', encerrarGesto);

  // --- teclado ------------------------------------------------------------

  ouvir(svg, 'keydown', (evento) => {
    const grupo = evento.target.closest?.('.hb-node');

    if (evento.key === 'Enter' || evento.key === ' ') {
      if (!grupo) return;
      evento.preventDefault();
      acoes.aoSelecionar?.(grupo.dataset.id);
      return;
    }

    // Esc **não** é tratado aqui: quem sai do foco pode ter clicado num botão
    // do painel lateral, e aí o evento nunca chega ao palco. Ele vive no
    // documento, montado pela página.
    const { largura, altura } = tamanho();
    if (evento.key === '+' || evento.key === '=') zoomEm(1.2, largura / 2, altura / 2);
    else if (evento.key === '-') zoomEm(1 / 1.2, largura / 2, altura / 2);
    else if (evento.key === '0') {
      camera.escala = 1;
      centralizar();
    }
  });

  return {
    camera,
    centralizar,
    enquadrar,
    aplicarCamera,
    ampliar: () => {
      const { largura, altura } = tamanho();
      zoomEm(1.2, largura / 2, altura / 2);
    },
    reduzir: () => {
      const { largura, altura } = tamanho();
      zoomEm(1 / 1.2, largura / 2, altura / 2);
    },
    /** Solta todos os nós presos e devolve a câmera ao começo. */
    reorganizar(nos) {
      for (const no of nos) if (!no.fixo) layout.soltar(no.id);
      layout.reaquecer(1);
      acoes.aoMover?.();
      acoes.aoReenquadrar?.();
    },
    destruir() {
      while (descartar.length) descartar.pop()();
      if (palco) delete palco.dataset?.arrastando;
    },
  };
}
