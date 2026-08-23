"""Detectores de Docker e Docker Compose.

O arquivo Compose é a melhor fonte de portas que existe no projeto: é
declarativo, versionado e reflete o que de fato sobe.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.detection.types import Category, DetectedTech, Detection, SuggestedService

COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

# Serviços cujo nome sugere o papel, para dar rótulo melhor que o nome cru.
ROLE_LABELS = {
    "frontend": "Frontend",
    "front": "Frontend",
    "web": "Frontend",
    "ui": "Frontend",
    "backend": "Backend",
    "api": "Backend",
    "server": "Backend",
    "app": "App",
    "db": "Database",
    "database": "Database",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongo": "MongoDB",
    "redis": "Redis",
    "worker": "Worker",
}

IMAGE_TECHNOLOGIES = {
    "postgres": "postgresql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "redis": "redis",
    "mongo": "mongodb",
    "rabbitmq": "rabbitmq",
    "nginx": "nginx",
}

HTTP_PORTS = {80, 3000, 4321, 5000, 5173, 8000, 8080, 8081, 8123, 8765, 9000}


def find_compose_file(project_dir: Path) -> Path | None:
    for name in COMPOSE_FILENAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    return None


#: `${POSTGRES_PORT:-5434}`, `${WEB_PORT}`, `$WEB_PORT`.
_VARIAVEL = re.compile(r"\$\{(\w+)(?::?-([^}]*))?\}|\$(\w+)")


def read_env_file(project_dir: Path) -> dict[str, str]:
    """As variáveis do `.env` ao lado do Compose, que é de onde ele as lê.

    Formato mínimo de propósito: `CHAVE=valor`, sem `export`, sem aspas
    inteligentes, sem continuação de linha. Só se precisa daqui o suficiente
    para resolver um número de porta, e um parser generoso demais acerta menos.
    """
    arquivo = project_dir / ".env"
    if not arquivo.is_file():
        return {}

    valores: dict[str, str] = {}
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    for linha in linhas:
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        chave, _, valor = limpa.partition("=")
        valores[chave.strip()] = valor.strip().strip("\"'")

    return valores


def _interpolar(texto: str, env: dict[str, str]) -> str:
    """Resolve `${VAR:-default}` como o Compose resolve: `.env` primeiro,
    depois o valor de reserva escrito na própria expressão."""

    def troca(casado: re.Match[str]) -> str:
        nome = casado.group(1) or casado.group(3)
        reserva = casado.group(2) or ""
        return env.get(nome, reserva)

    return _VARIAVEL.sub(troca, texto)


def parse_published_port(entry: object, env: dict[str, str] | None = None) -> int | None:
    """Extrai a porta publicada no host de uma entrada de `ports`.

    Formatos aceitos: `"8000:8000"`, `"127.0.0.1:8000:8000"`, `8000`,
    `{"published": 8000}`. Faixas (`"8000-8010:8000-8010"`) são ignoradas —
    sugerir a primeira porta de uma faixa seria adivinhação.

    Entrada com variável — `"${POSTGRES_PORT:-5434}:5432"` — é resolvida com o
    `.env` do projeto e, na falta dele, com o valor de reserva da própria
    expressão. Antes disso, um Compose inteiro escrito assim não rendia porta
    nenhuma: a PLATAFORMA publica `${POSTGRES_PORT:-5434}` e
    `${WEB_PORT:-8000}`, e a detecção devolvia zero serviços sem dizer por quê.
    """
    if isinstance(entry, dict):
        published = entry.get("published")
        if isinstance(published, str):
            published = _interpolar(published, env or {})
        try:
            return int(published) if published is not None else None
        except (TypeError, ValueError):
            return None

    if isinstance(entry, int):
        return entry if 1 <= entry <= 65535 else None

    if not isinstance(entry, str):
        return None

    text = _interpolar(entry.strip(), env or {}).split("/")[0]
    parts = text.split(":")

    host_part = parts[0] if len(parts) == 1 else parts[-2] if len(parts) >= 2 else None
    if host_part is None or "-" in host_part:
        return None

    try:
        port = int(host_part)
    except ValueError:
        return None

    return port if 1 <= port <= 65535 else None


class DockerfileDetector:
    name = "docker_dockerfile"

    def detect(self, project_dir: Path) -> Detection | None:
        if not (project_dir / "Dockerfile").is_file():
            return None
        return Detection(technologies=[DetectedTech("docker", Category.TOOLING, "Dockerfile")])


class ComposeDetector:
    name = "docker_compose"

    def detect(self, project_dir: Path) -> Detection | None:
        compose = find_compose_file(project_dir)
        if compose is None:
            return None

        detection = Detection(
            technologies=[
                DetectedTech("docker", Category.TOOLING, compose.name),
                DetectedTech("docker-compose", Category.TOOLING, compose.name),
            ],
            compose_file=compose.name,
        )

        # Lido uma vez para o arquivo inteiro: é o mesmo `.env` para todos os
        # serviços, e reler por porta seria I/O repetido à toa.
        env = read_env_file(project_dir)

        try:
            data = yaml.safe_load(compose.read_text(encoding="utf-8", errors="replace")) or {}
        except (yaml.YAMLError, OSError):
            detection.warnings.append(
                f"{compose.name} não pôde ser lido; portas não foram sugeridas."
            )
            return detection

        services = data.get("services")
        if not isinstance(services, dict):
            return detection

        for raw_name, definition in services.items():
            name = str(raw_name)
            if not isinstance(definition, dict):
                continue

            image = str(definition.get("image") or "")
            for marker, tech in IMAGE_TECHNOLOGIES.items():
                if marker in image.lower():
                    detection.technologies.append(
                        DetectedTech(tech, Category.DATABASE, compose.name)
                    )
                    break

            ports = definition.get("ports")
            if not isinstance(ports, list):
                continue

            for entry in ports:
                port = parse_published_port(entry, env)
                if port is None:
                    continue

                key = _service_key(name)
                if any(service.key == key for service in detection.services):
                    continue

                is_http = port in HTTP_PORTS
                detection.services.append(
                    SuggestedService(
                        key=key,
                        label=ROLE_LABELS.get(name.lower(), name),
                        port=port,
                        url=f"http://localhost:{port}" if is_http else None,
                        health_kind="HTTP" if is_http else "TCP",
                        # O Compose publica o número; não há convenção aqui.
                        port_source="file",
                    )
                )
                break

        return detection


def _service_key(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_-" else "-" for char in name.lower())
    return cleaned[:32] or "service"
