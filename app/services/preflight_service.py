"""Pré-voo: o que impede este projeto de subir, dito **antes** da tentativa.

O caminho antigo era descobrir pelo erro. Você clicava em Ligar, o painel
começava a subir, e no meio o Compose falhava com `port is already allocated` —
ou pior, o processo local nascia, morria em silêncio, e a tela mostrava
"desligado" sem dizer por quê.

Este serviço faz a pergunta na ordem certa: **as portas que este projeto
declara estão livres, e quem está nelas?** A resposta é uma lista de
impedimentos, cada um com o que dá para fazer a respeito.

A regra de atribuição é a mesma do resto do painel: porta ocupada por processo
**deste** projeto não é impedimento — é o projeto já estar no ar, que é o
resultado desejado. Impedimento é a porta estar com outro dono, ou com dono que
o painel não consegue provar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.models.project import Project

logger = logging.getLogger(__name__)


@dataclass
class Impedimento:
    port: int
    service_key: str
    service_label: str
    #: Quem está na porta, em texto para a tela.
    occupant: str
    #: Projeto dono do processo, quando o painel prova de quem é.
    occupant_project_id: str | None = None
    occupant_project_name: str | None = None
    #: PID, quando o painel se dispõe a encerrar o processo (órfão ou não
    #: gerenciado, sempre dentro de um root permitido — defesa D4).
    stoppable_pid: int | None = None

    @property
    def resolvable(self) -> bool:
        return self.stoppable_pid is not None

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "service_key": self.service_key,
            "service_label": self.service_label,
            "occupant": self.occupant,
            "occupant_project_id": self.occupant_project_id,
            "occupant_project_name": self.occupant_project_name,
            "stoppable_pid": self.stoppable_pid,
            "resolvable": self.resolvable,
        }


@dataclass
class Preflight:
    ready: bool = True
    #: Portas declaradas que já estão ocupadas por outro.
    blockers: list[Impedimento] = field(default_factory=list)
    #: Portas ocupadas por processo **deste** projeto: não impedem nada, mas a
    #: tela avisa, porque explicam por que "subir" pode não mudar nada.
    already_ours: list[int] = field(default_factory=list)
    #: `False` quando não houve varredura ainda. Sem observação, o pré-voo se
    #: cala em vez de liberar por ignorância — mas também não bloqueia.
    observed: bool = True

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "observed": self.observed,
            "blockers": [b.to_dict() for b in self.blockers],
            "already_ours": self.already_ours,
        }

    def message(self) -> str:
        """Uma frase que diz o que houve e o que fazer."""
        if self.ready:
            return "Nada impede a subida."

        partes = []
        for bloqueio in self.blockers:
            quem = bloqueio.occupant
            if bloqueio.occupant_project_name:
                quem += f", do {bloqueio.occupant_project_name}"
            partes.append(f"{bloqueio.port} ({bloqueio.service_label}) está com {quem}")

        return "Porta ocupada: " + "; ".join(partes) + "."


class PreflightService:
    def __init__(self, discovery=None) -> None:  # type: ignore[no-untyped-def]
        #: Só leitura da última varredura. Nada é escaneado aqui: é caminho de
        #: requisição, e quem varre é o poller (NFR-010).
        self.discovery = discovery

    def check(self, project: Project) -> Preflight:
        if self.discovery is None:
            return Preflight(observed=False)

        observacao = self.discovery.last_known()
        if not observacao.ports:
            # Antes do primeiro ciclo do poller não há o que cruzar. Liberar
            # por ignorância seria o mesmo erro de afirmar "no ar" sem prova —
            # então a tela recebe `observed: false` e diz isso.
            return Preflight(observed=False)

        por_porta = observacao.by_port()
        resultado = Preflight()

        for service in project.services:
            if not service.port:
                continue

            ocupada = por_porta.get(service.port)
            if ocupada is None:
                continue

            if ocupada.project_id == project.id:
                resultado.already_ours.append(service.port)
                continue

            resultado.blockers.append(
                Impedimento(
                    port=service.port,
                    service_key=service.key,
                    service_label=service.label,
                    occupant=self._descrever(ocupada),
                    occupant_project_id=ocupada.project_id,
                    occupant_project_name=ocupada.project_name,
                    # Só oferece encerrar o que a descoberta já classificou
                    # como encerrável: dentro de root permitido, órfão ou não
                    # gerenciado. O resto da máquina fica fora por construção.
                    stoppable_pid=ocupada.pid if ocupada.stoppable else None,
                )
            )

        resultado.ready = not resultado.blockers
        return resultado

    @staticmethod
    def _descrever(ocupada) -> str:  # type: ignore[no-untyped-def]
        """Quem está na porta, do mais informativo ao menos.

        Sem prova de dono, o texto diz isso — em vez de acusar um projeto pelo
        número que ele declara, que foi o erro que custou duas sessões.
        """
        nome = ocupada.process_name or "um processo"
        if ocupada.project_name and ocupada.strong_evidence:
            return nome
        if ocupada.project_name:
            return f"{nome} (sem prova de dono)"
        return nome
