"""Configuração da aplicação, carregada de variáveis de ambiente e de arquivos YAML.

Nada de porta, path ou timeout hardcoded fora daqui (NFR-022).
"""

from __future__ import annotations

import ipaddress
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Onde moram os recursos empacotados: frontend, migrações, configs de exemplo.

    Congelado pelo PyInstaller, o código roda de dentro de um diretório
    temporário (`sys._MEIPASS`) e `__file__` aponta para lá — não para a pasta
    do executável. Só os **recursos** vivem ali; banco, log e configuração do
    usuário ficam ao lado do `.exe`, e o `launcher` passa esses caminhos por
    variável de ambiente, sempre absolutos.
    """
    empacotado = getattr(sys, "_MEIPASS", None)
    if empacotado is not None:
        return Path(empacotado)
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _project_root()

# Hosts pelos quais a aplicação aceita ser alcançada (defesa D10).
ALLOWED_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEVCOCKPIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- servidor ---
    host: str = "127.0.0.1"
    port: int = 8765
    env: str = "development"

    # --- banco ---
    database_url: str = "sqlite:///./data/devcockpit.db"

    # --- log ---
    log_level: str = "INFO"
    log_file: Path = Path("./logs/devcockpit.log")
    log_format: str = "json"

    # --- arquivos de configuração ---
    roots_file: Path = Path("./configs/roots.yml")
    defaults_file: Path = Path("./configs/defaults.yml")

    # --- cache e polling ---
    cache_ttl_seconds: float = 5.0
    health_poll_interval: float = 30.0
    health_timeout: float = 2.0

    # --- timeouts de comando (segundos) ---
    timeout_git: float = 10.0
    timeout_docker_read: float = 15.0
    timeout_compose_up: float = 300.0
    timeout_compose_control: float = 120.0
    timeout_system_action: float = 10.0
    timeout_scan: float = 120.0

    # --- descoberta ---
    scan_max_depth: int = 3

    # --- jobs ---
    job_output_limit: int = 2 * 1024 * 1024
    job_retention: float = 3600.0

    # --- histórico e retenção ---
    #: Janela de "projeto recente" que decide quem o poller verifica (Q-02).
    #: Apesar do nome, não é retenção: é elegibilidade.
    health_history_days: int = 7
    #: Intervalo mínimo entre duas gravações iguais no histórico de health.
    #: Mudança de estado grava sempre; repetição grava de tempos em tempos.
    health_snapshot_interval: float = 300.0
    #: Por quanto tempo o histórico de health fica no banco.
    health_snapshot_retention_days: int = 14
    activity_retention_days: int = 90
    #: De quanto em quanto tempo a poda roda, dentro do laço do poller.
    retention_interval: float = 3600.0

    # --- Cockpit AI ---
    #: Desligado por padrão, e ligar é ato fora da interface: a partir daqui,
    #: conteúdo dos projetos passa a ser enviado ao provedor (defesa D-A1).
    ai_enabled: bool = False
    #: anthropic | openai | local | fake | none
    ai_provider: str = "none"
    ai_model: str = ""
    #: Nunca gravada em banco, nunca devolvida por rota (defesa D-A5).
    ai_api_key: str = ""
    #: Endereço do provedor. Configurável para proxy, gateway corporativo e
    #: para o servidor que a suíte usa no lugar da API real.
    ai_base_url: str = ""
    ai_timeout: float = 120.0
    ai_max_context_tokens: int = 12000
    ai_max_output_tokens: int = 2000
    #: Teto de tokens por dia. Zero desliga o teto — desaconselhado: custo
    #: invisível é o que um dia assusta.
    ai_daily_token_budget: int = 200_000

    # --- binários externos; vazio resolve pelo PATH ---
    git_bin: str = ""
    docker_bin: str = ""
    code_bin: str = ""

    version: str = Field(default="0.1.0")

    @field_validator("host")
    @classmethod
    def host_must_be_loopback(cls, value: str) -> str:
        """NFR-001: o bind é loopback por construção, não por configuração.

        Não existe flag para expor na rede. Quem quiser isso altera o código e
        assume o risco descrito em `docs/07-security-model.md`.
        """
        normalized = value.strip().strip("[]")
        if normalized == "localhost":
            return value
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError as exc:
            raise ValueError(
                f"DEVCOCKPIT_HOST inválido: {value!r}. Use 127.0.0.1, ::1 ou localhost."
            ) from exc
        if not address.is_loopback:
            raise ValueError(
                f"DEVCOCKPIT_HOST={value!r} não é loopback. O DevCockpit executa comandos "
                "na sua máquina e nunca deve escutar fora de 127.0.0.1. "
                "Ver docs/07-security-model.md (defesa D1)."
            )
        return value

    @property
    def self_origins(self) -> frozenset[str]:
        """Origens aceitas em requisições que alteram estado (defesa D5)."""
        return frozenset(
            f"http://{host}:{self.port}" for host in ("localhost", "127.0.0.1", "[::1]")
        )

    def resolve(self, relative: Path) -> Path:
        """Resolve um path de configuração relativo à raiz do projeto."""
        return relative if relative.is_absolute() else (PROJECT_ROOT / relative).resolve()


class RootsConfig:
    """Allowlist de diretórios raiz e regras de varredura (defesa D4).

    Carregado de arquivo. Nunca editável pela API — uma allowlist que o próprio
    cliente amplia não é uma allowlist (decisão D-10).
    """

    def __init__(
        self,
        allowed_roots: list[Path],
        scan_ignore: frozenset[str],
        scan_max_depth: int,
    ) -> None:
        self.allowed_roots = allowed_roots
        self.scan_ignore = scan_ignore
        self.scan_max_depth = scan_max_depth

    @classmethod
    def load(cls, path: Path, fallback_max_depth: int = 3) -> RootsConfig:
        if not path.exists():
            return cls(allowed_roots=[], scan_ignore=frozenset(), scan_max_depth=fallback_max_depth)

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        roots: list[Path] = []
        for raw in data.get("allowed_roots") or []:
            candidate = Path(str(raw)).expanduser()
            if candidate.is_absolute():
                roots.append(candidate.resolve())

        return cls(
            allowed_roots=roots,
            scan_ignore=frozenset(str(item) for item in data.get("scan_ignore") or []),
            scan_max_depth=int(data.get("scan_max_depth") or fallback_max_depth),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_roots_config() -> RootsConfig:
    settings = get_settings()
    return RootsConfig.load(
        settings.resolve(settings.roots_file),
        fallback_max_depth=settings.scan_max_depth,
    )
