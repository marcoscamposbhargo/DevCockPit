"""OSAdapter — toda diferença de sistema operacional vive aqui (ADR-007).

O adapter **monta e devolve `CommandSpec`**; quem executa é o `CommandRunner`.
Assim a auditoria e o timeout continuam inescapáveis, e o teste de cada
plataforma é uma asserção sobre argv — sem abrir nada de verdade.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol

from app.adapters.system import focus
from app.core.errors import ToolNotFound
from app.runner.command_spec import CommandSpec

DEFAULT_TIMEOUT_S = 10.0


class OSAdapter(Protocol):
    name: str

    def open_in_editor(self, path: Path) -> CommandSpec: ...
    def open_folder(self, path: Path) -> CommandSpec: ...
    def open_terminal(self, path: Path) -> CommandSpec: ...
    def tool_available(self, tool: str) -> bool: ...
    def focus_editor_window(self, path: Path) -> None: ...


class BaseOSAdapter:
    name = "base"

    def __init__(self, code_bin: str = "", timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.code_bin = code_bin
        self.timeout_s = timeout_s

    def tool_available(self, tool: str) -> bool:
        return shutil.which(tool) is not None

    def focus_editor_window(self, path: Path) -> None:
        """Sem efeito por padrão. Só o Windows precisa disto (D-46)."""
        return None

    def _editor(self) -> str:
        return self.code_bin or "code"

    def _require(self, tool: str, instrucao: str) -> str:
        if not self.tool_available(tool):
            raise ToolNotFound(f"'{tool}' não está no PATH. {instrucao}")
        return tool

    def _spec(self, argv: list[str], cwd: Path, label: str) -> CommandSpec:
        return CommandSpec(argv=argv, cwd=cwd, timeout_s=self.timeout_s, label=label)


class WindowsOSAdapter(BaseOSAdapter):
    """Plataforma primária (ADR-007)."""

    name = "windows"

    def open_in_editor(self, path: Path) -> CommandSpec:
        # No Windows o VS Code é um `.cmd`, não um binário: `shutil.which`
        # resolve o caminho completo, e sem isso a execução sem shell falha.
        editor = self._editor()
        resolved = shutil.which(editor)
        if resolved is None:
            raise ToolNotFound(
                f"'{editor}' não está no PATH. No VS Code, use "
                "'Shell Command: Install code command in PATH'."
            )
        return self._spec([resolved, str(path)], path, "system.vscode")

    def focus_editor_window(self, path: Path) -> None:
        """D-46 — `code` reaproveita a janela aberta e devolve 0 sem mostrá-la.

        O Windows recusa `SetForegroundWindow` vindo de processo sem foco, então
        a abertura era invisível para quem clicou. Best-effort: não levanta.
        """
        focus.focus_editor_window(path.name)

    def open_folder(self, path: Path) -> CommandSpec:
        # `explorer` devolve código de saída 1 mesmo quando funciona; quem
        # chama precisa saber disso (ver SystemActionService).
        return self._spec(["explorer.exe", str(path)], path, "system.folder")

    def open_terminal(self, path: Path) -> CommandSpec:
        """Windows Terminal quando existe; PowerShell como reserva.

        `wt.exe` não vem em instalações antigas do Windows 10, então a detecção
        é em tempo de execução, não uma suposição.
        """
        if self.tool_available("wt.exe"):
            return self._spec(
                ["wt.exe", "-d", str(path)],
                path,
                "system.terminal",
            )

        return self._spec(
            [
                "powershell.exe",
                "-NoExit",
                "-Command",
                # Argumento único e literal: não há shell interpretando isto,
                # e `path` já foi validado contra a allowlist de roots.
                f"Set-Location -LiteralPath '{path}'",
            ],
            path,
            "system.terminal",
        )


class MacOSAdapter(BaseOSAdapter):
    name = "macos"

    def open_in_editor(self, path: Path) -> CommandSpec:
        editor = self._require(self._editor(), "Instale o comando 'code' pelo VS Code.")
        return self._spec([editor, str(path)], path, "system.vscode")

    def open_folder(self, path: Path) -> CommandSpec:
        return self._spec(["open", str(path)], path, "system.folder")

    def open_terminal(self, path: Path) -> CommandSpec:
        return self._spec(["open", "-a", "Terminal", str(path)], path, "system.terminal")


class LinuxOSAdapter(BaseOSAdapter):
    name = "linux"

    #: Emuladores procurados, em ordem. O primeiro encontrado vence.
    TERMINALS: tuple[tuple[str, list[str]], ...] = (
        ("gnome-terminal", ["--working-directory"]),
        ("konsole", ["--workdir"]),
        ("xfce4-terminal", ["--working-directory"]),
        ("alacritty", ["--working-directory"]),
        ("kitty", ["--directory"]),
        ("x-terminal-emulator", []),
    )

    def open_in_editor(self, path: Path) -> CommandSpec:
        editor = self._require(self._editor(), "Instale o comando 'code' pelo VS Code.")
        return self._spec([editor, str(path)], path, "system.vscode")

    def open_folder(self, path: Path) -> CommandSpec:
        tool = self._require("xdg-open", "Instale xdg-utils.")
        return self._spec([tool, str(path)], path, "system.folder")

    def open_terminal(self, path: Path) -> CommandSpec:
        for terminal, flags in self.TERMINALS:
            if self.tool_available(terminal):
                argv = [terminal, *flags, str(path)] if flags else [terminal]
                return self._spec(argv, path, "system.terminal")

        raise ToolNotFound(
            "Nenhum emulador de terminal conhecido foi encontrado. "
            f"Procurados: {', '.join(name for name, _ in self.TERMINALS)}."
        )


def build_os_adapter(
    code_bin: str = "",
    timeout_s: float = DEFAULT_TIMEOUT_S,
    platform: str | None = None,
) -> BaseOSAdapter:
    resolved = platform or os.name

    if resolved in ("nt", "windows"):
        return WindowsOSAdapter(code_bin=code_bin, timeout_s=timeout_s)
    if resolved in ("darwin", "macos"):
        return MacOSAdapter(code_bin=code_bin, timeout_s=timeout_s)
    return LinuxOSAdapter(code_bin=code_bin, timeout_s=timeout_s)
