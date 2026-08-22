"""Harness de validação da máquina de jobs (US-043).

Existe para que a Fase 3a seja depurada com um processo previsível, antes de
`docker compose` entrar em cena. Depurar subprocess assíncrono e Compose ao
mesmo tempo é o pior cenário: quando falha, não se sabe de qual dos dois veio
(ADR-006, decisão D-22).

Uso:
    python scripts/job_probe.py --lines 500 --delay 0.05
    python scripts/job_probe.py --lines 10 --exit-code 3
    python scripts/job_probe.py --lines 100 --ignore-term    # resiste a término
    python scripts/job_probe.py --spawn-children 2           # cria filhos

`--ignore-term` e `--spawn-children` são os modos que provam o encerramento de
árvore de processos: um filho que ignora o sinal precisa morrer de todo jeito,
e junto com os netos.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess  # noqa: S404 - script de teste, fora de app/
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Processo previsível para testar jobs.")
    parser.add_argument("--lines", type=int, default=10, help="quantas linhas emitir")
    parser.add_argument("--delay", type=float, default=0.1, help="segundos entre linhas")
    parser.add_argument("--exit-code", type=int, default=0, help="código de saída final")
    parser.add_argument("--stderr-every", type=int, default=0, help="emite em stderr a cada N")
    parser.add_argument(
        "--ignore-term",
        action="store_true",
        help="ignora SIGTERM/SIGINT; só morre por término forçado",
    )
    parser.add_argument(
        "--spawn-children",
        type=int,
        default=0,
        help="cria N filhos que dormem, para testar encerramento de árvore",
    )
    parser.add_argument("--child", action="store_true", help="uso interno: modo filho")
    return parser.parse_args()


def install_signal_traps() -> None:
    def refuse(signum: int, _frame: object) -> None:
        print(f"recebi sinal {signum} e vou ignorar", flush=True)

    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        handler = getattr(signal, name, None)
        if handler is not None:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(handler, refuse)


def spawn_children(count: int) -> list[subprocess.Popen]:
    children = []
    for _ in range(count):
        children.append(
            subprocess.Popen(  # noqa: S603
                [sys.executable, __file__, "--child", "--lines", "9999", "--delay", "1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
    return children


def main() -> int:
    args = parse_args()

    if args.ignore_term:
        install_signal_traps()

    children = spawn_children(args.spawn_children) if args.spawn_children else []
    if children:
        print(f"criei {len(children)} filho(s): {[c.pid for c in children]}", flush=True)

    print(f"job_probe iniciado pid={os.getpid()} linhas={args.lines}", flush=True)

    for index in range(1, args.lines + 1):
        target = sys.stderr if args.stderr_every and index % args.stderr_every == 0 else sys.stdout
        print(f"linha {index}/{args.lines}", file=target, flush=True)
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"job_probe terminou com codigo {args.exit_code}", flush=True)
    return args.exit_code


if __name__ == "__main__":
    sys.exit(main())
