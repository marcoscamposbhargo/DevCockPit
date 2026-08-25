"""Gravação do histórico de health (alimenta os gráficos de disponibilidade).

A tabela `health_snapshot` existia desde a Fase 4 e nada escrevia nela: o
poller media e jogava fora. O painel respondia "agora" e nunca "e antes?", que
é a pergunta que separa rotina de aviso.

Política de escrita — nem tudo, nem só mudança:

* **mudou de estado** grava sempre. É o instante que importa: o minuto em que
  o serviço caiu vale mais que as duas horas em que esteve de pé;
* **não mudou** grava a cada `min_interval_s`. Sem isso, um serviço estável por
  uma semana teria um ponto só, e o gráfico não teria como distinguir "de pé o
  tempo todo" de "ninguém verificou".

Gravar todo ciclo seria 2.880 linhas por serviço por dia para dizer a mesma
coisa 2.879 vezes.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import sessionmaker

from app.models.base import session_scope, utcnow
from app.models.project import HealthSnapshot
from app.repositories.health_snapshot_repository import HealthSnapshotRepository
from app.services.health_service import HealthResult

logger = logging.getLogger(__name__)


class HealthHistoryService:
    def __init__(self, session_factory: sessionmaker, min_interval_s: float = 300.0) -> None:
        self.session_factory = session_factory
        self.min_interval_s = min_interval_s
        #: Último estado gravado por (projeto, serviço). Em memória para não
        #: consultar o banco a cada ciclo; carregado do banco na primeira volta
        #: para que reiniciar o servidor não gere uma enxurrada de repetições.
        self._ultimo: dict[tuple[str, str], tuple[str, float]] | None = None

    def record(self, results: list[HealthResult]) -> int:
        """Grava o que merece ser gravado. Devolve quantas linhas escreveu."""
        if not results:
            return 0

        agora = utcnow()
        with session_scope(self.session_factory) as session:
            repo = HealthSnapshotRepository(session)
            ultimo = self._carregar(repo)

            novos: list[HealthSnapshot] = []
            for resultado in results:
                chave = (resultado.project_id, resultado.key)
                estado = str(resultado.state)
                anterior = ultimo.get(chave)

                if anterior is not None:
                    estado_anterior, quando = anterior
                    mudou = estado_anterior != estado
                    velho = (agora.timestamp() - quando) >= self.min_interval_s
                    if not mudou and not velho:
                        continue

                checked_at = resultado.checked_at or agora
                novos.append(
                    HealthSnapshot(
                        project_id=resultado.project_id,
                        service_key=resultado.key,
                        state=estado,
                        latency_ms=resultado.latency_ms,
                        detail=resultado.detail,
                        checked_at=checked_at,
                    )
                )
                ultimo[chave] = (estado, checked_at.timestamp())

            return repo.add_many(novos)

    def _carregar(self, repo: HealthSnapshotRepository) -> dict[tuple[str, str], tuple[str, float]]:
        if self._ultimo is None:
            self._ultimo = {
                chave: (estado, quando.timestamp())
                for chave, (estado, quando) in repo.last_per_service().items()
            }
        return self._ultimo
