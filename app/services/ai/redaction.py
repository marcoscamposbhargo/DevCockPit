"""O que nunca sai da máquina.

Até a Fase 2, o DevCockpit não fazia uma requisição de saída. Falar com um
provedor muda a natureza do produto: passa a existir dado do usuário
trafegando. Este módulo é a defesa D-A2, e ele age **antes** de qualquer coisa
virar mensagem.

Duas camadas, porque uma só não basta:

1. **arquivo que nunca é lido** — `.env`, chave privada, credencial. Não
   adianta redigir o conteúdo de um arquivo que não deveria ter sido aberto;
2. **linha redigida** — segredo aparece dentro de código, de log de container e
   de exemplo em README. O valor sai; o nome da variável fica, porque é ele que
   dá sentido ao trecho.

A regra de ouro é a mesma do `redact_argv` que a auditoria já usa: preservar o
que explica, apagar o que autentica.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Arquivos que não são lidos em hipótese nenhuma. Comparação por nome e por
#: sufixo, sem depender de caminho.
NOMES_PROIBIDOS = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "credentials.json",
        "service-account.json",
        "id_rsa",
        "id_ed25519",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "secrets.yml",
        "secrets.yaml",
    }
)

SUFIXOS_PROIBIDOS = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")

#: Nome de variável que denuncia segredo. O valor à direita é substituído.
_ATRIBUICAO = re.compile(
    r"""(?ix)
    \b
    (?P<chave>[A-Z0-9_\-\.]*
        (?:SECRET|PASSWORD|PASSWD|TOKEN|API[_\-]?KEY|ACCESS[_\-]?KEY|
           PRIVATE[_\-]?KEY|CLIENT[_\-]?SECRET|AUTH|CREDENTIAL)
     [A-Z0-9_\-\.]*)
    \s*[:=]\s*
    (?P<valor>"[^"]*"|'[^']*'|[^\s,;#]+)
    """
)

#: Formatos que são segredo por si, apareçam onde aparecerem.
_FORMATOS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),          # OpenAI
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}"),      # Anthropic
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),      # GitHub
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),              # AWS
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),   # Slack
    re.compile(r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(
        r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
        re.S,
    ),
    #: URL com senha embutida (`postgres://user:senha@host`).
    re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):([^\s@/]+)@"),
)

MARCA = "[REDIGIDO]"


def arquivo_proibido(caminho: str | Path) -> bool:
    """Arquivo que nunca deve ser aberto para virar contexto."""
    p = Path(str(caminho))
    nome = p.name.lower()
    if nome in NOMES_PROIBIDOS:
        return True
    if nome.startswith(".env."):
        return True
    return any(nome.endswith(sufixo) for sufixo in SUFIXOS_PROIBIDOS)


def redigir(texto: str) -> str:
    """Apaga o que autentica e preserva o que explica."""
    if not texto:
        return texto

    def _atribuicao(m: re.Match) -> str:
        return f"{m.group('chave')}={MARCA}"

    resultado = _ATRIBUICAO.sub(_atribuicao, texto)

    for padrao in _FORMATOS:
        if padrao.groups == 2:
            # URL com credencial: preserva o esquema e o host, apaga a senha.
            resultado = padrao.sub(lambda m: f"{m.group(1)}:{MARCA}@", resultado)
        else:
            resultado = padrao.sub(MARCA, resultado)

    return resultado


def redigir_bloco(titulo: str, conteudo: str) -> str:
    """Bloco de contexto já rotulado e redigido.

    O rótulo serve a duas coisas: proveniência para quem lê a resposta, e o
    aviso ao modelo de que aquilo é **dado**, não instrução — a defesa contra
    README malicioso dentro de um dos projetos varridos (defesa D-A4).
    """
    return f"[{titulo}]\n{redigir(conteudo)}"
