"""Registry de detecção e extração de portas."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.detection.detectors.docker_stack import parse_published_port
from app.detection.registry import DetectionRegistry

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "compose"


@pytest.fixture
def registry() -> DetectionRegistry:
    return DetectionRegistry()


def names(detection) -> set[str]:  # type: ignore[no-untyped-def]
    return {tech.name for tech in detection.technologies}


# --- Python ---------------------------------------------------------------


def test_requirements_detecta_fastapi_e_postgres(registry, workspace: Path) -> None:
    project = workspace / "api"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "fastapi==0.115.0\nuvicorn[standard]\npsycopg2-binary\n# comentario\n-r outro.txt\n",
        encoding="utf-8",
    )

    detection = registry.run(project)

    assert {"python", "fastapi", "uvicorn"} <= names(detection)
    assert any(service.port == 8000 for service in detection.services)


def test_pyproject_com_dependencias(registry, workspace: Path) -> None:
    project = workspace / "svc"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "svc"\ndependencies = ["flask>=3", "redis"]\n', encoding="utf-8"
    )

    detection = registry.run(project)

    assert {"python", "flask", "redis"} <= names(detection)


def test_pyproject_invalido_gera_aviso_e_nao_erro(registry, workspace: Path) -> None:
    project = workspace / "quebrado"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project\nnome = ", encoding="utf-8")

    detection = registry.run(project)

    assert "python" in names(detection)
    assert detection.warnings


# --- Node -----------------------------------------------------------------


def test_package_json_detecta_next(registry, workspace: Path) -> None:
    project = workspace / "web"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"next": "15", "react": "19"},
                "devDependencies": {"typescript": "5"},
            }
        ),
        encoding="utf-8",
    )

    detection = registry.run(project)

    assert {"node", "nextjs", "react", "typescript"} <= names(detection)
    assert any(service.port == 3000 for service in detection.services)


def test_package_json_invalido_mantem_runtime(registry, workspace: Path) -> None:
    project = workspace / "web-quebrado"
    project.mkdir()
    (project / "package.json").write_text("{ nao é json", encoding="utf-8")

    detection = registry.run(project)

    assert "node" in names(detection)
    assert detection.warnings


def test_vite_config_extrai_porta_declarada(registry, workspace: Path) -> None:
    project = workspace / "spa"
    project.mkdir()
    (project / "vite.config.ts").write_text(
        "export default defineConfig({ server: { port: 4200 } })", encoding="utf-8"
    )

    detection = registry.run(project)

    assert "vite" in names(detection)
    assert any(service.port == 4200 for service in detection.services)


def test_vite_sem_porta_usa_convencao(registry, workspace: Path) -> None:
    project = workspace / "spa2"
    project.mkdir()
    (project / "vite.config.js").write_text("export default {}", encoding="utf-8")

    detection = registry.run(project)

    assert any(service.port == 5173 for service in detection.services)


# --- Docker ---------------------------------------------------------------


def test_compose_extrai_portas_e_imagens(registry, workspace: Path) -> None:
    project = workspace / "stack"
    project.mkdir()
    shutil.copy(FIXTURES / "multi_service.yml", project / "docker-compose.yml")

    detection = registry.run(project)

    assert {"docker", "docker-compose", "postgresql"} <= names(detection)
    assert detection.compose_file == "docker-compose.yml"

    ports = {service.port for service in detection.services}
    assert {5173, 8000, 5432} <= ports
    # serviço sem `ports` não vira serviço; faixa de portas é ignorada
    assert not any(service.key == "worker" for service in detection.services)
    assert not any(service.key == "ranged" for service in detection.services)


def test_compose_invalido_avisa_sem_quebrar(registry, workspace: Path) -> None:
    project = workspace / "stack-ruim"
    project.mkdir()
    shutil.copy(FIXTURES / "malformed.yml", project / "compose.yml")

    detection = registry.run(project)

    assert "docker" in names(detection)
    assert detection.warnings


def test_backend_do_compose_tem_health_http(registry, workspace: Path) -> None:
    project = workspace / "stack2"
    project.mkdir()
    shutil.copy(FIXTURES / "multi_service.yml", project / "docker-compose.yml")

    detection = registry.run(project)
    backend = next(s for s in detection.services if s.key == "backend")
    db = next(s for s in detection.services if s.key == "db")

    assert backend.health_kind == "HTTP"
    assert db.health_kind == "TCP"
    assert db.url is None


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("8000:8000", 8000),
        ("127.0.0.1:8000:8000", 8000),
        ("8000:8000/tcp", 8000),
        (8000, 8000),
        ({"published": 8000}, 8000),
        ("9000-9010:9000-9010", None),
        ("nao-e-porta", None),
        ("99999:80", None),
        (None, None),
    ],
)
def test_parse_de_porta_publicada(entrada: object, esperado: int | None) -> None:
    assert parse_published_port(entrada) == esperado


# --- outras stacks e regras gerais ----------------------------------------


@pytest.mark.parametrize(
    ("marker", "esperado"),
    [
        ("pom.xml", {"java", "maven"}),
        ("build.gradle", {"java", "gradle"}),
        ("go.mod", {"go"}),
        ("Cargo.toml", {"rust"}),
        ("Dockerfile", {"docker"}),
    ],
)
def test_marcadores_simples(registry, workspace: Path, marker: str, esperado: set[str]) -> None:
    project = workspace / marker.replace(".", "-")
    project.mkdir()
    (project / marker).write_text("x", encoding="utf-8")

    assert esperado <= names(registry.run(project))


def test_multiplas_stacks_no_mesmo_projeto(registry, workspace: Path) -> None:
    project = workspace / "fullstack"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (project / "package.json").write_text('{"dependencies":{"react":"19"}}', encoding="utf-8")
    (project / "Dockerfile").write_text("FROM python", encoding="utf-8")

    detection = registry.run(project)

    assert {"python", "fastapi", "node", "react", "docker"} <= names(detection)


def test_projeto_sem_marcador_nao_detecta_nada(registry, workspace: Path) -> None:
    project = workspace / "vazio"
    project.mkdir()

    assert registry.run(project).technologies == []


def test_html_estatico_e_apenas_fallback(registry, workspace: Path) -> None:
    """Um `index.html` de template não pode rotular um Next.js como estático."""
    estatico = workspace / "site"
    estatico.mkdir()
    (estatico / "index.html").write_text("<h1>oi</h1>", encoding="utf-8")
    assert "html" in names(registry.run(estatico))

    nextjs = workspace / "app-next"
    nextjs.mkdir()
    (nextjs / "index.html").write_text("<h1>oi</h1>", encoding="utf-8")
    (nextjs / "next.config.js").write_text("module.exports = {}", encoding="utf-8")
    assert "html" not in names(registry.run(nextjs))


def test_diretorio_inexistente_avisa_em_vez_de_falhar(registry, workspace: Path) -> None:
    detection = registry.run(workspace / "fantasma")

    assert detection.technologies == []
    assert detection.warnings


# --- divergência entre o cadastro e o arquivo ------------------------------
#
# A detecção nunca sobrescreve o que o usuário cadastrou, e isso está certo. O
# que faltava era o outro lado: não sobrescrever não é motivo para não contar.


def _projeto_com_compose(session, workspace: Path, porta_no_arquivo: int):  # type: ignore[no-untyped-def]
    from app.models.project import Project

    diretorio = workspace / "stack"
    diretorio.mkdir()
    (diretorio / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    ports:\n"
        f'      - "{porta_no_arquivo}:5432"\n',
        encoding="utf-8",
    )
    project = Project(id="stack", name="Stack", path=str(diretorio))
    session.add(project)
    session.flush()
    return project


def test_porta_que_mudou_no_arquivo_e_relatada_sem_ser_aplicada(session, workspace: Path) -> None:  # type: ignore[no-untyped-def]
    """O caso real: o `.env` do projeto passou a publicar outra porta e o
    cadastro ficou onde estava. A detecção respondia "nada mudou" enquanto o
    painel verificava um número que o projeto já tinha abandonado."""
    from app.models.project import ProjectService as ProjectServiceModel
    from app.services.detection_service import DetectionService

    project = _projeto_com_compose(session, workspace, porta_no_arquivo=5434)
    project.services.append(ProjectServiceModel(key="db", label="Database", port=5433))
    session.flush()

    diff = DetectionService(session=session).run_for(project, record=False)

    assert [(d.key, d.declared, d.detected) for d in diff.port_drift] == [("db", 5433, 5434)]
    # Relatado, não aplicado: o cadastro é do usuário.
    assert next(s.port for s in project.services if s.key == "db") == 5433


def test_porta_igual_no_arquivo_e_no_cadastro_nao_gera_divergencia(
    session, workspace: Path
) -> None:  # type: ignore[no-untyped-def]
    from app.models.project import ProjectService as ProjectServiceModel
    from app.services.detection_service import DetectionService

    project = _projeto_com_compose(session, workspace, porta_no_arquivo=5433)
    project.services.append(ProjectServiceModel(key="db", label="Database", port=5433))
    session.flush()

    assert DetectionService(session=session).run_for(project, record=False).port_drift == []


def test_divergencia_entra_no_registro_de_atividade(session, workspace: Path) -> None:  # type: ignore[no-untyped-def]
    """Quem for entender depois por que o serviço vivia offline procura no
    histórico, não no toast que passou há três dias."""
    from app.models.project import ActivityLog
    from app.models.project import ProjectService as ProjectServiceModel
    from app.services.detection_service import DetectionService

    project = _projeto_com_compose(session, workspace, porta_no_arquivo=5434)
    project.services.append(ProjectServiceModel(key="db", label="Database", port=5433))
    session.flush()

    DetectionService(session=session).run_for(project)
    session.flush()

    registro = session.query(ActivityLog).filter(ActivityLog.action == "project.detect").one()
    assert "5433->5434" in registro.message


def test_porta_convencional_do_framework_nao_acusa_o_cadastro(session, workspace: Path) -> None:  # type: ignore[no-untyped-def]
    """A primeira versão desta checagem acusou os três projetos da máquina de
    uma vez, todos com o mesmo "detected: 8000" — que é o padrão do uvicorn, e
    não uma leitura de arquivo nenhum. Quem cadastrou 3001 passa `--port 3001`;
    o padrão do framework não contradiz isso, e tratar como contradição faz de
    toda porta escolhida a mão um alerta permanente."""
    from app.models.project import Project
    from app.models.project import ProjectService as ProjectServiceModel
    from app.services.detection_service import DetectionService

    diretorio = workspace / "api"
    diretorio.mkdir()
    (diretorio / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    project = Project(id="api", name="Api", path=str(diretorio))
    session.add(project)
    session.flush()
    project.services.append(ProjectServiceModel(key="backend", label="Backend", port=3001))
    session.flush()

    diff = DetectionService(session=session).run_for(project, record=False)

    assert diff.port_drift == []


# --- porta escrita como variável no Compose --------------------------------


def test_porta_com_variavel_usa_o_valor_do_env(registry, workspace: Path) -> None:
    """O Compose da PLATAFORMA publica `${POSTGRES_PORT:-5434}`. Sem resolver a
    variável, um arquivo inteiro escrito assim rendia zero portas — e a
    detecção respondia "nada encontrado" sem dizer que não soube ler."""
    project = workspace / "ingressos"
    project.mkdir()
    (project / ".env").write_text("POSTGRES_PORT=5440\n", encoding="utf-8")
    (project / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    ports:\n"
        '      - "${POSTGRES_PORT:-5434}:5432"\n',
        encoding="utf-8",
    )

    detection = registry.run(project)

    assert [(s.key, s.port) for s in detection.services] == [("db", 5440)]


def test_sem_env_a_variavel_cai_no_valor_de_reserva(registry, workspace: Path) -> None:
    project = workspace / "reserva"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        'services:\n  web:\n    image: nginx\n    ports:\n      - "${WEB_PORT:-8000}:8000"\n',
        encoding="utf-8",
    )

    assert [s.port for s in registry.run(project).services] == [8000]


def test_variavel_sem_reserva_e_sem_env_nao_vira_porta(registry, workspace: Path) -> None:
    """Não dá para saber o número. Inventar um seria pior que não sugerir."""
    project = workspace / "vazia"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        'services:\n  web:\n    image: nginx\n    ports:\n      - "${WEB_PORT}:8000"\n',
        encoding="utf-8",
    )

    assert [s.port for s in registry.run(project).services] == []


def test_env_com_comentario_e_aspas(workspace: Path) -> None:
    from app.detection.detectors.docker_stack import read_env_file

    project = workspace / "envfile"
    project.mkdir()
    (project / ".env").write_text(
        '# porta do banco\nPOSTGRES_PORT="5440"\n\nVAZIO=\n', encoding="utf-8"
    )

    assert read_env_file(project) == {"POSTGRES_PORT": "5440", "VAZIO": ""}


# --- monorepo -------------------------------------------------------------


def test_monorepo_sem_marcador_na_raiz_e_reconhecido(registry, workspace: Path) -> None:
    """Um repositório com `backend/` e `frontend/` não declara nada na raiz.

    Ele aparecia sem stack nenhuma no painel — e sem ambiente, porque o Compose
    de quem separa infraestrutura mora em `infra/`. O planejador de execução já
    descia um nível; a detecção não, e as duas discordavam sobre o mesmo
    projeto.
    """
    projeto = workspace / "monorepo"
    (projeto / "backend").mkdir(parents=True)
    (projeto / "frontend").mkdir()
    (projeto / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (projeto / "frontend" / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^15.0.0"}}), encoding="utf-8"
    )

    detection = registry.run(projeto)

    assert {"fastapi", "nextjs"} <= names(detection)


def test_a_evidencia_diz_de_qual_pasta_veio(registry, workspace: Path) -> None:
    """"pyproject.toml" mandaria procurar na raiz um arquivo que está em `backend/`."""
    projeto = workspace / "monorepo"
    (projeto / "backend").mkdir(parents=True)
    (projeto / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    detection = registry.run(projeto)

    fastapi = next(t for t in detection.technologies if t.name == "fastapi")
    assert fastapi.evidence.startswith("backend/")


def test_compose_em_subpasta_vem_com_o_caminho(registry, workspace: Path) -> None:
    """Nome solto mentiria: quem lê "docker-compose.yml" procura na raiz."""
    projeto = workspace / "monorepo"
    (projeto / "infra").mkdir(parents=True)
    shutil.copy(FIXTURES / "multi_service.yml", projeto / "infra" / "docker-compose.yml")

    detection = registry.run(projeto)

    assert detection.compose_file == "infra/docker-compose.yml"


def test_a_raiz_vence_a_subpasta(registry, workspace: Path) -> None:
    """O que a raiz declara é a palavra do projeto sobre si mesmo."""
    projeto = workspace / "monorepo"
    (projeto / "backend").mkdir(parents=True)
    (projeto / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (projeto / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    detection = registry.run(projeto)

    fastapi = next(t for t in detection.technologies if t.name == "fastapi")
    assert fastapi.evidence == "requirements.txt", "a evidência da raiz não foi substituída"


def test_deteccao_nao_cadastra_servico_em_porta_ja_ocupada(session, workspace: Path) -> None:  # type: ignore[no-untyped-def]
    """A rota de edição recusa porta duplicada desde a sessão passada.

    A detecção entrava pela outra porta da mesma casa: chave nova e porta
    ocupada criavam `postgres 5442` ao lado de `servico-5442`, os dois na mesma
    porta — o estado que a API proíbe, gravado pelo próprio painel, com a tela
    depois acusando a inconsistência que ele mesmo produziu.

    Quase sempre é o mesmo serviço com outro nome: o painel cadastrou a partir
    de uma porta observada, o Compose chama de `db`. Renomear seria decidir
    sozinho; duplicar seria mentir.
    """
    from app.models.project import ProjectService as ProjectServiceModel
    from app.services.detection_service import DetectionService

    project = _projeto_com_compose(session, workspace, porta_no_arquivo=5433)
    project.services.append(ProjectServiceModel(key="servico-5433", label="App", port=5433))
    session.flush()

    diff = DetectionService(session=session).run_for(project, record=False)

    assert "db" not in diff.services_added
    assert [s.key for s in project.services] == ["servico-5433"]
    assert any("já é de 'servico-5433'" in aviso for aviso in diff.warnings), (
        "ignorar em silêncio deixaria a pessoa sem saber por que o serviço não apareceu"
    )
