"""DockerAdapter — monta argv do `docker compose` e parseia a saída.

Por que o CLI e não o SDK: o SDK Python não cobre Compose v2, e o CLI é o
contrato real (ADR-003, decisão D-03).

O formato de `ps --format json` **varia entre versões**: umas devolvem um array
JSON, outras um objeto por linha. Verificado no Compose v5.3.1 desta máquina:
JSON por linha. O parser aceita os dois, e ignora qualquer linha que não comece
com `{` ou `[` — o Compose emite avisos (`the attribute version is obsolete`)
que podem se misturar à saída.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.docker.models import ComposeStatus, Container, PublishedPort
from app.runner.command_runner import CommandRunner
from app.runner.command_spec import CommandSpec

# Ações de leitura e de controle. Nenhuma remove volume: `-v` e `--volumes`
# não aparecem em lugar nenhum, por decisão (D-16, defesa D6).
COMPOSE_ACTIONS: dict[str, list[str]] = {
    "up": ["up", "-d", "--remove-orphans"],
    "down": ["down", "--remove-orphans"],
    "start": ["start"],
    "stop": ["stop"],
    "restart": ["restart"],
}

DAEMON_DOWN_MARKERS = (
    "error during connect",
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "docker daemon is not running",
    "open //./pipe/docker",
)

NO_COMPOSE_MARKERS = (
    "no configuration file provided",
    "no such file or directory",
)


class DockerAdapter:
    def __init__(
        self,
        runner: CommandRunner,
        docker_bin: str = "",
        read_timeout_s: float = 15.0,
    ) -> None:
        self.runner = runner
        self.docker_bin = docker_bin or "docker"
        self.read_timeout_s = read_timeout_s

    # --- construção de comandos ---

    def _compose_args(self, compose_file: str | None) -> list[str]:
        args = ["compose"]
        if compose_file:
            args += ["-f", compose_file]
        return args

    def _spec(
        self,
        project_dir: Path,
        args: list[str],
        label: str,
        timeout_s: float | None = None,
    ) -> CommandSpec:
        return CommandSpec(
            argv=[self.docker_bin, *args],
            cwd=project_dir,
            timeout_s=timeout_s or self.read_timeout_s,
            label=label,
        )

    def version_spec(self, project_dir: Path) -> CommandSpec:
        return self._spec(project_dir, ["compose", "version", "--short"], "docker.version")

    def ps_spec(self, project_dir: Path, compose_file: str | None) -> CommandSpec:
        args = [*self._compose_args(compose_file), "ps", "--all", "--format", "json"]
        return self._spec(project_dir, args, "docker.ps")

    def action_spec(
        self,
        project_dir: Path,
        compose_file: str | None,
        action: str,
        services: list[str],
        timeout_s: float,
    ) -> CommandSpec:
        """Monta o comando de uma ação do Compose.

        `action` vem de `COMPOSE_ACTIONS`, nunca do cliente. `services` já foi
        validado contra os serviços declarados no Compose do projeto — nome
        desconhecido nunca chega aqui.
        """
        if action not in COMPOSE_ACTIONS:
            raise ValueError(f"Ação Compose não permitida: {action!r}")

        args = [*self._compose_args(compose_file), *COMPOSE_ACTIONS[action], *services]
        return self._spec(project_dir, args, f"docker.{action}", timeout_s=timeout_s)

    def logs_spec(
        self,
        project_dir: Path,
        compose_file: str | None,
        service: str | None,
        tail: int,
    ) -> CommandSpec:
        args = [
            *self._compose_args(compose_file),
            "logs",
            "--no-color",
            "--tail",
            str(max(1, min(int(tail), 2000))),
        ]
        if service:
            args.append(service)
        return self._spec(project_dir, args, "docker.logs")

    # --- operações de leitura ---

    def compose_version(self, project_dir: Path) -> str | None:
        result = self.runner.run(self.version_spec(project_dir))
        return result.stdout.strip() or None if result.ok else None

    def status(
        self,
        project_dir: Path,
        compose_file: str | None,
    ) -> ComposeStatus:
        result = self.runner.run(self.ps_spec(project_dir, compose_file))

        if not result.ok:
            reason = classify_failure(result.stderr)
            return ComposeStatus(
                available=reason != "daemon_down" and reason != "unknown",
                compose_file=compose_file,
                detail=failure_message(reason, result.stderr),
            )

        return ComposeStatus(
            available=True,
            compose_file=compose_file,
            containers=parse_ps(result.stdout),
        )

    def logs(
        self,
        project_dir: Path,
        compose_file: str | None,
        service: str | None,
        tail: int = 200,
    ) -> tuple[bool, str]:
        result = self.runner.run(self.logs_spec(project_dir, compose_file, service, tail))
        if not result.ok:
            return False, failure_message(classify_failure(result.stderr), result.stderr)
        return True, result.stdout


# --- parsers -------------------------------------------------------------


def parse_ps(output: str) -> list[Container]:
    """Aceita array JSON e JSON-por-linha, e ignora ruído.

    Linha malformada é descartada em silêncio: uma versão do Compose que
    intercale aviso no meio da saída não pode zerar a lista de containers.
    """
    containers: list[Container] = []
    text = output.strip()
    if not text:
        return containers

    for entry in _iter_json_objects(text):
        container = _to_container(entry)
        if container is not None:
            containers.append(container)

    return containers


def _iter_json_objects(text: str):  # type: ignore[no-untyped-def]
    stripped = text.lstrip()

    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return
        if isinstance(data, list):
            yield from (item for item in data if isinstance(item, dict))
        return

    for line in text.splitlines():
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            entry = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def _to_container(entry: dict) -> Container | None:
    name = str(entry.get("Name") or entry.get("Names") or "").strip()
    if not name:
        return None

    health = str(entry.get("Health") or "").strip() or None
    exit_code = entry.get("ExitCode")

    return Container(
        name=name,
        service=str(entry.get("Service") or "").strip() or name,
        state=str(entry.get("State") or "unknown").strip(),
        image=str(entry.get("Image") or "").strip(),
        # `Status` é o texto do Docker ("Up 3 hours (unhealthy)"). Não se tenta
        # converter em segundos: o formato é humano e varia por locale.
        status=str(entry.get("Status") or "").strip(),
        health=health,
        exit_code=int(exit_code) if isinstance(exit_code, int) else None,
        ports=parse_publishers(entry),
    )


def parse_publishers(entry: dict) -> list[PublishedPort]:
    """Usa `Publishers`, que é estruturado, em vez de parsear a string `Ports`.

    Só interessa porta publicada no host; container sem publicação não aparece.
    Entradas IPv6 (`::`) duplicam a mesma porta e são deduplicadas.
    """
    publishers = entry.get("Publishers")
    if not isinstance(publishers, list):
        return []

    seen: set[tuple[int, int, str]] = set()
    ports: list[PublishedPort] = []

    for item in publishers:
        if not isinstance(item, dict):
            continue
        published = item.get("PublishedPort")
        target = item.get("TargetPort")
        if not isinstance(published, int) or published <= 0:
            continue

        key = (
            published,
            target if isinstance(target, int) else 0,
            str(item.get("Protocol") or "tcp"),
        )
        if key in seen:
            continue
        seen.add(key)
        ports.append(
            PublishedPort(host_port=key[0], container_port=key[1], protocol=key[2])
        )

    return sorted(ports, key=lambda port: port.host_port)


def classify_failure(stderr: str) -> str:
    lowered = stderr.lower()
    if any(marker in lowered for marker in DAEMON_DOWN_MARKERS):
        return "daemon_down"
    if any(marker in lowered for marker in NO_COMPOSE_MARKERS):
        return "no_compose"
    return "unknown"


def failure_message(reason: str, stderr: str) -> str:
    if reason == "daemon_down":
        return "O Docker não está respondendo. Verifique se o Docker Desktop está aberto."
    if reason == "no_compose":
        return "Nenhum arquivo Compose encontrado neste projeto."

    for line in stderr.splitlines():
        if line.strip() and not line.strip().startswith("time="):
            return line.strip()[:300]
    return "Falha ao consultar o Docker."
