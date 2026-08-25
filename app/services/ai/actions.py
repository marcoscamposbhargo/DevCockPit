"""O registro de ações que a IA pode **propor** — e nada além disto.

Este arquivo é o encontro do Cockpit AI com o ADR-003. A regra do painel é que
nenhum comando vem do cliente; a regra da IA (defesa D-A3) é mais forte ainda:
**ela não ganha capacidade nova nenhuma.**

O que existe aqui não é um executor. É um catálogo fechado de coisas que o
painel **já faz por botão**, com um nome estável para cada uma. O modelo
escolhe um nome desta lista; o servidor confere se o nome existe; a tela mostra
a proposta e a pessoa confirma. A execução acontece pela mesma rota que o botão
usa — a IA não abre caminho novo, ela aponta para um caminho que já estava lá.

Nome fora desta lista nunca vira ação: vira recusa registrada na auditoria, que
é o sinal de modelo alucinando.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Classe(StrEnum):
    """Quanto uma ação pode custar se estiver errada.

    Espelha a classificação de `docs/07-security-model.md`. A consequência
    prática é uma só: o que não é `READ` precisa de confirmação humana.
    """

    READ = "READ"
    SAFE_WRITE = "SAFE_WRITE"
    SENSITIVE_WRITE = "SENSITIVE_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass(frozen=True)
class Acao:
    key: str
    label: str
    #: O que a tela mostra antes de perguntar "confirma?". Escrito na segunda
    #: pessoa e no futuro, porque é uma promessa do que vai acontecer.
    describe: str
    classe: Classe
    #: Precisa saber de qual projeto se fala. Sem projeto resolvido, a proposta
    #: não é oferecida — é melhor não propor do que propor no projeto errado.
    needs_project: bool = True
    #: Método e caminho da rota que a tela chama depois do "Confirmar". É a
    #: mesma rota do botão; `{project_id}` é substituído pelo cliente.
    method: str = "POST"
    path: str = ""

    @property
    def needs_confirmation(self) -> bool:
        return self.classe is not Classe.READ


#: A lista fechada. Cada entrada aponta para uma rota que já existia antes da
#: IA — se uma linha daqui não tiver rota correspondente, é bug, não feature.
ACOES: tuple[Acao, ...] = (
    Acao(
        key="environment.up",
        label="Ligar o ambiente",
        describe="Vou subir o ambiente de {projeto}: containers do Compose e, "
        "depois que as dependências responderem, a aplicação.",
        classe=Classe.SENSITIVE_WRITE,
        path="/api/projects/{project_id}/environment/up",
    ),
    Acao(
        key="environment.down",
        label="Desligar o ambiente",
        describe="Vou parar o ambiente de {projeto}. Containers do Compose "
        "continuam de pé; só a aplicação para.",
        classe=Classe.SENSITIVE_WRITE,
        path="/api/projects/{project_id}/environment/down",
    ),
    Acao(
        key="server.start",
        label="Subir o servidor",
        describe="Vou subir só o servidor de desenvolvimento de {projeto}, sem "
        "mexer em container.",
        classe=Classe.SENSITIVE_WRITE,
        path="/api/projects/{project_id}/server/start",
    ),
    Acao(
        key="server.stop",
        label="Parar o servidor",
        describe="Vou parar o servidor de desenvolvimento de {projeto}.",
        classe=Classe.SENSITIVE_WRITE,
        path="/api/projects/{project_id}/server/stop",
    ),
    Acao(
        key="server.logs",
        label="Ver o log do servidor",
        describe="Mostro as últimas linhas que o servidor de {projeto} escreveu.",
        classe=Classe.READ,
        method="GET",
        path="/api/projects/{project_id}/server/logs",
    ),
    Acao(
        key="server.status",
        label="Ver o estado do servidor",
        describe="Mostro se o servidor de {projeto} está de pé, com que comando "
        "e desde quando.",
        classe=Classe.READ,
        method="GET",
        path="/api/projects/{project_id}/server",
    ),
    Acao(
        key="preflight.check",
        label="Conferir as portas antes de ligar",
        describe="Confiro se as portas que {projeto} declara estão livres, e "
        "quem está nelas.",
        classe=Classe.READ,
        method="GET",
        path="/api/projects/{project_id}/environment/preflight",
    ),
    Acao(
        key="docker.ps",
        label="Ver os containers",
        describe="Listo os containers de {projeto} e o estado de cada um.",
        classe=Classe.READ,
        method="GET",
        path="/api/projects/{project_id}/docker/status",
    ),
    Acao(
        key="git.status",
        label="Ver o estado do Git",
        describe="Mostro a branch e os arquivos sem commit de {projeto}.",
        classe=Classe.READ,
        method="GET",
        path="/api/projects/{project_id}/git/status",
    ),
    Acao(
        key="ports.map",
        label="Ver o mapa de portas",
        describe="Mostro quem está ocupando cada porta na máquina agora.",
        classe=Classe.READ,
        needs_project=False,
        method="GET",
        path="/api/services/ports",
    ),
    Acao(
        key="open.vscode",
        label="Abrir no VS Code",
        describe="Abro {projeto} no VS Code.",
        classe=Classe.SAFE_WRITE,
        path="/api/projects/{project_id}/open/vscode",
    ),
    Acao(
        key="open.terminal",
        label="Abrir o terminal",
        describe="Abro um terminal na pasta de {projeto}.",
        classe=Classe.SAFE_WRITE,
        path="/api/projects/{project_id}/open/terminal",
    ),
)

POR_CHAVE: dict[str, Acao] = {acao.key: acao for acao in ACOES}


def catalogo() -> str:
    """O registro em texto, para entrar no prompt do orquestrador.

    Uma linha por ação, nome primeiro. Formato enxuto de propósito: num
    provedor local cada token do prompt é tempo de leitura, e este bloco entra
    em toda pergunta.
    """
    return "\n".join(f"{acao.key} - {acao.label.lower()}" for acao in ACOES)
