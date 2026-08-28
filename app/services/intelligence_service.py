"""Health Score de projeto — Fase 4.

O que este serviço **não** faz: inventar número. Cada indicador aponta para
algo que o painel já mede, e indicador sem dado vira `None`, não zero. Zero é
uma afirmação ("está ruim"); ausência não é ("não sei"), e as duas viravam a
mesma barra vermelha em toda ferramenta que já fez isso.

Por isso o score agregado vem acompanhado de **quanto dele foi calculado**: um
projeto com dois indicadores medidos e nota 80 não é comparável a um com seis
medidos e a mesma nota, e a tela precisa poder dizer isso.

Nada aqui roda comando nem toca a rede. Leitura de disco é a mesma que a
detecção já faz — existência de arquivo e de diretório, sem abrir conteúdo
grande —, e o resto vem do banco e dos caches que o poller preencheu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.monorepo import SUBPROJETOS
from app.models.ai import AiMemory, AiSession, MemoryKind
from app.models.base import utcnow
from app.models.project import ActivityLog, ActivityStatus, Project
from app.models.task import AiTask, TaskStatus

#: Quanto tempo para trás conta como "recente". Duas semanas cobrem uma pausa
#: de fim de semana prolongado sem transformar projeto parado há um mês em
#: projeto ativo.
JANELA_DIAS = 14

#: Arquivos que sustentam a afirmação "este projeto está documentado". Nenhum
#: deles é lido: só a existência conta, porque avaliar qualidade de texto seria
#: exatamente o tipo de nota inventada que este módulo recusa.
DOCUMENTOS = ("README.md", "readme.md", "README.MD")


@dataclass(frozen=True)
class Indicador:
    """Uma dimensão do score.

    `nota` é `None` quando não houve dado para calcular. A tela mostra isso
    como "não medido", e o agregado o ignora em vez de contá-lo como zero.
    """

    chave: str
    rotulo: str
    nota: int | None
    #: Por que a nota é essa, em texto curto. É o que separa um número de um
    #: número com explicação — e sem isso ninguém sabe o que fazer a respeito.
    evidencia: str
    #: O que este projeto ganharia se o indicador subisse. Vazio quando já está
    #: no teto ou quando não há ação óbvia.
    sugestao: str = ""


@dataclass
class HealthScore:
    project_id: str
    indicadores: list[Indicador] = field(default_factory=list)

    @property
    def medidos(self) -> list[Indicador]:
        return [i for i in self.indicadores if i.nota is not None]

    @property
    def score(self) -> int | None:
        """Média dos indicadores **medidos**, ou `None` se nenhum foi.

        Média simples de propósito. Peso por indicador seria a primeira coisa a
        virar palpite: não há dado nesta máquina que diga que documentação vale
        o dobro de teste, e inventar o peso contaminaria o número inteiro.
        """
        medidos = self.medidos
        if not medidos:
            return None
        return round(sum(i.nota or 0 for i in medidos) / len(medidos))

    @property
    def cobertura(self) -> str:
        """Quanto do score foi de fato calculado, para a tela dizer junto."""
        return f"{len(self.medidos)} de {len(self.indicadores)}"


class IntelligenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def score(self, project: Project) -> HealthScore:
        pasta = Path(project.path)
        existe = pasta.is_dir()

        return HealthScore(
            project_id=project.id,
            indicadores=[
                self._documentacao(pasta, existe),
                self._testes(pasta, existe),
                self._ambiente(project),
                self._atividade(project),
                self._tarefas(project),
                self._divida(project),
            ],
        )

    # --- indicadores ---

    def _documentacao(self, pasta: Path, existe: bool) -> Indicador:
        if not existe:
            return Indicador(
                chave="documentacao",
                rotulo="Documentação",
                nota=None,
                evidencia="A pasta do projeto não foi encontrada.",
            )

        tem_readme = any((pasta / nome).is_file() for nome in DOCUMENTOS)
        tem_docs = (pasta / "docs").is_dir()
        tem_manifesto = (pasta / "devcockpit.yml").is_file()

        pontos = sum((tem_readme, tem_docs, tem_manifesto))
        faltando = [
            rotulo
            for rotulo, presente in (
                ("README", tem_readme),
                ("pasta docs/", tem_docs),
                ("devcockpit.yml", tem_manifesto),
            )
            if not presente
        ]

        return Indicador(
            chave="documentacao",
            rotulo="Documentação",
            nota=round(pontos / 3 * 100),
            evidencia=(
                "README, docs/ e devcockpit.yml presentes."
                if not faltando
                else "Falta: " + ", ".join(faltando) + "."
            ),
            sugestao=(
                ""
                if not faltando
                else "Um README explicando como subir o projeto é o que mais rende aqui."
                if not tem_readme
                else "O devcockpit.yml fixa comando e portas, e evita o painel adivinhar."
                if not tem_manifesto
                else ""
            ),
        )

    def _testes(self, pasta: Path, existe: bool) -> Indicador:
        if not existe:
            return Indicador(
                chave="testes",
                rotulo="Testes",
                nota=None,
                evidencia="A pasta do projeto não foi encontrada.",
            )

        # A raiz **e** as subpastas de monorepo. Olhar só a raiz daria "0 testes"
        # para um projeto com `backend/tests` cheio — e essa é exatamente a
        # forma de defeito que o painel já produziu três vezes: correção que
        # para na raiz. Zero aqui é afirmação forte, e afirmação forte errada é
        # pior que silêncio.
        candidatas: list[str] = []
        for base in ("", *SUBPROJETOS):
            raiz = pasta / base if base else pasta
            if not raiz.is_dir():
                continue
            for nome in ("tests", "test", "spec", "__tests__"):
                if (raiz / nome).is_dir():
                    candidatas.append(f"{base}/{nome}" if base else nome)

        pastas = candidatas
        if not pastas:
            return Indicador(
                chave="testes",
                rotulo="Testes",
                nota=0,
                evidencia="Nenhuma pasta de teste na raiz nem nas subpastas de projeto.",
                sugestao="Um teste que falhe pelo bug de ontem já paga a pasta.",
            )

        arquivos = 0
        for nome in pastas:
            # Dois níveis: contar recursivamente numa árvore com `node_modules`
            # dentro custaria caro e a resposta não mudaria.
            arquivos += sum(1 for _ in (pasta / nome).glob("*test*"))
            arquivos += sum(1 for _ in (pasta / nome).glob("*/*test*"))

        return Indicador(
            chave="testes",
            rotulo="Testes",
            nota=100 if arquivos else 50,
            evidencia=(
                f"{arquivos} arquivo(s) de teste em {', '.join(pastas)}/."
                if arquivos
                else f"Pasta {pastas[0]}/ existe, mas sem arquivo de teste dentro."
            ),
            sugestao="" if arquivos else "A pasta está lá; falta o primeiro teste.",
        )

    def _ambiente(self, project: Project) -> Indicador:
        """Sobe pelo painel? A prova é o histórico de ações, não o palpite."""
        desde = utcnow() - timedelta(days=JANELA_DIAS)
        linhas = list(
            self.session.execute(
                select(ActivityLog.status, func.count())
                .where(
                    ActivityLog.project_id == project.id,
                    ActivityLog.action.in_(
                        ("environment.up", "server.start", "environment.down", "server.stop")
                    ),
                    ActivityLog.created_at >= desde,
                )
                .group_by(ActivityLog.status)
            )
        )

        total = sum(quantidade for _, quantidade in linhas)
        if not total:
            return Indicador(
                chave="ambiente",
                rotulo="Ambiente",
                nota=None,
                evidencia=f"Nada foi ligado ou desligado pelo painel em {JANELA_DIAS} dias.",
                sugestao="Subir uma vez pelo painel é o que dá material para medir.",
            )

        sucessos = sum(q for status, q in linhas if status == ActivityStatus.SUCCESS.value)
        return Indicador(
            chave="ambiente",
            rotulo="Ambiente",
            nota=round(sucessos / total * 100),
            evidencia=f"{sucessos} de {total} operação(ões) de ambiente concluíram.",
            sugestao=(
                ""
                if sucessos == total
                else "A aba Activity mostra o que falhou, com o motivo de cada uma."
            ),
        )

    def _atividade(self, project: Project) -> Indicador:
        desde = utcnow() - timedelta(days=JANELA_DIAS)
        sessoes = self.session.execute(
            select(func.count())
            .select_from(AiSession)
            .where(AiSession.project_id == project.id, AiSession.started_at >= desde)
        ).scalar_one()

        if not sessoes:
            ultima = self.session.execute(
                select(func.max(AiSession.started_at)).where(AiSession.project_id == project.id)
            ).scalar_one()
            if ultima is None:
                return Indicador(
                    chave="atividade",
                    rotulo="Atividade",
                    nota=None,
                    evidencia="Nenhuma sessão de trabalho registrada neste projeto.",
                    sugestao="Abrir uma sessão ao começar dá ao painel o que registrar.",
                )
            dias = (utcnow() - ultima).days
            return Indicador(
                chave="atividade",
                rotulo="Atividade",
                nota=0,
                evidencia=f"Última sessão há {dias} dia(s).",
            )

        # Três sessões em duas semanas já é ritmo de projeto vivo; acima disso o
        # indicador satura em vez de premiar quem abre sessão à toa.
        return Indicador(
            chave="atividade",
            rotulo="Atividade",
            nota=min(100, round(sessoes / 3 * 100)),
            evidencia=f"{sessoes} sessão(ões) nos últimos {JANELA_DIAS} dias.",
        )

    def _tarefas(self, project: Project) -> Indicador:
        linhas = list(
            self.session.execute(
                select(AiTask.status, func.count())
                .where(AiTask.project_id == project.id)
                .group_by(AiTask.status)
            )
        )
        total = sum(q for _, q in linhas)
        if not total:
            return Indicador(
                chave="tarefas",
                rotulo="Tarefas",
                nota=None,
                evidencia="Nenhuma tarefa registrada neste projeto.",
            )

        feitas = sum(q for status, q in linhas if status == TaskStatus.DONE.value)
        abertas = sum(
            q for status, q in linhas if status in (TaskStatus.OPEN.value, TaskStatus.DOING.value)
        )
        return Indicador(
            chave="tarefas",
            rotulo="Tarefas",
            nota=round(feitas / total * 100),
            evidencia=f"{feitas} de {total} concluída(s); {abertas} em aberto.",
            sugestao="" if not abertas else "A aba do projeto lista as abertas por prioridade.",
        )

    def _divida(self, project: Project) -> Indicador:
        """Dívida declarada é sinal de cuidado, mas acumulada vira peso.

        A nota cai com o número de itens abertos, e satura: dez itens ou trinta
        são a mesma mensagem, e fingir precisão entre eles seria número
        inventado.
        """
        abertas = self.session.execute(
            select(func.count())
            .select_from(AiMemory)
            .where(
                AiMemory.project_id == project.id,
                AiMemory.kind.in_((MemoryKind.DEBT.value, MemoryKind.BUG.value)),
            )
        ).scalar_one()

        if not abertas:
            return Indicador(
                chave="divida",
                rotulo="Dívida técnica",
                nota=None,
                evidencia="Nada registrado como dívida ou bug na memória do projeto.",
                sugestao="Anotar a dívida é o que permite medi-la depois.",
            )

        return Indicador(
            chave="divida",
            rotulo="Dívida técnica",
            nota=max(0, 100 - min(abertas, 10) * 10),
            evidencia=f"{abertas} item(ns) de dívida ou bug na memória.",
            sugestao="" if abertas < 3 else "Fechar os mais antigos costuma render mais.",
        )
