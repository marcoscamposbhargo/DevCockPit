"""Jobs com processo real, usando `scripts/job_probe.py` (US-043).

É aqui que se prova o item mais importante do critério de saída da Fase 3a:
**nenhum processo órfão**. Um `compose up` interrompido que deixa filho vivo
continua segurando porta e volume, e o usuário não tem como saber.
"""

from __future__ import annotations

import asyncio
import os
import subprocess  # noqa: S404 - o teste precisa inspecionar processos reais
import sys
from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT
from app.jobs.job import JobStatus
from app.jobs.job_manager import JobManager
from app.runner.command_spec import CommandSpec

pytestmark = pytest.mark.integration

PROBE = PROJECT_ROOT / "scripts" / "job_probe.py"
IS_WINDOWS = os.name == "nt"


def probe_spec(tmp_path: Path, *args: str, timeout: float = 60.0) -> CommandSpec:
    return CommandSpec(
        argv=[sys.executable, str(PROBE), *args],
        cwd=tmp_path,
        timeout_s=timeout,
        label="test.probe",
    )


def count_probe_processes() -> int:
    """Quantos `job_probe.py` estão vivos agora.

    Conta por linha de comando, nunca por porta: matar processo por porta
    derruba o Docker Desktop nesta máquina.
    """
    if IS_WINDOWS:
        completed = subprocess.run(  # noqa: S603
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -like '*job_probe.py*' }).Count",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = completed.stdout.strip()
        return int(raw) if raw.isdigit() else 0

    completed = subprocess.run(  # noqa: S603
        ["pgrep", "-fc", "job_probe.py"], capture_output=True, text=True, timeout=30
    )
    raw = completed.stdout.strip()
    return int(raw) if raw.isdigit() else 0


@pytest.fixture
def manager() -> JobManager:
    return JobManager()


def test_probe_existe() -> None:
    assert PROBE.is_file(), "scripts/job_probe.py é pré-requisito da Fase 3a"


async def test_saida_incremental_com_processo_real(
    manager: JobManager, tmp_path: Path
) -> None:
    job = manager.submit(probe_spec(tmp_path, "--lines", "20", "--delay", "0.05"), key="p1")

    await asyncio.sleep(0.6)
    parcial = len(job.lines)

    final = await manager.wait(job.id, timeout=30)

    assert parcial > 0, "a saída deveria aparecer durante a execução"
    assert parcial < len(final.lines), "a saída deveria continuar crescendo"
    assert final.status == JobStatus.SUCCESS
    assert "linha 20/20" in final.output


async def test_codigo_de_saida_e_propagado(manager: JobManager, tmp_path: Path) -> None:
    job = await manager.wait(
        manager.submit(
            probe_spec(tmp_path, "--lines", "2", "--delay", "0", "--exit-code", "3"), key="p"
        ).id,
        timeout=30,
    )

    assert job.status == JobStatus.FAILED
    assert job.exit_code == 3


async def test_stderr_entra_na_saida_sem_marcacao(manager: JobManager, tmp_path: Path) -> None:
    """Progresso em stderr é normal em `docker compose` e `git`.

    Marcar essas linhas como erro faria o console parecer quebrado numa
    operação bem-sucedida.
    """
    job = await manager.wait(
        manager.submit(
            probe_spec(tmp_path, "--lines", "6", "--delay", "0", "--stderr-every", "2"), key="p"
        ).id,
        timeout=30,
    )

    assert "[stderr]" not in job.output
    # as 6 linhas aparecem, independente do canal
    assert sum(1 for line in job.output.splitlines() if line.startswith("linha ")) == 6


async def test_timeout_encerra_o_processo(manager: JobManager, tmp_path: Path) -> None:
    antes = count_probe_processes()

    job = await manager.wait(
        manager.submit(
            probe_spec(tmp_path, "--lines", "500", "--delay", "0.5", timeout=2), key="p"
        ).id,
        timeout=30,
    )

    assert job.status == JobStatus.TIMEOUT

    await asyncio.sleep(1.5)
    assert count_probe_processes() <= antes, "sobrou processo após o timeout"


async def test_cancelamento_encerra_em_menos_de_dois_segundos(
    manager: JobManager, tmp_path: Path
) -> None:
    job = manager.submit(probe_spec(tmp_path, "--lines", "500", "--delay", "0.5"), key="p")
    await asyncio.sleep(0.5)

    inicio = asyncio.get_running_loop().time()
    manager.cancel(job.id)
    await manager.wait(job.id, timeout=30)
    decorrido = asyncio.get_running_loop().time() - inicio

    assert job.status == JobStatus.CANCELLED
    assert decorrido < 2.0, f"cancelamento levou {decorrido:.2f}s"


@pytest.mark.slow
async def test_processo_que_ignora_termino_morre_mesmo_assim(
    manager: JobManager, tmp_path: Path
) -> None:
    """O caso difícil: `--ignore-term` recusa o sinal educado."""
    antes = count_probe_processes()

    job = manager.submit(
        probe_spec(tmp_path, "--lines", "500", "--delay", "0.5", "--ignore-term"), key="p"
    )
    await asyncio.sleep(1.0)
    manager.cancel(job.id)
    await manager.wait(job.id, timeout=30)

    await asyncio.sleep(2.0)

    assert job.status == JobStatus.CANCELLED
    assert count_probe_processes() <= antes, "o processo teimoso sobreviveu"


@pytest.mark.slow
async def test_filhos_morrem_junto_com_o_pai(manager: JobManager, tmp_path: Path) -> None:
    """Encerrar só o filho direto deixaria netos segurando recursos."""
    antes = count_probe_processes()

    job = manager.submit(
        probe_spec(tmp_path, "--lines", "500", "--delay", "0.5", "--spawn-children", "2"),
        key="p",
    )
    await asyncio.sleep(1.5)
    assert count_probe_processes() > antes, "os filhos deveriam estar vivos"

    manager.cancel(job.id)
    await manager.wait(job.id, timeout=30)
    await asyncio.sleep(2.5)

    assert count_probe_processes() <= antes, "sobrou filho órfão"


@pytest.mark.slow
async def test_vinte_execucoes_seguidas_nao_deixam_orfao(
    manager: JobManager, tmp_path: Path
) -> None:
    """Critério de saída da Fase 3a."""
    antes = count_probe_processes()

    for indice in range(20):
        job = manager.submit(
            probe_spec(tmp_path, "--lines", "3", "--delay", "0.01"), key=f"lote-{indice}"
        )
        await manager.wait(job.id, timeout=30)
        assert job.status == JobStatus.SUCCESS, f"execução {indice} falhou"

    await asyncio.sleep(1.0)
    assert count_probe_processes() <= antes, "sobrou processo após 20 execuções"


async def test_jobs_de_chaves_diferentes_rodam_de_fato_em_paralelo(
    manager: JobManager, tmp_path: Path
) -> None:
    inicio = asyncio.get_running_loop().time()

    a = manager.submit(probe_spec(tmp_path, "--lines", "10", "--delay", "0.1"), key="a")
    b = manager.submit(probe_spec(tmp_path, "--lines", "10", "--delay", "0.1"), key="b")
    await asyncio.gather(manager.wait(a.id, timeout=30), manager.wait(b.id, timeout=30))

    decorrido = asyncio.get_running_loop().time() - inicio

    assert a.status == JobStatus.SUCCESS
    assert b.status == JobStatus.SUCCESS
    # Em série seriam ~2 s; em paralelo, pouco mais de 1 s.
    assert decorrido < 2.0, f"pareceram rodar em série: {decorrido:.2f}s"


async def test_programa_inexistente_falha_sem_travar(
    manager: JobManager, tmp_path: Path
) -> None:
    spec = CommandSpec(
        argv=["programa-inexistente-devcockpit"],
        cwd=tmp_path,
        timeout_s=10,
        label="test.missing",
    )

    job = await manager.wait(manager.submit(spec, key="p").id, timeout=30)

    assert job.status == JobStatus.FAILED
    assert job.exit_code == 127
