"""Gera o ícone do aplicativo a partir de código, não de um arquivo binário solto.

Um `.ico` versionado é uma caixa-preta: ninguém sabe como refazer quando a cor
do tema muda. Aqui a forma é o desenho do próprio painel — o arco do `gauge`
que já existe em `frontend/js/lib/charts.js` — nas mesmas cores dos tokens de
CSS. Trocar a identidade é trocar duas constantes e rodar de novo:

    .venv\\Scripts\\python.exe scripts\\make_icon.py

Saída: `frontend/assets/devcockpit.ico`, com todos os tamanhos que o Windows
pede (16 px na barra de tarefas, 256 px na visualização grande do Explorer).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "frontend" / "assets" / "devcockpit.ico"

#: Os mesmos valores de `frontend/css/tokens.css`.
FUNDO = (14, 17, 22)
TRILHO = (45, 51, 59)
ACENTO = (47, 129, 247)
ONLINE = (63, 185, 80)

#: Desenhamos grande e reduzimos: é o antisserrilhado do pobre, e o único que
#: funciona sem depender de fonte ou de biblioteca de vetor.
LADO = 1024
ESCALA = 4


def desenhar() -> Image.Image:
    imagem = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)

    # Quadrado arredondado do fundo, no mesmo raio proporcional que o painel usa
    # nos cartões.
    desenho.rounded_rectangle([0, 0, LADO - 1, LADO - 1], radius=LADO // 5, fill=FUNDO)

    # Arco de 0 a 100, aberto embaixo — o mesmo gesto do `gauge` da tela da
    # máquina. Meia-lua, e não anel fechado: o vazio embaixo é onde a agulha
    # nasce.
    margem = LADO * 0.22
    caixa = [margem, margem * 1.15, LADO - margem, LADO - margem * 0.85]
    grossura = int(LADO * 0.085)

    desenho.arc(caixa, start=180, end=360, fill=TRILHO, width=grossura)
    # Dois terços preenchidos: um painel em repouso, não em alarme.
    desenho.arc(caixa, start=180, end=300, fill=ACENTO, width=grossura)

    # Agulha apontando para onde o arco parou.
    centro = (LADO / 2, LADO - margem * 0.85 - (LADO - margem * 2) / 2)
    import math

    angulo = math.radians(300)
    raio = (caixa[2] - caixa[0]) / 2 * 0.72
    ponta = (centro[0] + raio * math.cos(angulo), centro[1] + raio * math.sin(angulo))
    desenho.line([centro, ponta], fill=(230, 237, 243), width=int(LADO * 0.035))
    pino = LADO * 0.045
    desenho.ellipse(
        [centro[0] - pino, centro[1] - pino, centro[0] + pino, centro[1] + pino],
        fill=(230, 237, 243),
    )

    # Ponto verde: o sinal de "no ar" que o painel usa em toda lista. É o que
    # diferencia este ícone de um velocímetro genérico.
    ponto = LADO * 0.055
    cx, cy = LADO * 0.76, LADO * 0.76
    desenho.ellipse([cx - ponto, cy - ponto, cx + ponto, cy + ponto], fill=ONLINE)

    return imagem.resize((LADO // ESCALA, LADO // ESCALA), Image.LANCZOS)


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    imagem = desenhar()
    imagem.save(
        DESTINO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    imagem.resize((256, 256), Image.LANCZOS).save(DESTINO.with_suffix(".png"))
    print(f"gerado: {DESTINO}")


if __name__ == "__main__":
    main()
