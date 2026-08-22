"""Descoberta de porta: quem está escutando e de qual projeto é.

Nenhum teste aqui olha as portas da máquina. O `FakePortScanner` entrega uma
lista fixa, que é o que permite exercitar o caso de `cwd` negado, o caso do
Docker e o caso do projeto dentro de projeto — nenhum dos três reproduzível sob
demanda numa máquina real.
"""

from __future__ import annotations

import os

import pytest

from app.adapters.system.ports import FakePortScanner, ListeningPort, normalized
from app.core.cache import TTLCache
from app.services.port_discovery_service import (
    PortDiscoveryService,
    ProjectRef,
)

RAIZ = "C:/dev" if os.name == "nt" else "/dev"


def projeto(nome: str, sub: str) -> ProjectRef:
    return ProjectRef(id=nome, name=nome.title(), path=f"{RAIZ}/{sub}")


def servico(cache_ttl: float = 300.0) -> tuple[PortDiscoveryService, FakePortScanner]:
    scanner = FakePortScanner()
    return PortDiscoveryService(scanner=scanner, cache=TTLCache(ttl_seconds=cache_ttl)), scanner


# --- normalização de path ------------------------------------------------


def test_normalized_devolve_none_sem_path() -> None:
    """`cwd` negado chega como None e não pode virar tupla vazia.

    Tupla vazia é prefixo de qualquer coisa: casaria com todo projeto.
    """
    assert normalized(None) is None
    assert normalized("") is None


@pytest.mark.skipif(os.name != "nt", reason="a insensibilidade a caixa é do Windows")
def test_normalized_ignora_caixa_no_windows() -> None:
    assert normalized("C:/Dev/App") == normalized("c:/dev/app")


# --- atribuição por diretório de trabalho --------------------------------


def test_porta_e_do_projeto_quando_o_processo_roda_dentro_dele() -> None:
    disco, scanner = servico()
    app = projeto("app", "app")
    scanner.ports = [
        ListeningPort(port=8765, pid=10, process_name="python.exe", cwd=f"{RAIZ}/app")
    ]

    observacao = disco.observe([app])

    assert len(observacao.ports) == 1
    porta = observacao.ports[0]
    assert porta.project_id == "app"
    assert porta.matched_by == "cwd"
    assert porta.claimed is True


def test_subdiretorio_do_projeto_tambem_conta() -> None:
    """`npm run dev` roda de `frontend/`, não da raiz."""
    disco, scanner = servico()
    app = projeto("app", "app")
    scanner.ports = [
        ListeningPort(port=5173, pid=11, process_name="node.exe", cwd=f"{RAIZ}/app/frontend")
    ]

    assert disco.observe([app]).ports[0].project_id == "app"


def test_projeto_vizinho_de_nome_parecido_nao_casa() -> None:
    """O bug que `app/core/paths.py` existe para não ter, agora aqui também.

    Comparar por texto faria `/dev/app-antigo` casar com `/dev/app`.
    """
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(port=3000, pid=12, process_name="node.exe", cwd=f"{RAIZ}/app-antigo")
    ]

    observacao = disco.observe([projeto("app", "app")])

    assert observacao.ports[0].project_id is None


def test_projeto_aninhado_vence_o_pai() -> None:
    """Num monorepo, a porta é do pacote que a abriu, não do repositório."""
    disco, scanner = servico()
    mono = projeto("mono", "mono")
    interno = ProjectRef(id="api", name="Api", path=f"{RAIZ}/mono/services/api")
    scanner.ports = [
        ListeningPort(port=8000, pid=13, process_name="python.exe", cwd=f"{RAIZ}/mono/services/api")
    ]

    observacao = disco.observe([mono, interno])

    assert observacao.ports[0].project_id == "api"


def test_cwd_negado_nao_atribui_a_ninguem() -> None:
    """Processo de outro usuário recusa a leitura; a porta segue reportada."""
    disco, scanner = servico()
    scanner.ports = [ListeningPort(port=445, pid=4, process_name="System", cwd=None)]

    observacao = disco.observe([projeto("app", "app")])

    assert observacao.ports[0].project_id is None
    assert observacao.ports[0].matched_by == "unknown"
    assert observacao.ports[0].port == 445


# --- atribuição por linha de comando -------------------------------------


def test_linha_de_comando_com_o_caminho_do_projeto_casa() -> None:
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(
            port=8080,
            pid=14,
            process_name="python.exe",
            cwd=f"{RAIZ}/outro-lugar",
            cmdline=f"python -m uvicorn --app-dir {RAIZ}/app app.main:app",
        )
    ]

    observacao = disco.observe([projeto("app", "app")])

    assert observacao.ports[0].project_id == "app"
    assert observacao.ports[0].matched_by == "cmdline"


def test_linha_de_comando_tolera_barra_invertida() -> None:
    """O mesmo caminho aparece com `\\` no argumento e `/` no cadastro."""
    disco, scanner = servico()
    caminho_windows = f"{RAIZ}/app".replace("/", "\\")
    scanner.ports = [
        ListeningPort(
            port=8080,
            pid=15,
            process_name="node.exe",
            cwd=None,
            cmdline=f"node {caminho_windows}\\server.js",
        )
    ]

    assert disco.observe([projeto("app", "app")]).ports[0].project_id == "app"


# --- runtime de container ------------------------------------------------


def test_porta_do_docker_e_marcada_em_vez_de_atribuida() -> None:
    """O `cwd` do Docker aponta para a instalação dele, nunca para o projeto.

    Marcar é melhor que chutar: "publicada por container" é verdade, e
    "dono desconhecido" faria a pessoa procurar um processo que não existe.
    """
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(
            port=8123,
            pid=16,
            process_name="com.docker.backend.exe",
            cwd="C:/Users/User/AppData/Local/Docker",
        )
    ]

    porta = disco.observe([projeto("app", "app")]).ports[0]

    assert porta.project_id is None
    assert porta.matched_by == "container"


def test_projeto_vence_o_docker_quando_o_cwd_casa() -> None:
    """Ordem importa: `cwd` dentro do projeto é evidência mais forte."""
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(
            port=8123,
            pid=17,
            process_name="docker-proxy",
            cwd=f"{RAIZ}/app",
        )
    ]

    assert disco.observe([projeto("app", "app")]).ports[0].matched_by == "cwd"


# --- resiliência e cache -------------------------------------------------


class ScannerQueQuebra(FakePortScanner):
    def scan(self) -> list[ListeningPort]:
        raise OSError("sem privilégio")


def test_varredura_que_falha_nao_propaga_e_marca_indisponivel() -> None:
    """Distinguir "não consegui olhar" de "nada escutando" é o ponto.

    Sem a marca, uma varredura recusada apareceria na tela como o mesmo
    silêncio de uma máquina sem serviço nenhum no ar.
    """
    disco = PortDiscoveryService(scanner=ScannerQueQuebra(), cache=TTLCache(ttl_seconds=300))

    observacao = disco.observe([projeto("app", "app")])

    assert observacao.available is False
    assert observacao.ports == []


def test_last_known_e_vazio_antes_do_primeiro_ciclo() -> None:
    disco, _ = servico()

    observacao = disco.last_known()

    assert observacao.ports == []
    # Vazio por não ter varrido ainda não é o mesmo que varredura recusada.
    assert observacao.available is True


def test_last_known_devolve_a_ultima_varredura_mesmo_expirada() -> None:
    """O dado velho vale mais que dado nenhum: a tela mostra a idade dele."""
    disco, scanner = servico(cache_ttl=0.0)
    scanner.ports = [ListeningPort(port=8765, pid=10, cwd=f"{RAIZ}/app", process_name="python.exe")]
    disco.observe([projeto("app", "app")])

    assert [p.port for p in disco.last_known().ports] == [8765]


def test_uma_porta_em_ipv4_e_ipv6_conta_uma_vez() -> None:
    """O par `0.0.0.0` + `::` é a mesma porta vista duas vezes."""
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(port=8765, pid=10, cwd=f"{RAIZ}/app", addresses=frozenset({"0.0.0.0", "::"}))
    ]

    assert len(disco.observe([projeto("app", "app")]).ports) == 1


def test_for_project_filtra_pelo_dono() -> None:
    disco, scanner = servico()
    scanner.ports = [
        ListeningPort(port=8765, pid=10, cwd=f"{RAIZ}/app", process_name="python.exe"),
        ListeningPort(port=3000, pid=11, cwd=f"{RAIZ}/web", process_name="node.exe"),
    ]

    observacao = disco.observe([projeto("app", "app"), projeto("web", "web")])

    assert [p.port for p in observacao.for_project("app")] == [8765]


# --- contrato HTTP: declarado x observado --------------------------------


def _cadastra(client, workspace, nome: str, porta: int) -> str:  # type: ignore[no-untyped-def]
    from tests.conftest import WRITE_HEADERS

    diretorio = workspace / nome
    diretorio.mkdir(exist_ok=True)
    criado = client.post(
        "/api/projects",
        json={"path": str(diretorio), "name": nome, "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()
    client.put(
        f"/api/projects/{criado['id']}/services",
        json={"items": [{"key": "backend", "label": "Backend", "port": porta}]},
        headers=WRITE_HEADERS,
    )
    return criado["id"]


def test_ports_sem_varredura_ainda_responde(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """Antes do primeiro ciclo do poller a tela precisa carregar assim mesmo."""
    _cadastra(client, workspace, "app", 3000)

    corpo = client.get("/api/services/ports").json()

    assert corpo["observed"] == []
    assert corpo["observation_available"] is True
    assert corpo["mismatches"] == []
    # O lado declarado continua completo: a descoberta é acréscimo, não troca.
    assert [b["port"] for b in corpo["bindings"]] == [3000]


def test_ports_aponta_a_divergencia_entre_declarado_e_observado(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """O caso concreto: cadastrado em 3003, servidor no ar em 8765."""
    projeto_id = _cadastra(client, workspace, "app", 3003)

    client.app.state.port_discovery.scanner = FakePortScanner(
        [
            ListeningPort(
                port=8765,
                pid=99,
                process_name="python.exe",
                cwd=str(workspace / "app"),
            )
        ]
    )
    client.app.state.port_discovery.observe(
        [ProjectRef(id=projeto_id, name="app", path=str(workspace / "app"))]
    )

    corpo = client.get("/api/services/ports").json()

    assert [p["port"] for p in corpo["observed"]] == [8765]
    assert corpo["observed"][0]["project_id"] == projeto_id

    assert len(corpo["mismatches"]) == 1
    divergencia = corpo["mismatches"][0]
    assert divergencia["declared_port"] == 3003
    assert divergencia["observed_port"] == 8765
    assert divergencia["service_key"] == "backend"


def test_projeto_parado_nao_vira_divergencia(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """Silêncio é o estado esperado de projeto desligado, não alerta.

    Sem esta regra, todo projeto que não está rodando apareceria como "porta
    errada" — e um aviso que aparece para todo mundo não avisa ninguém.
    """
    _cadastra(client, workspace, "app", 3000)

    client.app.state.port_discovery.scanner = FakePortScanner(
        [ListeningPort(port=6463, pid=50, process_name="Discord.exe", cwd="C:/Discord")]
    )
    client.app.state.port_discovery.observe([])

    corpo = client.get("/api/services/ports").json()

    assert corpo["mismatches"] == []
    # A porta de terceiro continua listada: é ela que explica um `up` que
    # falha com "address already in use".
    assert [p["port"] for p in corpo["observed"]] == [6463]
    assert corpo["observed"][0]["project_id"] is None


def test_porta_declarada_que_confere_nao_vira_divergencia(client, workspace) -> None:  # type: ignore[no-untyped-def]
    projeto_id = _cadastra(client, workspace, "app", 8765)

    client.app.state.port_discovery.scanner = FakePortScanner(
        [ListeningPort(port=8765, pid=99, process_name="python.exe", cwd=str(workspace / "app"))]
    )
    client.app.state.port_discovery.observe(
        [ProjectRef(id=projeto_id, name="app", path=str(workspace / "app"))]
    )

    assert client.get("/api/services/ports").json()["mismatches"] == []


def test_uma_porta_observada_nao_e_sugerida_a_dois_servicos(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """Aceitar as duas sugestões poria os dois serviços na mesma porta.

    Seria um conflito criado pela própria ferramenta que existe para apontar
    conflitos. Com ambiguidade, o certo é reportar sem sugerir.
    """
    from tests.conftest import WRITE_HEADERS

    diretorio = workspace / "app"
    diretorio.mkdir(exist_ok=True)
    criado = client.post(
        "/api/projects",
        json={"path": str(diretorio), "name": "app", "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()
    client.put(
        f"/api/projects/{criado['id']}/services",
        json={
            "items": [
                {"key": "backend", "label": "Backend", "port": 3004},
                {"key": "db", "label": "Database", "port": 3005},
            ]
        },
        headers=WRITE_HEADERS,
    )

    # Só uma porta do projeto está escutando; os dois serviços divergem dela.
    client.app.state.port_discovery.scanner = FakePortScanner(
        [ListeningPort(port=8000, pid=7, process_name="python.exe", cwd=str(diretorio))]
    )
    client.app.state.port_discovery.observe(
        [ProjectRef(id=criado["id"], name="app", path=str(diretorio))]
    )

    corpo = client.get("/api/services/ports").json()

    assert len(corpo["mismatches"]) == 2
    # A divergência continua sendo apontada — o número está errado nos dois.
    assert {m["declared_port"] for m in corpo["mismatches"]} == {3004, 3005}
    # Mas nenhuma sugestão: não há como saber qual serviço é o da 8000.
    assert all(m["observed_port"] is None for m in corpo["mismatches"])


def test_com_um_so_servico_divergente_a_sugestao_volta(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """Sem ambiguidade a porta que sobra é daquele serviço, e o clique economiza
    a digitação."""
    from tests.conftest import WRITE_HEADERS

    diretorio = workspace / "solo"
    diretorio.mkdir(exist_ok=True)
    criado = client.post(
        "/api/projects",
        json={"path": str(diretorio), "name": "solo", "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()
    client.put(
        f"/api/projects/{criado['id']}/services",
        json={"items": [{"key": "backend", "label": "Backend", "port": 3004}]},
        headers=WRITE_HEADERS,
    )

    client.app.state.port_discovery.scanner = FakePortScanner(
        [ListeningPort(port=8000, pid=7, process_name="python.exe", cwd=str(diretorio))]
    )
    client.app.state.port_discovery.observe(
        [ProjectRef(id=criado["id"], name="solo", path=str(diretorio))]
    )

    divergencias = client.get("/api/services/ports").json()["mismatches"]

    assert len(divergencias) == 1
    assert divergencias[0]["observed_port"] == 8000


def test_porta_de_container_e_atribuida_a_quem_a_declara_sozinho() -> None:
    """O banco em container é do projeto cujo Compose o publicou.

    Sem esta regra ele aparecia como "sem dono" e o serviço declarado virava
    divergência — alarme falso justamente na configuração que o painel
    recomenda: ambiente em container, aplicação nativa.
    """
    disco, scanner = servico()
    app = ProjectRef(id="app", name="App", path=f"{RAIZ}/app", declared_ports=(5432,))
    scanner.ports = [
        ListeningPort(
            port=5432,
            pid=9,
            process_name="com.docker.backend.exe",
            cwd="C:/Docker",
        )
    ]

    porta = disco.observe([app]).ports[0]

    assert porta.project_id == "app"
    assert porta.matched_by == "container"


def test_porta_de_container_disputada_por_dois_projetos_nao_e_atribuida() -> None:
    """Evidência ambígua não vira atribuição: é o conflito que a tela aponta."""
    disco, scanner = servico()
    a = ProjectRef(id="a", name="A", path=f"{RAIZ}/a", declared_ports=(5432,))
    b = ProjectRef(id="b", name="B", path=f"{RAIZ}/b", declared_ports=(5432,))
    scanner.ports = [
        ListeningPort(port=5432, pid=9, process_name="com.docker.backend.exe", cwd="C:/Docker")
    ]

    assert disco.observe([a, b]).ports[0].project_id is None
