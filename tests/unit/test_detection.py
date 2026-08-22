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
