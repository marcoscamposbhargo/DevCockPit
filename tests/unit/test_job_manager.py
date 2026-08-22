"""JobManager e Job: estados, saída incremental, exclusão mútua e limites.

Sem tocar em processo real: o runner é substituído por um fake. O
comportamento com processo de verdade está em
`tests/integration/test_jobs_real.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.errors import OperationInProgress
from app.jobs.job import Job, JobStatus
from app.jobs.job_manager import JobManager
from app.runner.command_spec import CommandResult, CommandSpec
from tests.support import FakeAsyncRunner

pytestmark = pytest.mark.unit


def spec(tmp_path: Path, label: str = "test.job", timeout: float = 30.0) -> CommandSpec:
    return CommandSpec(argv=["fake"], cwd=tmp_path, timeout_s=timeout, label=label)


# --- ciclo de vida -------------------------------------------------------


async def test_job_completa_com_sucesso(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner(lines=["a", "b"]))

    job = manager.submit(spec(tmp_path), key="k1")
    assert job.status == JobStatus.PENDING

    await manager.wait(job.id)

    assert job.status == JobStatus.SUCCESS
    assert job.exit_code == 0
    assert job.output.splitlines() == ["a", "b"]
    assert job.duration_ms is not None


async def test_exit_code_diferente_de_zero_vira_failed(tmp_path: Path) -> None:
    runner = FakeAsyncRunner(result=CommandResult(2, "", "erro: faltou algo\n", 8))
    manager = JobManager(runner=runner)

    job = await manager.wait((manager.submit(spec(tmp_path), key="k")).id)

    assert job.status == JobStatus.FAILED
    assert job.exit_code == 2
    assert "erro: faltou algo" in job.message


async def test_timeout_vira_status_timeout(tmp_path: Path) -> None:
    runner = FakeAsyncRunner(result=CommandResult(-1, "", "", 30, timed_out=True))
    manager = JobManager(runner=runner)

    job = await manager.wait((manager.submit(spec(tmp_path, timeout=1), key="k")).id)

    assert job.status == JobStatus.TIMEOUT
    assert "tempo limite" in job.message


async def test_saida_e_visivel_durante_a_execucao(tmp_path: Path) -> None:
    """O ponto do console de job: ver progresso, não esperar no escuro."""
    runner = FakeAsyncRunner(lines=[f"linha {i}" for i in range(10)], delay=0.02)
    manager = JobManager(runner=runner)

    job = manager.submit(spec(tmp_path), key="k")
    await asyncio.sleep(0.08)

    parcial = len(job.lines)
    assert 0 < parcial < 10, f"esperava saída parcial, veio {parcial}"

    await manager.wait(job.id)
    assert len(job.lines) == 10


# --- exclusão mútua (FR-057) ---------------------------------------------


async def test_segundo_job_na_mesma_chave_e_recusado(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner(hang=True))
    primeiro = manager.submit(spec(tmp_path), key="docker:proj-a")
    await asyncio.sleep(0)

    with pytest.raises(OperationInProgress):
        manager.submit(spec(tmp_path), key="docker:proj-a")

    manager.cancel(primeiro.id)
    await manager.wait(primeiro.id)


async def test_chaves_diferentes_rodam_em_paralelo(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner(lines=["x"], delay=0.05))

    a = manager.submit(spec(tmp_path), key="docker:proj-a")
    b = manager.submit(spec(tmp_path), key="docker:proj-b")

    await asyncio.gather(manager.wait(a.id), manager.wait(b.id))

    assert a.status == JobStatus.SUCCESS
    assert b.status == JobStatus.SUCCESS


async def test_chave_libera_apos_conclusao(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner())

    primeiro = manager.submit(spec(tmp_path), key="k")
    await manager.wait(primeiro.id)

    segundo = manager.submit(spec(tmp_path), key="k")
    await manager.wait(segundo.id)

    assert segundo.status == JobStatus.SUCCESS


# --- cancelamento --------------------------------------------------------


async def test_cancelamento_encerra_o_job(tmp_path: Path) -> None:
    runner = FakeAsyncRunner(hang=True)
    manager = JobManager(runner=runner)

    job = manager.submit(spec(tmp_path), key="k")
    await asyncio.sleep(0.02)
    manager.cancel(job.id)
    await manager.wait(job.id)

    assert job.status == JobStatus.CANCELLED
    assert runner.terminated is True


async def test_cancelar_job_ja_concluido_nao_muda_estado(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner())
    job = await manager.wait(manager.submit(spec(tmp_path), key="k").id)

    manager.cancel(job.id)

    assert job.status == JobStatus.SUCCESS


async def test_shutdown_cancela_tudo_que_esta_rodando(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner(hang=True))
    job = manager.submit(spec(tmp_path), key="k")
    await asyncio.sleep(0.02)

    await manager.shutdown(timeout=5)

    assert job.status.is_final


# --- limite de saída -----------------------------------------------------


def test_saida_e_truncada_pelo_comeco() -> None:
    """O interessante em log de comando longo quase sempre está no fim."""
    job = Job(id="j1", action="a", key="k")
    limite = 200

    for i in range(200):
        job.append(f"linha {i:04d}", limit=limite)

    assert job.output_truncated is True
    assert job.output_bytes <= limite * 1.5
    assert "linha 0199" in job.output
    assert "linha 0000" not in job.output
    # O marcador é apresentação e vive em `output`, não em `lines`: uma linha
    # sintética na lista desalinharia o índice absoluto que o console usa.
    assert "truncada" in job.output
    assert all("truncada" not in linha for linha in job.lines)


def test_revision_avanca_a_cada_linha() -> None:
    job = Job(id="j1", action="a", key="k")

    job.append("um", limit=10_000)
    job.append("dois", limit=10_000)

    assert job.revision == 2


# --- trabalho em processo (varredura) ------------------------------------


async def test_submit_callable_executa_e_conclui() -> None:
    manager = JobManager()

    async def work(job: Job) -> str:
        job.append("trabalhando", limit=10_000)
        return "feito"

    job = await manager.wait(
        manager.submit_callable(work, key="scan", action="discovery.scan").id
    )

    assert job.status == JobStatus.SUCCESS
    assert job.message == "feito"
    assert "trabalhando" in job.output


async def test_submit_callable_que_falha_nao_derruba_o_manager() -> None:
    manager = JobManager()

    async def work(_: Job) -> str:
        raise RuntimeError("quebrou")

    job = await manager.wait(manager.submit_callable(work, key="s", action="x").id)

    assert job.status == JobStatus.FAILED
    assert "quebrou" in job.message


# --- auditoria e retenção ------------------------------------------------


async def test_hook_de_auditoria_recebe_o_resultado(tmp_path: Path) -> None:
    registrados: list[tuple[str, str]] = []

    def hook(job, _result):  # type: ignore[no-untyped-def]
        registrados.append((job.action, job.status.value))

    manager = JobManager(runner=FakeAsyncRunner(), audit_hook=hook)
    await manager.wait(manager.submit(spec(tmp_path, label="docker.up"), key="k").id)

    assert registrados == [("docker.up", "SUCCESS")]


async def test_hook_que_falha_nao_derruba_o_job(tmp_path: Path) -> None:
    def hook(_job, _result):  # type: ignore[no-untyped-def]
        raise RuntimeError("auditoria quebrada")

    manager = JobManager(runner=FakeAsyncRunner(), audit_hook=hook)
    job = await manager.wait(manager.submit(spec(tmp_path), key="k").id)

    assert job.status == JobStatus.SUCCESS


async def test_job_antigo_e_descartado(tmp_path: Path) -> None:
    manager = JobManager(runner=FakeAsyncRunner(), retention_s=0.0)

    antigo = manager.submit(spec(tmp_path), key="k1")
    await manager.wait(antigo.id)

    manager.submit(spec(tmp_path), key="k2")

    assert manager.get(antigo.id) is None
