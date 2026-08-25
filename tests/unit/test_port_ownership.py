"""De quem é a porta — e o que o painel pode afirmar a partir disso.

O defeito que estes testes prendem: a verificação de saúde abre um socket e
pergunta "tem alguém aí?", nunca "quem?". Com dois projetos declarando 8000,
o painel dizia "no ar" para o projeto parado, mostrando o container do outro.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.system.ports import FakePortScanner, ListeningPort
from app.core.cache import TTLCache
from app.services.container_ports_service import parse_ps_global
from app.services.dashboard_service import DashboardService
from app.services.port_discovery_service import PortDiscoveryService, ProjectRef

pytestmark = pytest.mark.unit


PS_GLOBAL = (
    '{"Names":"plataformadeingressos-web-1","Ports":"0.0.0.0:8000->8000/tcp, '
    '[::]:8000->8000/tcp","Labels":"com.docker.compose.project.working_dir='
    'C:\\\\Users\\\\User\\\\Projetos\\\\PLATAFORMA,com.docker.compose.service=web"}\n'
    '{"Names":"solto","Ports":"0.0.0.0:9999->9999/tcp","Labels":"algo=1"}\n'
)


def test_le_diretorio_do_projeto_no_rotulo_do_container() -> None:
    portas = parse_ps_global(PS_GLOBAL)

    assert len(portas) == 1, "container sem rótulo do Compose não diz de quem é"
    assert portas[0].port == 8000
    assert portas[0].working_dir.endswith("PLATAFORMA")


def test_caminho_com_virgula_nao_corta_o_diretorio() -> None:
    """Caminho do Windows pode ter vírgula, e os rótulos são separados por vírgula."""
    linha = (
        '{"Names":"x","Ports":"0.0.0.0:7000->7000/tcp","Labels":'
        '"com.docker.compose.project.working_dir=C:\\\\Users\\\\a,b\\\\proj,'
        'com.docker.compose.service=web"}'
    )

    portas = parse_ps_global(linha)

    assert portas[0].working_dir.endswith("a,b\\proj")


def test_linha_ilegivel_nao_derruba_o_resto() -> None:
    assert len(parse_ps_global("{quebrado\n" + PS_GLOBAL)) == 1


def observacao_para(container_dirs: dict[int, str], projetos: list[ProjectRef]):  # type: ignore[no-untyped-def]
    escutando = [
        ListeningPort(
            port=8000,
            pid=123,
            process_name="com.docker.backend.exe",
            cwd="C:/Program Files/Docker",
            cmdline="com.docker.backend.exe",
            addresses=frozenset({"0.0.0.0"}),
        )
    ]
    servico = PortDiscoveryService(
        scanner=FakePortScanner(escutando), cache=TTLCache(ttl_seconds=60)
    )
    return servico.observe(projetos, container_dirs=container_dirs)


def test_rotulo_do_container_e_prova_mesmo_com_dois_declarando_a_porta() -> None:
    """A regra antiga se calava aqui: dois projetos declarando 8000, sem dono."""
    dono = ProjectRef(
        id="plataforma", name="Plataforma", path="C:/proj/plataforma", declared_ports=(8000,)
    )
    outro = ProjectRef(
        id="contabil", name="Contábil", path="C:/proj/contabil", declared_ports=(8000,)
    )

    observacao = observacao_para({8000: "C:/proj/plataforma"}, [dono, outro])
    porta = observacao.by_port()[8000]

    assert porta.project_id == "plataforma"
    assert porta.matched_by == "container-label"
    assert porta.strong_evidence, "rótulo do Compose é fato, não dedução"


def test_sem_rotulo_a_atribuicao_continua_sendo_palpite() -> None:
    dono = ProjectRef(
        id="plataforma", name="Plataforma", path="C:/proj/plataforma", declared_ports=(8000,)
    )

    porta = observacao_para({}, [dono]).by_port()[8000]

    assert porta.matched_by == "container"
    assert not porta.strong_evidence


# --- o que o dashboard pode afirmar --------------------------------------


class DonoFalso:
    def __init__(self, project_id, project_name, strong, nome="python.exe"):  # type: ignore[no-untyped-def]
        self.project_id = project_id
        self.project_name = project_name
        self.strong_evidence = strong
        self.process_name = nome


def test_porta_de_outro_projeto_nao_e_prova(tmp_path: Path) -> None:
    from app.models.project import Project

    projeto = Project(id="contabil", name="Contábil", path=str(tmp_path))
    dono = DonoFalso("plataforma", "Plataforma", True)

    provado, pista = DashboardService._avaliar_dono(projeto, dono)

    assert provado is False
    assert "Plataforma" in pista


def test_sem_dono_conhecido_nao_e_prova(tmp_path: Path) -> None:
    from app.models.project import Project

    projeto = Project(id="contabil", name="Contábil", path=str(tmp_path))

    provado, pista = DashboardService._avaliar_dono(projeto, DonoFalso(None, None, False))

    assert provado is False
    assert "sem dono" in pista


def test_processo_do_proprio_projeto_e_prova(tmp_path: Path) -> None:
    from app.models.project import Project

    projeto = Project(id="contabil", name="Contábil", path=str(tmp_path))

    dono = DonoFalso("contabil", "Contábil", True)
    provado, pista = DashboardService._avaliar_dono(projeto, dono)

    assert provado is True
    assert pista is None


def test_sem_observacao_nenhuma_o_painel_nao_desconfia(tmp_path: Path) -> None:
    """Antes do primeiro ciclo do poller não há o que cruzar.

    Marcar tudo como suspeito no primeiro minuto seria pior que o defeito que
    esta regra conserta.
    """
    from app.models.project import Project

    projeto = Project(id="contabil", name="Contábil", path=str(tmp_path))

    assert DashboardService._avaliar_dono(projeto, None) == (True, None)
