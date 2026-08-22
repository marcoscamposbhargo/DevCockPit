"""GitAdapter — monta argv e parseia saída do `git` CLI.

Formato estável obrigatório: `--porcelain=v2` e `--format` com separador
próprio. Saída humana do Git muda entre versões e locales; parsear isso é a
origem clássica do bug sutil (docs/10-testing-strategy.md).

Este adapter não executa nada por conta própria — devolve `CommandSpec` para o
`CommandRunner`, que é quem aplica timeout e auditoria (ADR-003).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.adapters.git.models import ChangedFile, Commit, GitStatus, Remote
from app.core.paths import normalize_for_comparison
from app.runner.command_runner import CommandRunner
from app.runner.command_spec import CommandSpec

# Separadores improváveis em conteúdo real, para não colidir com mensagem de
# commit que contenha vírgula, pipe ou tabulação.
FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"

LOG_FORMAT = FIELD_SEP.join(["%h", "%an", "%aI", "%s"]) + RECORD_SEP

_XY_TO_CHANGE = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "modified",
    "U": "conflicted",
}


class GitAdapter:
    def __init__(self, runner: CommandRunner, git_bin: str = "", timeout_s: float = 10.0) -> None:
        self.runner = runner
        self.git_bin = git_bin or "git"
        self.timeout_s = timeout_s

    # --- construção de comandos ---

    def _spec(self, project_dir: Path, args: list[str], label: str) -> CommandSpec:
        return CommandSpec(
            argv=[self.git_bin, *args],
            cwd=project_dir,
            timeout_s=self.timeout_s,
            label=label,
            # Desliga toda leitura de configuração global do usuário e qualquer
            # prompt: um `git` que pede senha travaria até o timeout.
            env_extra={"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
        )

    # --- operações (todas somente leitura — FR-038) ---

    def locate_repo(self, project_dir: Path) -> tuple[Path | None, bool]:
        """Descobre a raiz do repositório e se ela é o próprio diretório.

        `git rev-parse --is-inside-work-tree` **sobe a árvore de diretórios**.
        Numa máquina onde exista um repositório em `C:/Users/User` — algo mais
        comum do que parece —, todo projeto abaixo dele responderia "sim, sou
        um repositório" e exibiria a branch e os arquivos sujos do repositório
        pai. Trinta projetos mostrariam o mesmo estado, todo ele errado.

        Por isso a pergunta certa não é "estou dentro de um repositório?" e sim
        "a raiz do repositório é este diretório?".

        Devolve `(raiz, é_a_raiz)`. Raiz `None` significa que não há
        repositório algum acima.
        """
        result = self.runner.run(
            self._spec(project_dir, ["rev-parse", "--show-toplevel"], "git.toplevel")
        )
        if not result.ok:
            return None, False

        raw = result.stdout.strip()
        if not raw:
            return None, False

        toplevel = Path(raw).resolve(strict=False)
        return toplevel, is_same_dir(toplevel, project_dir.resolve(strict=False))

    def is_repo(self, project_dir: Path) -> bool:
        """True apenas quando o diretório é a **raiz** de um repositório."""
        _, is_root = self.locate_repo(project_dir)
        return is_root

    def status(self, project_dir: Path, file_limit: int = 50) -> GitStatus:
        repo_root, is_root = self.locate_repo(project_dir)

        if not is_root:
            return GitStatus(
                is_repo=False,
                repo_root=repo_root.as_posix() if repo_root else None,
                inside_other_repo=repo_root is not None,
            )

        result = self.runner.run(
            self._spec(
                project_dir,
                ["status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
                "git.status",
            )
        )
        if not result.ok:
            return GitStatus(is_repo=False)

        status = parse_status(result.stdout, file_limit=file_limit)
        status.repo_root = repo_root.as_posix() if repo_root else None
        return status

    def log(self, project_dir: Path, limit: int = 20) -> list[Commit]:
        safe_limit = max(1, min(int(limit), 200))
        result = self.runner.run(
            self._spec(
                project_dir,
                ["log", f"-n{safe_limit}", f"--format={LOG_FORMAT}"],
                "git.log",
            )
        )
        if not result.ok:
            return []
        return parse_log(result.stdout)

    def branches(self, project_dir: Path) -> list[str]:
        result = self.runner.run(
            self._spec(
                project_dir,
                ["for-each-ref", "--format=%(refname:short)", "refs/heads/"],
                "git.branches",
            )
        )
        if not result.ok:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def remotes(self, project_dir: Path) -> list[Remote]:
        result = self.runner.run(self._spec(project_dir, ["remote", "-v"], "git.remotes"))
        if not result.ok:
            return []
        return parse_remotes(result.stdout)


def is_same_dir(left: Path, right: Path) -> bool:
    """Compara diretórios respeitando a caixa da plataforma."""
    return normalize_for_comparison(left) == normalize_for_comparison(right)


# --- parsers (funções puras, testadas com fixtures de saída real) ----------


def parse_status(output: str, file_limit: int = 50) -> GitStatus:
    """Interpreta `git status --porcelain=v2 --branch`.

    Formato (documentado e estável):
      `# branch.oid <sha>` · `# branch.head <nome|(detached)>`
      `# branch.ab +N -M`
      `1 <XY> ... <path>`        entrada comum
      `2 <XY> ... <path>\t<orig>` renomeada
      `u <XY> ... <path>`         conflito
      `? <path>`                  não rastreada
    """
    status = GitStatus(is_repo=True, counts={})
    counts = {
        "modified": 0,
        "added": 0,
        "deleted": 0,
        "renamed": 0,
        "untracked": 0,
        "staged": 0,
        "conflicted": 0,
    }
    files: list[ChangedFile] = []
    total = 0

    for line in output.splitlines():
        if not line:
            continue

        if line.startswith("# branch.oid "):
            sha = line.removeprefix("# branch.oid ").strip()
            status.head_sha = None if sha == "(initial)" else sha
            continue

        if line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ").strip()
            if head == "(detached)":
                status.detached = True
            else:
                status.current_branch = head
            continue

        if line.startswith("# branch.ab "):
            for token in line.removeprefix("# branch.ab ").split():
                if token.startswith("+"):
                    status.ahead = int(token[1:])
                elif token.startswith("-"):
                    status.behind = int(token[1:])
            continue

        if line.startswith("# "):
            continue

        total += 1
        entry = _parse_entry(line)
        if entry is None:
            total -= 1
            continue

        change, staged, path = entry
        counts[change] = counts.get(change, 0) + 1
        if staged:
            counts["staged"] += 1

        if len(files) < file_limit:
            files.append(ChangedFile(path=path, change=change, staged=staged))

    status.counts = counts
    status.files = files
    status.files_truncated = total > len(files)
    return status


def _parse_entry(line: str) -> tuple[str, bool, str] | None:
    kind, _, rest = line.partition(" ")

    if kind == "?":
        return "untracked", False, rest.strip()

    if kind == "u":
        parts = rest.split(" ", 9)
        return "conflicted", False, parts[-1].strip() if parts else rest.strip()

    if kind not in {"1", "2"}:
        return None

    parts = rest.split(" ")
    if len(parts) < 2:
        return None

    xy = parts[0]
    staged = xy[0] != "."
    marker = xy[0] if staged else xy[1]
    change = _XY_TO_CHANGE.get(marker, "modified")

    if kind == "1":
        path = " ".join(parts[7:]) if len(parts) > 7 else parts[-1]
    else:  # renomeada: `<path>\t<original>`
        tail = " ".join(parts[8:]) if len(parts) > 8 else parts[-1]
        path = tail.split("\t")[0]
        change = "renamed"

    return change, staged, path.strip()


def parse_log(output: str) -> list[Commit]:
    commits: list[Commit] = []

    for record in output.split(RECORD_SEP):
        cleaned = record.strip("\n\r")
        if not cleaned:
            continue

        fields = cleaned.split(FIELD_SEP)
        if len(fields) < 4:
            continue

        sha, author, iso_date, subject = fields[0], fields[1], fields[2], fields[3]
        commits.append(
            Commit(
                sha=sha.strip(),
                author=author.strip(),
                date=_parse_iso(iso_date.strip()),
                subject=subject.strip(),
            )
        )

    return commits


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_remotes(output: str) -> list[Remote]:
    seen: dict[str, str] = {}

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            seen.setdefault(parts[0], parts[1])

    return [Remote(name=name, url=url) for name, url in seen.items()]
