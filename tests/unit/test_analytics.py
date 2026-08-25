"""Análise histórica: agregação, disponibilidade, gravação e poda.

O que estes testes protegem não é o desenho do gráfico, é a **honestidade do
número**: uptime ponderado por tempo, cobertura declarada, buraco preservado e
nada afirmado a partir de amostra que não existe.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.models.base import utcnow
from app.models.project import ActivityLog, HealthSnapshot, Project
from app.services.analytics_service import AnalyticsService, percentil
from app.services.health_history_service import HealthHistoryService
from app.services.health_service import HealthResult, HealthState
from app.services.retention_service import RetentionService
from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.unit


@pytest.fixture
def projeto(session: Session) -> Project:
    project = Project(id="p1", name="App Web", path="C:/tmp/app-web")
    session.add(project)
    session.commit()
    return project


def acao(session: Session, *, action: str, status: str, minutos: int, duracao: int | None) -> None:
    session.add(
        ActivityLog(
            action=action,
            status=status,
            duration_ms=duracao,
            created_at=utcnow() - timedelta(minutes=minutos),
        )
    )


def amostra(session: Session, *, estado: str, minutos: int, latencia: int | None = 12) -> None:
    session.add(
        HealthSnapshot(
            project_id="p1",
            service_key="backend",
            state=estado,
            latency_ms=latencia,
            checked_at=utcnow() - timedelta(minutes=minutos),
        )
    )


def servico(session: Session, cache: TTLCache | None = None) -> AnalyticsService:
    return AnalyticsService(session, cache or TTLCache(ttl_seconds=0.0), max_gap_s=600.0)


# --- atividade ------------------------------------------------------------


def test_dias_sem_atividade_aparecem_zerados(session: Session) -> None:
    acao(session, action="git.status", status="SUCCESS", minutos=10, duracao=30)
    session.commit()

    dados = servico(session).build(days=3)

    assert len(dados.activity_daily) == 4, "três dias mais o dia corrente"
    # A ação pode cair no dia anterior se a suíte rodar logo depois da
    # meia-noite: o que se afirma é que ela aparece **uma vez** e que os
    # demais dias estão presentes zerados, não em qual deles caiu.
    com_atividade = [dia for dia in dados.activity_daily if dia.total]
    assert len(com_atividade) == 1
    assert com_atividade[0].success == 1


def test_taxa_de_falha_conta_recusa_e_tempo_esgotado(session: Session) -> None:
    acao(session, action="a", status="SUCCESS", minutos=1, duracao=10)
    acao(session, action="a", status="FAILED", minutos=2, duracao=10)
    acao(session, action="a", status="TIMEOUT", minutos=3, duracao=10)
    acao(session, action="a", status="DENIED", minutos=4, duracao=10)
    session.commit()

    dados = servico(session).build(days=1)

    assert dados.failure_rate == 75.0
    resumo = dados.actions[0]
    assert resumo.total == 4
    assert resumo.failures == 3


def test_percentil_devolve_valor_observado() -> None:
    assert percentil([10, 20, 30, 40], 0.5) == 30
    assert percentil([], 0.5) is None
    assert percentil([7], 0.95) == 7


def test_acao_sem_duracao_nao_vira_zero(session: Session) -> None:
    """`duration_ms` nulo é "não medido", não "instantâneo"."""
    acao(session, action="open.vscode", status="SUCCESS", minutos=1, duracao=None)
    session.commit()

    resumo = servico(session).build(days=1).actions[0]

    assert resumo.p50_ms is None
    assert resumo.p95_ms is None


# --- disponibilidade ------------------------------------------------------


def test_uptime_ponderado_por_tempo(session: Session, projeto: Project) -> None:
    """Duas amostras ONLINE seguidas de uma OFFLINE não são 66%: são tempo."""
    amostra(session, estado="ONLINE", minutos=30)
    amostra(session, estado="ONLINE", minutos=25)
    amostra(session, estado="OFFLINE", minutos=20)
    session.commit()

    item = servico(session).build(days=1).uptime[0]

    # ONLINE cobre 5 min + 5 min; OFFLINE cobre 10 min (teto do intervalo).
    assert item.uptime_pct == 50.0
    assert item.samples == 3
    assert item.last_state == "OFFLINE"


def test_buraco_longo_nao_vira_disponibilidade(session: Session, projeto: Project) -> None:
    """Amostra isolada cobre o teto, não o dia inteiro em que ninguém olhou."""
    amostra(session, estado="ONLINE", minutos=60 * 20)
    session.commit()

    item = servico(session).build(days=1).uptime[0]

    assert item.uptime_pct == 100.0, "o que se mediu estava no ar"
    assert item.coverage_pct < 2.0, "e quase nada do período foi medido"


def test_serie_de_latencia_preserva_o_vazio(session: Session, projeto: Project) -> None:
    amostra(session, estado="ONLINE", minutos=5, latencia=40)
    session.commit()

    serie = servico(session).build(days=1).uptime[0].latency_series

    assert len(serie) == 24
    assert serie[-1] == 40.0
    assert all(ponto is None for ponto in serie[:-1]), "sem amostra é None, não zero"


def test_latencia_de_queda_nao_entra_na_serie(session: Session, projeto: Project) -> None:
    """Verificação que estourou o tempo mede o timeout, não o serviço."""
    amostra(session, estado="ONLINE", minutos=6, latencia=20)
    amostra(session, estado="OFFLINE", minutos=5, latencia=3000)
    session.commit()

    item = servico(session).build(days=1).uptime[0]

    assert item.p95_latency_ms == 20
    assert max(p for p in item.latency_series if p is not None) == 20.0


def test_servico_sem_amostra_nao_aparece(session: Session, projeto: Project) -> None:
    assert servico(session).build(days=1).uptime == []


# --- gravação do histórico ------------------------------------------------


def resultado(estado: HealthState, latencia: int = 10) -> HealthResult:
    return HealthResult(
        project_id="p1",
        key="backend",
        state=estado,
        latency_ms=latencia,
        checked_at=utcnow(),
    )


def test_repeticao_nao_grava_de_novo(session_factory, session: Session, projeto: Project) -> None:
    history = HealthHistoryService(session_factory, min_interval_s=300.0)

    assert history.record([resultado(HealthState.ONLINE)]) == 1
    assert history.record([resultado(HealthState.ONLINE)]) == 0, "mesmo estado, cedo demais"

    assert session.query(HealthSnapshot).count() == 1


def test_mudanca_de_estado_grava_sempre(
    session_factory, session: Session, projeto: Project
) -> None:
    history = HealthHistoryService(session_factory, min_interval_s=3600.0)

    history.record([resultado(HealthState.ONLINE)])
    gravou = history.record([resultado(HealthState.OFFLINE)])

    assert gravou == 1, "queda é o instante que mais importa"
    assert session.query(HealthSnapshot).count() == 2


def test_repeticao_volta_a_gravar_depois_do_intervalo(
    session_factory, session: Session, projeto: Project
) -> None:
    history = HealthHistoryService(session_factory, min_interval_s=0.0)

    history.record([resultado(HealthState.ONLINE)])
    history.record([resultado(HealthState.ONLINE)])

    assert session.query(HealthSnapshot).count() == 2


def test_estado_anterior_vem_do_banco_apos_reinicio(
    session_factory, session: Session, projeto: Project
) -> None:
    """Reiniciar o servidor não pode gerar uma enxurrada de repetições."""
    HealthHistoryService(session_factory, min_interval_s=300.0).record(
        [resultado(HealthState.ONLINE)]
    )

    outro = HealthHistoryService(session_factory, min_interval_s=300.0)
    assert outro.record([resultado(HealthState.ONLINE)]) == 0


# --- poda -----------------------------------------------------------------


def test_poda_respeita_a_retencao_de_cada_tabela(
    session_factory, session: Session, projeto: Project
) -> None:
    session.add(
        ActivityLog(action="antiga", status="SUCCESS", created_at=utcnow() - timedelta(days=120))
    )
    session.add(
        ActivityLog(action="recente", status="SUCCESS", created_at=utcnow() - timedelta(days=2))
    )
    amostra(session, estado="ONLINE", minutos=60 * 24 * 40)
    amostra(session, estado="ONLINE", minutos=30)
    session.commit()

    apagados = RetentionService(
        session_factory, activity_days=90, health_days=14
    ).prune()

    assert apagados == {"activity": 1, "health": 1}
    assert session.query(ActivityLog).count() == 1
    assert session.query(HealthSnapshot).count() == 1


def test_poda_so_roda_uma_vez_por_intervalo(session_factory) -> None:
    retention = RetentionService(session_factory, interval_s=3600.0)

    assert retention.prune_if_due() is not None
    assert retention.prune_if_due() is None


# --- contrato HTTP --------------------------------------------------------


def test_rota_devolve_analise(client: TestClient, workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace / "api"
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    client.post("/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS)

    corpo = client.get("/api/analytics?days=7").json()

    assert corpo["days"] == 7
    assert len(corpo["activity_daily"]) == 8
    assert corpo["truncated"] is False
    assert any(tech["name"] == "fastapi" for tech in corpo["technologies"])


def test_rota_recusa_periodo_fora_da_faixa(client: TestClient) -> None:
    assert client.get("/api/analytics?days=0").status_code == 422
    assert client.get("/api/analytics?days=400").status_code == 422


# --- poller ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_poller_grava_o_que_verificou(session_factory, session: Session, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Sem isto, a tabela volta a ser o que era: schema sem escrita."""
    import socket

    from app.core.cache import TTLCache as Cache
    from app.models.project import ProjectService
    from app.services.health_poller import HealthPoller
    from app.services.health_service import HealthService

    with socket.socket() as temporario:
        temporario.bind(("127.0.0.1", 0))
        fechada = temporario.getsockname()[1]

    outra = session_factory()
    try:
        projeto = Project(id="p9", name="Fixado", path=str(tmp_path / "p9"), is_pinned=True)
        projeto.services.append(ProjectService(key="db", label="DB", port=fechada))
        outra.add(projeto)
        outra.commit()
    finally:
        outra.close()

    poller = HealthPoller(
        session_factory,
        HealthService(cache=Cache(ttl_seconds=300), timeout_s=1.0),
        interval_s=999,
        history=HealthHistoryService(session_factory, min_interval_s=300.0),
        retention=RetentionService(session_factory),
    )

    assert await poller.run_once() == 1

    gravado = session.query(HealthSnapshot).one()
    assert gravado.project_id == "p9"
    assert gravado.state == "OFFLINE"


# --- timeout de job em processo -------------------------------------------


@pytest.mark.asyncio
async def test_job_em_processo_estoura_e_libera_a_chave() -> None:
    """`timeout_scan` deixou de ser configuração decorativa."""
    import asyncio

    from app.jobs.job_manager import JobManager

    manager = JobManager()

    async def eterno(job) -> str:  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)
        return "nunca"

    job = manager.submit_callable(eterno, key="k", action="discovery.scan", timeout_s=0.05)
    await manager.wait(job.id, timeout=2.0)

    assert job.status.value == "TIMEOUT"
    assert manager.active_for_key("k") is None or manager.active_for_key("k").status.is_final
