"""De quem é a porta publicada por container.

A descoberta de porta identifica o dono de um processo pelo diretório de
trabalho dele. Com container isso nunca funciona: o `cwd` aponta para a
instalação do Docker, não para o projeto. A regra que sobrava era uma
heurística — *se um único projeto declara este número, é dele* — e ela erra
justamente onde dói: dois projetos declarando 8000, que é o padrão de meio
mundo. Foi assim que o Dashboard-contabil apareceu "no ar" mostrando o
container da PLATAFORMA DE INGRESSOS.

O Compose grava o diretório do projeto em cada container
(`com.docker.compose.project.working_dir`). Perguntar ao Docker troca palpite
por fato, e custa uma chamada a cada ciclo do poller.

Falhar aqui nunca é erro de tela: sem Docker, com o daemon parado ou com uma
saída em formato inesperado, o resultado é um mapa vazio — e a descoberta volta
a se virar com o que tinha antes.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.adapters.docker.adapter import DockerAdapter

logger = logging.getLogger(__name__)

#: `0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp` — só interessa o número do
#: host, e ele aparece depois do último `:` antes da seta.
_PORTA_PUBLICADA = re.compile(r":(\d{1,5})->")

_ROTULO_DIRETORIO = "com.docker.compose.project.working_dir="


@dataclass(frozen=True)
class ContainerPort:
    port: int
    #: Diretório do projeto, como o Compose gravou no rótulo.
    working_dir: str
    container: str


def parse_ps_global(saida: str) -> list[ContainerPort]:
    """Lê a saída de `docker ps --format '{{json .}}'` — um JSON por linha."""
    resultado: list[ContainerPort] = []

    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            entrada = json.loads(linha)
        except json.JSONDecodeError:
            # Uma linha ilegível não invalida as outras: o mapa parcial ainda
            # é melhor que nenhum.
            continue
        if not isinstance(entrada, dict):
            continue

        diretorio = _diretorio_do_rotulo(str(entrada.get("Labels") or ""))
        if not diretorio:
            # Container fora do Compose (`docker run` na mão) não diz de quem é.
            continue

        nome = str(entrada.get("Names") or "")
        # A mesma porta aparece duas vezes quando o container publica em IPv4 e
        # IPv6 (`0.0.0.0:8000->8000, [::]:8000->8000`). É a mesma publicação.
        vistas: set[int] = set()
        for numero in _PORTA_PUBLICADA.findall(str(entrada.get("Ports") or "")):
            porta = int(numero)
            if 0 < porta < 65536 and porta not in vistas:
                vistas.add(porta)
                resultado.append(
                    ContainerPort(port=porta, working_dir=diretorio, container=nome)
                )

    return resultado


def _diretorio_do_rotulo(rotulos: str) -> str | None:
    """Extrai o `working_dir` da string de rótulos, que vem separada por vírgula.

    O valor é um caminho do Windows e **pode conter vírgula**. Por isso a busca
    é pelo prefixo, e o corte é no rótulo seguinte, não em toda vírgula.
    """
    inicio = rotulos.find(_ROTULO_DIRETORIO)
    if inicio < 0:
        return None

    resto = rotulos[inicio + len(_ROTULO_DIRETORIO) :]
    # O rótulo seguinte começa com `,com.docker.` ou `,desktop.docker.`.
    corte = re.search(r",(?:com|desktop|org)\.[a-z]", resto)
    valor = resto[: corte.start()] if corte else resto
    return valor.strip() or None


class ContainerPortsService:
    """Mapa `porta publicada -> diretório do projeto`, com cache curto."""

    def __init__(
        self,
        adapter: DockerAdapter,
        runner,  # type: ignore[no-untyped-def]
        cwd: Path,
        ttl_s: float = 20.0,
    ) -> None:
        self.adapter = adapter
        self.runner = runner
        self.cwd = cwd
        #: Cache próprio, e não o `TTLCache` da aplicação: aquele existe para o
        #: caminho da requisição, com TTL de segundos. Aqui quem chama é o
        #: poller, e chamar o Docker a cada volta de 30 s custa mais do que
        #: guardar o mapa por vinte.
        self.ttl_s = ttl_s
        self._mapa: dict[int, str] = {}
        self._lido_em: float | None = None

    def read(self) -> dict[int, str]:
        agora = time.monotonic()
        if self._lido_em is not None and (agora - self._lido_em) < self.ttl_s:
            return self._mapa

        mapa: dict[int, str] = {}
        try:
            resultado = self.runner.run(self.adapter.ps_global_spec(self.cwd))
            if resultado.exit_code == 0:
                for item in parse_ps_global(resultado.stdout):
                    mapa[item.port] = item.working_dir
        except Exception:  # noqa: BLE001 - sem Docker o painel segue funcionando
            logger.debug("não foi possível listar containers", exc_info=True)

        self._mapa = mapa
        self._lido_em = agora
        return mapa
