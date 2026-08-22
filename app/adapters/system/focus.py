"""Trazer a janela do editor para frente no Windows (D-46).

Por que isto existe: `code <path>` reaproveita a janela já aberta, devolve
código de saída 0 e o log registra SUCCESS — mas o Windows não deixa um
processo que não tem foco (o uvicorn) chamar `SetForegroundWindow`. Para quem
clicou, nada acontece.

O contorno documentado é anexar a fila de entrada da nossa thread à da thread
que está em primeiro plano: com as filas anexadas, o sistema passa a permitir
a troca de foco. Depois as filas são desanexadas.

Tudo aqui é **best-effort**: o comando já rodou e o projeto já foi aberto, então
qualquer falha é registrada em debug e engolida. Nada nesta camada pode
transformar uma abertura bem-sucedida em erro para o usuário.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time

if sys.platform == "win32":  # `ctypes.wintypes` não existe fora do Windows
    from ctypes import wintypes
else:  # pragma: no cover - o adapter só chama este módulo no Windows
    wintypes = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

#: Sufixo do título de toda janela do VS Code, em qualquer idioma da interface.
EDITOR_WINDOW_SUFFIX = "visual studio code"

#: Por quanto tempo procurar a janela. Abrir uma pasta nova leva alguns
#: segundos até o título refletir o projeto.
SEARCH_TIMEOUT_S = 5.0
SEARCH_INTERVAL_S = 0.25

SW_RESTORE = 9


def _user32() -> ctypes.WinDLL:  # type: ignore[name-defined]
    return ctypes.WinDLL("user32", use_last_error=True)


def _kernel32() -> ctypes.WinDLL:  # type: ignore[name-defined]
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _visible_window_titles(user32) -> list[tuple[int, str]]:  # type: ignore[no-untyped-def]
    """Título de cada janela de topo visível, com o respectivo handle."""
    encontrados: list[tuple[int, str]] = []

    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):  # type: ignore[no-untyped-def]
        if not user32.IsWindowVisible(hwnd):
            return True
        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
        encontrados.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(proto(_callback), 0)
    return encontrados


def _find_editor_window(user32, folder_name: str) -> int | None:  # type: ignore[no-untyped-def]
    """Janela do VS Code cujo título carrega o nome da pasta do projeto.

    Casar pelo nome da pasta é o que impede focar o projeto errado quando há
    várias janelas do editor abertas — que é o caso normal de quem usa isto.
    """
    alvo = folder_name.lower()
    for hwnd, titulo in _visible_window_titles(user32):
        minusculo = titulo.lower()
        if minusculo.endswith(EDITOR_WINDOW_SUFFIX) and alvo in minusculo:
            return hwnd
    return None


def _raise_window(user32, kernel32, hwnd: int) -> None:  # type: ignore[no-untyped-def]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    primeiro_plano = user32.GetForegroundWindow()
    thread_alvo = user32.GetWindowThreadProcessId(primeiro_plano, None)
    thread_nossa = kernel32.GetCurrentThreadId()

    anexou = False
    if thread_alvo and thread_alvo != thread_nossa:
        anexou = bool(user32.AttachThreadInput(thread_nossa, thread_alvo, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if anexou:
            user32.AttachThreadInput(thread_nossa, thread_alvo, False)


def _focus_now(folder_name: str) -> bool:
    user32 = _user32()
    kernel32 = _kernel32()

    limite = time.monotonic() + SEARCH_TIMEOUT_S
    while time.monotonic() < limite:
        hwnd = _find_editor_window(user32, folder_name)
        if hwnd is not None:
            _raise_window(user32, kernel32, hwnd)
            return True
        time.sleep(SEARCH_INTERVAL_S)

    logger.debug("janela do editor não encontrada para %r", folder_name)
    return False


def focus_editor_window(folder_name: str, blocking: bool = False) -> None:
    """Traz para frente a janela do VS Code aberta na pasta `folder_name`.

    Roda numa thread daemon por padrão: a resposta HTTP não deve esperar até
    cinco segundos por uma cortesia visual. Passe `blocking=True` no teste.
    """
    if sys.platform != "win32":
        return

    if blocking:
        _rodar_protegido(folder_name)
        return

    threading.Thread(
        target=_rodar_protegido,
        args=(folder_name,),
        name="focus-editor",
        daemon=True,
    ).start()


def _rodar_protegido(folder_name: str) -> None:
    try:
        _focus_now(folder_name)
    except Exception:  # best-effort: nunca derruba a ação que já deu certo
        logger.debug("falha ao focar a janela do editor", exc_info=True)
