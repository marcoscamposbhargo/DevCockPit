"""Processo de vida longa: o servidor de desenvolvimento de um projeto.

Um servidor de desenvolvimento **não é um job**. Job é "faça isto e termine": o
`JobManager` aplica timeout, cancela no encerramento da aplicação e descarta o
resultado depois da retenção. Aplicar qualquer uma dessas três coisas a um
`npm run dev` mata o servidor que a pessoa acabou de subir.

Então este módulo existe ao lado do `JobManager`, não dentro dele:

- **sem timeout** — o processo termina quando alguém manda, ou quando quebra;
- **sobrevive ao DevCockpit** — grupo de processo próprio, console próprio.
  Reiniciar o painel não pode derrubar o servidor de ninguém;
- **saída vai para arquivo**, não para um buffer em memória. Um servidor
  ligado o dia inteiro estoura qualquer buffer, e o log precisa continuar
  legível depois de reiniciar o painel.

Sobreviver ao painel só é aceitável porque a descoberta de porta existe: ao
voltar, o DevCockpit reencontra o processo pelo PID gravado e pela porta em
escuta. Sem isso, sobreviver viraria órfão — que é justamente o que o
`JobManager` foi feito para nunca deixar.

Mora em `app/runner/` porque é aqui que `subprocess` pode ser importado
(ADR-003).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # noqa: S404 - ponto único de execução, ver ADR-003
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import redact_argv
from app.runner.process import kill_tree

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class BackgroundStart:
    pid: int
    log_file: str


def _resolve_program(program: str, cwd: Path) -> str:
    """Descobre o caminho real do executável antes de chamá-lo.

    Dois casos, e os dois já morderam:

    **Nome simples** (`npm`, `node`, `python`). No Windows, `npm`, `pnpm`,
    `yarn` e companhia são arquivos `.cmd`. Sem shell — e aqui nunca há shell —
    `CreateProcess` recebe "npm", não encontra arquivo com esse nome exato e
    devolve "O sistema não pode encontrar o arquivo especificado". O programa
    está instalado; o que falta é a extensão, que só o `PATHEXT` conhece.
    `shutil.which` resolve.

    **Caminho relativo** (`.venv/Scripts/python.exe`). É como um manifesto
    aponta o interpretador do próprio projeto, e a única leitura que faz
    sentido é "relativo ao projeto". Mas `CreateProcess` resolve caminho
    relativo contra o diretório do **processo que chama**, não contra o `cwd`
    que se passa ao filho — então o painel acabava executando outro Python, ou
    nenhum. O sintoma foi um `ModuleNotFoundError` de uma biblioteca que estava
    instalada no `.venv` apontado.

    Não encontrou, devolve o original: quem chama trata o `FileNotFound` com a
    mensagem certa, e inventar um caminho aqui só esconderia a causa.
    """
    if "/" in program or "\\" in program:
        candidato = (cwd / program).resolve()
        if candidato.is_file():
            return str(candidato)
        return program

    return shutil.which(program) or program


def start_background(
    argv: list[str],
    cwd: Path,
    log_file: Path,
    env_extra: dict[str, str] | None = None,
) -> BackgroundStart:
    """Sobe o processo desligado do nosso e aponta a saída para `log_file`.

    Levanta `OSError` quando o programa não existe ou não pôde ser iniciado —
    quem chama traduz isso na mensagem que a tela mostra.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    argv = [_resolve_program(argv[0], cwd), *argv[1:]]

    env = {**os.environ, **(env_extra or {})}
    # Servidor de desenvolvimento que detecta terminal costuma ligar cores ANSI
    # e barra de progresso com `\r`. Num arquivo isso vira lixo ilegível.
    env.setdefault("NO_COLOR", "1")
    env.setdefault("FORCE_COLOR", "0")
    env.setdefault("CI", "1")

    creation_flags = 0
    start_new_session = False
    if _IS_WINDOWS:
        # `CREATE_NEW_PROCESS_GROUP` é o que permite encerrar a árvore inteira
        # depois — um `npm run dev` vira node, esbuild e mais um punhado de
        # filhos, e matar só o pai deixa a porta ocupada por órfão.
        #
        # `CREATE_NO_WINDOW`, e não `DETACHED_PROCESS`: os dois escondem a
        # janela, mas o segundo custava o log. `npm` no Windows é um `.cmd`, e
        # `CreateProcess` roda `.cmd` por dentro do `cmd.exe`. Sem console
        # nenhum, o `cmd.exe` alocava um por conta própria e a saída ia para
        # esse console novo em vez do arquivo — o servidor subia certo e o log
        # aparecia vazio, que é a pior combinação para depurar uma queda.
        #
        # Nenhum dos dois amarra o filho ao nosso tempo de vida: o Windows só
        # encerra filho junto com o pai via Job Object, que não é o caso aqui.
        # Reiniciar o painel continua não derrubando o servidor.
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        start_new_session = True

    # `a` e não `w`: reiniciar o servidor não pode apagar o log do que acabou
    # de quebrar, que é exatamente o momento em que alguém vai lê-lo.
    handle = log_file.open("a", encoding="utf-8", errors="replace")
    try:
        processo = subprocess.Popen(  # noqa: S603 - argv validado em run_plan
            argv,
            cwd=str(cwd),
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=False,
            env=env,
            creationflags=creation_flags,
            start_new_session=start_new_session,
        )
    finally:
        # O filho herdou o descritor; o nosso já não serve para nada.
        handle.close()

    logger.info(
        "processo de longa duração iniciado",
        extra={
            "extra_fields": {
                "argv": redact_argv(argv),
                "pid": processo.pid,
                "cwd": str(cwd),
            }
        },
    )
    return BackgroundStart(pid=processo.pid, log_file=str(log_file))


def is_alive(pid: int) -> bool:
    """Diz se o PID ainda existe.

    Não confunde "não existe" com "não é meu": um PID de outro usuário responde
    que existe, e é essa a pergunta. Reciclagem de PID é um risco teórico aqui
    — quem chama confere também a linha de comando quando isso importa.
    """
    if pid <= 0:
        return False

    if _IS_WINDOWS:
        try:
            import psutil

            return psutil.pid_exists(pid)
        except Exception:  # noqa: BLE001 - ausência de psutil não pode quebrar o painel
            return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def stop_background(pid: int) -> bool:
    """Encerra o processo e a árvore dele. Já morto conta como sucesso."""
    if not is_alive(pid):
        return True
    return kill_tree(pid)


def tail_log(log_file: Path, lines: int = 200, max_bytes: int = 512 * 1024) -> list[str]:
    """Últimas linhas do log, lendo só o fim do arquivo.

    Ler um log de servidor ligado há oito horas por inteiro para mostrar as
    últimas 200 linhas seria trabalho por nada, e trava a resposta enquanto o
    disco entrega megabytes.
    """
    if not log_file.is_file():
        return []

    try:
        tamanho = log_file.stat().st_size
        with log_file.open("rb") as arquivo:
            if tamanho > max_bytes:
                arquivo.seek(tamanho - max_bytes)
                # O `seek` provavelmente caiu no meio de uma linha (e talvez no
                # meio de um caractere multibyte). A primeira linha é descartada.
                arquivo.readline()
            conteudo = arquivo.read()
    except OSError:
        return []

    texto = conteudo.decode("utf-8", errors="replace")
    todas = [linha.rstrip("\r") for linha in texto.splitlines()]
    return todas[-lines:]
