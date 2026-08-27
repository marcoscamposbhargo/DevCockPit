"""Onde procurar quando a raiz do projeto não tem marcador nenhum.

Um repositório com `backend/` e `frontend/` não declara nada na raiz: nem
`package.json`, nem `pyproject.toml`, nem Compose. O painel se declarava sem
stack e sem ambiente — quando bastava olhar uma pasta adiante.

A lista mora aqui, e não em quem a usa, porque duas partes precisam concordar
sobre o que é subpasta de projeto: a **detecção**, que descobre a stack, e o
**planejador**, que monta o comando de subir. Discordar produziria o pior
resultado possível — reconhecer o Next do `frontend/` e não saber subi-lo.

Um nível só. Dois já seria varredura, e varredura tem tela própria.
"""

from __future__ import annotations

#: Ordem pensada para **subir**: backend antes de frontend, porque o front quase
#: sempre depende dele, e subir o front contra uma API morta produz uma tela que
#: carrega e não funciona — pior que não subir.
#:
#: `infra` fecha a lista porque não é subprojeto que se roda: é onde mora o
#: Compose de quem separa infraestrutura do código. Ele nunca deve ser escolhido
#: como aplicação, e por isso vem depois de tudo.
SUBPROJETOS: tuple[str, ...] = (
    "backend",
    "api",
    "server",
    "src/backend",
    "frontend",
    "web",
    "client",
    "app",
    "infra",
)

#: O que o planejador considera. `infra` fica de fora: rodar "a pasta infra" não
#: significa nada, e o Compose sobe pela aba Docker, não pelo botão de ligar.
SUBPROJETOS_EXECUTAVEIS: tuple[str, ...] = SUBPROJETOS[:-1]
