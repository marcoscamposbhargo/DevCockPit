"""Health check, poller, OSAdapter e ações de sistema."""

from __future__ import annotations

import asyncio
import socket
from datetime import timedelta
from pathlib import Path

import pytest

from app.adapters.system.adapter import (
    LinuxOSAdapter,
    MacOSAdapter,
    WindowsOSAdapter,
    build_os_adapter,
)
from app.core.cache import TTLCache
from app.core.errors import ToolNotFound
from app.models.base import utcnow
from app.services.health_service import (
    HealthService,
    HealthState,
    ServiceTarget,
    should_poll,
)

pytestmark = pytest.mark.unit


def target(**kwargs) -> ServiceTarget:  # type: ignore[no-untyped-def]
    base = {
        "project_id": "p1",
        "key": "backend",
        "label": "Backend",
        "host": "127.0.0.1",
        "port": None,
        "url": None,
        "health_url": None,
        "health_kind": "TCP",
    }
    return ServiceTarget(**{**base, **kwargs})


@pytest.fixture
def health() -> HealthService:
    return HealthService(cache=TTLCache(ttl_seconds=300), timeout_s=1.0, stale_after_s=90)


@pytest.fixture
def porta_aberta():  # type: ignore[no-untyped-def]
    """Socket real escutando numa porta livre — mais honesto que mock de TCP."""
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    yield servidor.getsockname()[1]
    servidor.close()


def porta_livre() -> int:
    with socket.socket() as temporario:
        temporario.bind(("127.0.0.1", 0))
        return temporario.getsockname()[1]


# --- health check TCP -----------------------------------------------------


async def test_tcp_com_porta_aberta_fica_online(health: HealthService, porta_aberta: int) -> None:
    resultado = await health.check(target(port=porta_aberta))

    assert resultado.state == HealthState.ONLINE
    assert resultado.latency_ms is not None


async def test_tcp_com_porta_fechada_fica_offline(health: HealthService) -> None:
    resultado = await health.check(target(port=porta_livre()))

    assert resultado.state == HealthState.OFFLINE
    # O detalhe varia por plataforma e é isso mesmo: no Windows a tentativa
    # contra porta fechada costuma pendurar até o timeout em vez de ser
    # recusada na hora. O estado é o contrato; o texto explica qual dos dois
    # caminhos aconteceu.
    assert any(termo in resultado.detail.lower() for termo in ("fechada", "sem resposta"))


async def test_sem_porta_nem_url_fica_unknown(health: HealthService) -> None:
    resultado = await health.check(target())

    assert resultado.state == HealthState.UNKNOWN


async def test_health_kind_none_nao_e_verificado(health: HealthService) -> None:
    """Atalho como 'API Docs' não é serviço monitorado."""
    resultado = await health.check(target(health_kind="NONE", port=1234))

    assert resultado.state == HealthState.UNKNOWN
    assert "não monitorado" in resultado.detail


async def test_verificacoes_rodam_concorrentes(health: HealthService) -> None:
    """Três portas fechadas em série levariam ~3 s; concorrentes, ~1 s."""
    alvos = [target(key=f"s{i}", port=porta_livre()) for i in range(3)]

    inicio = asyncio.get_running_loop().time()
    resultados = await health.check_many(alvos)
    decorrido = asyncio.get_running_loop().time() - inicio

    assert len(resultados) == 3
    assert decorrido < 2.0, f"pareceu serial: {decorrido:.2f}s"


async def test_concorrencia_tem_teto(health: HealthService) -> None:
    """O lote respeita `max_concurrency`, e por isso o timeout mede o serviço.

    Sem teto, um ciclo com muitos projetos disparava dezenas de conexões de uma
    vez: o event loop congestionava e o `wait_for` de 2 s estourava em porta que
    responde em 0 ms. O histórico do painel guardou a prova do defeito —
    latências de 3 a 6 segundos num teto de 2, impossíveis a menos que o tempo
    tenha sido gasto na fila. Na tela, isso era serviço no ar aparecendo
    desligado de forma intermitente.
    """
    health.max_concurrency = 4
    em_voo = 0
    pico = 0
    original = health.check

    async def espiar(alvo):  # type: ignore[no-untyped-def]
        nonlocal em_voo, pico
        em_voo += 1
        pico = max(pico, em_voo)
        try:
            await asyncio.sleep(0.01)
            return await original(alvo)
        finally:
            em_voo -= 1

    health.check = espiar  # type: ignore[method-assign]
    alvos = [target(key=f"s{i}", port=porta_livre()) for i in range(20)]

    resultados = await health.check_many(alvos)

    assert len(resultados) == 20
    assert pico <= 4, f"{pico} verificações simultâneas, teto era 4"


def test_teto_minimo_e_um() -> None:
    """Valor inválido não desliga o teto — vira 1, que é serial mas correto."""
    servico = HealthService(cache=TTLCache(ttl_seconds=300), max_concurrency=0)

    assert servico.max_concurrency == 1


# --- cache e STALE --------------------------------------------------------


def test_servico_nunca_verificado_e_unknown(health: HealthService) -> None:
    resultado = health.last_known("p1", "backend")

    assert resultado.state == HealthState.UNKNOWN
    assert "Ainda não verificado" in resultado.detail


async def test_last_known_devolve_do_cache(health: HealthService, porta_aberta: int) -> None:
    await health.check(target(port=porta_aberta))

    assert health.last_known("p1", "backend").state == HealthState.ONLINE


async def test_dado_velho_vira_stale(porta_aberta: int) -> None:
    """Nunca apresentar dado antigo como tempo real (decisão D-18)."""
    health = HealthService(cache=TTLCache(ttl_seconds=3600), timeout_s=1.0, stale_after_s=60)
    resultado = await health.check(target(port=porta_aberta))

    # Envelhece o registro sem esperar de verdade.
    resultado.checked_at = utcnow() - timedelta(seconds=120)

    posterior = health.last_known("p1", "backend")
    assert posterior.state == HealthState.STALE
    assert "Última verificação" in posterior.detail


async def test_invalidate_limpa_o_projeto(health: HealthService, porta_aberta: int) -> None:
    await health.check(target(port=porta_aberta))

    health.invalidate("p1")

    assert health.last_known("p1", "backend").state == HealthState.UNKNOWN


# --- política do poller (Q-02) -------------------------------------------


class ProjetoFalso:
    def __init__(self, is_pinned: bool = False, dias_atras: int | None = None) -> None:
        self.is_pinned = is_pinned
        self.last_accessed_at = (
            None if dias_atras is None else utcnow() - timedelta(days=dias_atras)
        )


def test_projeto_fixado_sempre_e_verificado() -> None:
    assert should_poll(ProjetoFalso(is_pinned=True), recent_days=7) is True


def test_projeto_acessado_recentemente_e_verificado() -> None:
    assert should_poll(ProjetoFalso(dias_atras=2), recent_days=7) is True


def test_projeto_antigo_nao_e_verificado() -> None:
    """36 projetos a cada 30 s seria caro e inútil: a maioria está parada."""
    assert should_poll(ProjetoFalso(dias_atras=30), recent_days=7) is False


def test_projeto_nunca_acessado_nao_e_verificado() -> None:
    assert should_poll(ProjetoFalso(), recent_days=7) is False


# --- OSAdapter: argv por plataforma --------------------------------------


def test_windows_terminal_quando_disponivel(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    adapter = WindowsOSAdapter()
    monkeypatch.setattr(adapter, "tool_available", lambda tool: tool == "wt.exe")

    spec = adapter.open_terminal(tmp_path)

    assert spec.argv[0] == "wt.exe"
    assert "-d" in spec.argv
    assert str(tmp_path) in spec.argv


def test_windows_cai_para_powershell_sem_wt(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`wt.exe` não existe em instalações antigas do Windows 10."""
    adapter = WindowsOSAdapter()
    monkeypatch.setattr(adapter, "tool_available", lambda _tool: False)

    spec = adapter.open_terminal(tmp_path)

    assert spec.argv[0] == "powershell.exe"
    assert "-NoExit" in spec.argv
    assert str(tmp_path) in spec.argv[-1]


def test_windows_abre_pasta_com_explorer(tmp_path: Path) -> None:
    spec = WindowsOSAdapter().open_folder(tmp_path)

    assert spec.argv == ["explorer.exe", str(tmp_path)]


def test_windows_sem_code_no_path_da_erro_util(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.adapters.system.adapter.shutil.which", lambda _name: None)

    with pytest.raises(ToolNotFound, match="Install code command"):
        WindowsOSAdapter().open_in_editor(tmp_path)


def test_editor_vazio_nao_leva_caminho_nenhum(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """O atalho de começar o dia abre o editor sem pasta.

    O argv precisa ser só o binário: qualquer caminho sobrando aqui abriria uma
    pasta que ninguém escolheu — e a casa do usuário é a última que se quer
    abrir num editor por engano.
    """
    monkeypatch.setattr("app.adapters.system.adapter.shutil.which", lambda name: f"C:/bin/{name}")

    spec = WindowsOSAdapter().open_editor_blank()

    assert spec.argv == ["C:/bin/code"]
    assert spec.label == "system.vscode_blank"
    assert spec.detached is True


def test_editor_vazio_reaproveita_o_erro_de_code_ausente(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Mesma mensagem do caminho com projeto, porque é o mesmo código."""
    monkeypatch.setattr("app.adapters.system.adapter.shutil.which", lambda _name: None)

    with pytest.raises(ToolNotFound, match="Install code command"):
        WindowsOSAdapter().open_editor_blank()


def test_editor_vazio_e_auditado_sem_projeto(tmp_path: Path) -> None:
    """A ação global registra na auditoria com `project_id` nulo.

    Atribuí-la a um projeto qualquer — o último aberto, por exemplo — seria
    inventar autoria num log que existe para não deixar dúvida sobre o que
    aconteceu.
    """
    from app.adapters.system.adapter import BaseOSAdapter
    from app.runner.fake import FakeCommandRunner
    from app.services.system_action_service import SystemActionService

    registros: list[dict] = []

    class AdapterFalso(BaseOSAdapter):
        def open_in_editor(self, path: Path):  # type: ignore[no-untyped-def]
            return self._spec(["code", str(path)], path, "system.vscode")

    class AtividadeEspia:
        def record(self, **kwargs):  # type: ignore[no-untyped-def]
            registros.append(kwargs)

    runner = FakeCommandRunner()
    servico = SystemActionService(AdapterFalso(), runner, AtividadeEspia())  # type: ignore[arg-type]

    servico.open_editor_blank()

    assert runner.labels == ["system.vscode_blank"]
    assert registros[0]["project_id"] is None
    assert registros[0]["argv"] == ["code"]


def test_macos_usa_open(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    adapter = MacOSAdapter()
    monkeypatch.setattr(adapter, "tool_available", lambda _tool: True)

    assert adapter.open_folder(tmp_path).argv == ["open", str(tmp_path)]
    assert adapter.open_terminal(tmp_path).argv[:3] == ["open", "-a", "Terminal"]


def test_linux_escolhe_o_primeiro_terminal_disponivel(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    adapter = LinuxOSAdapter()
    monkeypatch.setattr(adapter, "tool_available", lambda tool: tool == "konsole")

    spec = adapter.open_terminal(tmp_path)

    assert spec.argv == ["konsole", "--workdir", str(tmp_path)]


def test_linux_sem_terminal_algum_da_erro_listando_os_procurados(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    adapter = LinuxOSAdapter()
    monkeypatch.setattr(adapter, "tool_available", lambda _tool: False)

    with pytest.raises(ToolNotFound, match="gnome-terminal"):
        adapter.open_terminal(tmp_path)


@pytest.mark.parametrize(
    ("plataforma", "esperado"),
    [("nt", "windows"), ("darwin", "macos"), ("posix", "linux")],
)
def test_fabrica_escolhe_a_implementacao(plataforma: str, esperado: str) -> None:
    assert build_os_adapter(platform=plataforma).name == esperado


def test_todo_spec_tem_timeout(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Nenhuma ação de SO pode ficar pendurada."""
    adapter = WindowsOSAdapter(timeout_s=7)
    monkeypatch.setattr(adapter, "tool_available", lambda _tool: True)

    for spec in (adapter.open_folder(tmp_path), adapter.open_terminal(tmp_path)):
        assert spec.timeout_s == 7


# --- poller ---------------------------------------------------------------


async def test_poller_verifica_apenas_projetos_elegiveis(
    session_factory, workspace: Path
) -> None:
    """Cobre a política de Q-02 ponta a ponta, contra o banco."""
    from app.models.project import Project, ProjectService
    from app.services.health_poller import HealthPoller

    fechada = porta_livre()
    session = session_factory()
    try:
        fixado = Project(id="fixado", name="Fixado", path=str(workspace / "a"), is_pinned=True)
        fixado.services.append(ProjectService(key="db", label="DB", port=fechada))

        antigo = Project(id="antigo", name="Antigo", path=str(workspace / "b"))
        antigo.last_accessed_at = utcnow() - timedelta(days=90)
        antigo.services.append(ProjectService(key="db", label="DB", port=fechada))

        session.add_all([fixado, antigo])
        session.commit()
    finally:
        session.close()

    health = HealthService(cache=TTLCache(ttl_seconds=300), timeout_s=1.0)
    poller = HealthPoller(session_factory, health, interval_s=999, recent_days=7)

    verificados = await poller.run_once()

    assert verificados == 1
    assert health.last_known("fixado", "db").state == HealthState.OFFLINE
    assert health.last_known("antigo", "db").state == HealthState.UNKNOWN


async def test_poller_nao_derruba_a_aplicacao_ao_falhar(session_factory) -> None:
    from app.services.health_poller import HealthPoller

    health = HealthService(cache=TTLCache(ttl_seconds=300), timeout_s=1.0)
    poller = HealthPoller(session_factory, health, interval_s=0.05)

    def explode() -> list:
        raise RuntimeError("banco caiu")

    poller._collect = explode  # type: ignore[method-assign]

    poller.start()
    await asyncio.sleep(0.2)
    await poller.stop()
    # Chegar aqui já é o teste: a exceção foi contida no ciclo.


# --- foco da janela do editor (D-46) ---


def test_windows_pede_foco_da_janela_do_projeto(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`code` devolve 0 reaproveitando janela escondida; o foco é o que falta."""
    pedidos: list[str] = []
    monkeypatch.setattr(
        "app.adapters.system.focus.focus_editor_window",
        lambda nome: pedidos.append(nome),
    )

    WindowsOSAdapter().focus_editor_window(tmp_path)

    assert pedidos == [tmp_path.name]


def test_adapters_nao_windows_nao_tentam_focar(tmp_path: Path) -> None:
    """No macOS e no Linux abrir já traz a janela; forçar foco seria intrusivo."""
    assert MacOSAdapter().focus_editor_window(tmp_path) is None
    assert LinuxOSAdapter().focus_editor_window(tmp_path) is None


def test_busca_de_janela_casa_pelo_nome_da_pasta(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Com várias janelas do editor abertas, focar a errada é pior que não focar."""
    from app.adapters.system import focus

    monkeypatch.setattr(
        focus,
        "_visible_window_titles",
        lambda _user32: [
            (10, "Google Chrome"),
            (20, "main.py - OUTRO-PROJETO - Visual Studio Code"),
            (30, "bom dia! - DEVCOCKPIT - Visual Studio Code"),
        ],
    )

    assert focus._find_editor_window(None, "DEVCOCKPIT") == 30
    assert focus._find_editor_window(None, "OUTRO-PROJETO") == 20
    assert focus._find_editor_window(None, "INEXISTENTE") is None


def test_falha_ao_focar_nao_derruba_a_abertura(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A ação já deu certo: o foco é cortesia e não pode virar erro."""
    from app.adapters.system import focus

    def _explode(_nome: str) -> bool:
        raise OSError("user32 indisponível")

    monkeypatch.setattr(focus, "_focus_now", _explode)

    focus._rodar_protegido("QUALQUER")  # não levanta


def test_abrir_no_editor_pede_foco_depois_de_executar(tmp_path: Path) -> None:
    """A ordem importa: só faz sentido focar a janela depois que `code` rodou."""
    from app.adapters.system.adapter import BaseOSAdapter
    from app.models.project import Project
    from app.runner.fake import FakeCommandRunner
    from app.services.system_action_service import SystemActionService

    eventos: list[str] = []

    class AdapterEspiao(BaseOSAdapter):
        def open_in_editor(self, path: Path):  # type: ignore[no-untyped-def]
            eventos.append("montou-comando")
            return self._spec(["code", str(path)], path, "system.vscode")

        def focus_editor_window(self, path: Path) -> None:
            eventos.append(f"focou:{path.name}")

    class AtividadeMuda:
        def record(self, **_kwargs):  # type: ignore[no-untyped-def]
            eventos.append("registrou")

    runner = FakeCommandRunner()
    servico = SystemActionService(AdapterEspiao(), runner, AtividadeMuda())  # type: ignore[arg-type]
    projeto = Project(id="p", name="P", path=str(tmp_path))

    servico.open_in_editor(projeto)

    assert eventos == ["montou-comando", "registrou", f"focou:{tmp_path.name}"]
    assert runner.labels == ["system.vscode"]


# --- "online" sem prova de dono --------------------------------------------


def test_servico_online_em_porta_sem_dono_provado_e_marcado(  # type: ignore[no-untyped-def]
    client, workspace: Path
) -> None:
    """O caso do SmartDash: containers todos removidos, `uvicorn` parado, e o
    card dizendo "1/2 online". Quem respondia na 5432 era o Postgres de um
    projeto que nem está cadastrado. A verificação de saúde pergunta "tem
    alguém aí?" e nunca soube perguntar "quem?"."""
    from app.adapters.system.ports import ListeningPort
    from app.api.deps import get_port_discovery
    from app.core.cache import TTLCache
    from app.models.base import utcnow
    from app.services.health_service import HealthResult, HealthState
    from app.services.port_discovery_service import PortDiscoveryService
    from tests.conftest import WRITE_HEADERS
    from tests.unit.test_port_discovery import FakePortScanner

    caminho = workspace / "smartdash"
    caminho.mkdir()
    (caminho / "docker-compose.yml").write_text(
        "\n".join(
            [
                "services:",
                "  db:",
                "    image: postgres:16",
                "    ports:",
                '      - "5432:5432"',
            ]
        ),
        encoding="utf-8",
    )
    project_id = client.post(
        "/api/projects", json={"path": str(caminho)}, headers=WRITE_HEADERS
    ).json()["id"]

    # Alguém responde na 5432, e a descoberta só sabe que é um container —
    # evidência fraca, que não prova dono nenhum.
    disco = PortDiscoveryService(
        scanner=FakePortScanner(
            [
                ListeningPort(
                    port=5432,
                    pid=99,
                    process_name="com.docker.backend.exe",
                    cwd="C:/Users/User/AppData/Local/Docker",
                )
            ]
        ),
        cache=TTLCache(ttl_seconds=300),
    )
    disco.observe([])

    app = client.app
    app.state.health_service._store(
        HealthResult(
            project_id=project_id,
            key="db",
            state=HealthState.ONLINE,
            latency_ms=3,
            checked_at=utcnow(),
        )
    )
    app.dependency_overrides[get_port_discovery] = lambda: disco

    try:
        resposta = client.get(f"/api/projects/{project_id}/services")
    finally:
        app.dependency_overrides.pop(get_port_discovery, None)

    assert resposta.status_code == 200, resposta.text
    item = next(i for i in resposta.json()["items"] if i["key"] == "db")
    assert item["state"] == "ONLINE"
    assert item["unverified_owner"] is not None
    assert "5432" in item["unverified_owner"]


def test_container_do_proprio_projeto_publicando_a_porta_e_prova(client, workspace: Path) -> None:  # type: ignore[no-untyped-def]
    """Porta de container nunca casa por diretório — o `cwd` de um container
    aponta para a instalação do Docker. Sem consultar quem publica o quê, todo
    serviço em Compose ficaria marcado como "responde, mas não sei de quem",
    o que num fluxo baseado em Docker é ruído puro e não aviso."""
    from app.adapters.docker.models import ComposeStatus, Container, PublishedPort
    from app.adapters.system.ports import ListeningPort
    from app.api.deps import get_docker_service, get_port_discovery
    from app.core.cache import TTLCache
    from app.models.base import utcnow
    from app.services.health_service import HealthResult, HealthState
    from app.services.port_discovery_service import PortDiscoveryService
    from tests.conftest import WRITE_HEADERS
    from tests.unit.test_port_discovery import FakePortScanner

    caminho = workspace / "comdocker"
    caminho.mkdir()
    (caminho / "docker-compose.yml").write_text(
        "\n".join(
            [
                "services:",
                "  db:",
                "    image: postgres:16",
                "    ports:",
                '      - "5435:5432"',
            ]
        ),
        encoding="utf-8",
    )
    project_id = client.post(
        "/api/projects", json={"path": str(caminho)}, headers=WRITE_HEADERS
    ).json()["id"]

    disco = PortDiscoveryService(
        scanner=FakePortScanner(
            [
                ListeningPort(
                    port=5435,
                    pid=99,
                    process_name="com.docker.backend.exe",
                    cwd="C:/Users/User/AppData/Local/Docker",
                )
            ]
        ),
        cache=TTLCache(ttl_seconds=300),
    )
    disco.observe([])

    class DockerComContainer:
        def status(self, _project):  # type: ignore[no-untyped-def]
            return ComposeStatus(
                available=True,
                compose_file="docker-compose.yml",
                containers=[
                    Container(
                        name="comdocker-db-1",
                        service="db",
                        state="running",
                        image="postgres:16",
                        status="Up",
                        ports=[PublishedPort(host_port=5435, container_port=5432)],
                    )
                ],
            )

    app = client.app
    app.state.health_service._store(
        HealthResult(
            project_id=project_id,
            key="db",
            state=HealthState.ONLINE,
            latency_ms=3,
            checked_at=utcnow(),
        )
    )
    app.dependency_overrides[get_port_discovery] = lambda: disco
    app.dependency_overrides[get_docker_service] = DockerComContainer

    try:
        resposta = client.get(f"/api/projects/{project_id}/services")
    finally:
        app.dependency_overrides.pop(get_port_discovery, None)
        app.dependency_overrides.pop(get_docker_service, None)

    item = next(i for i in resposta.json()["items"] if i["key"] == "db")
    assert item["state"] == "ONLINE"
    assert item["unverified_owner"] is None, "o container do projeto publica a porta: é prova"
