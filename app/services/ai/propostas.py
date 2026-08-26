"""Registro de propostas pendentes — o que permite a auditoria dizer "foi a IA".

O problema que este módulo resolve não é técnico, é de honestidade. Até a Fase
3.4, a ação que o agente propôs e a pessoa confirmou era gravada como **ação do
usuário**: verdade parcial, num painel cuja tese inteira é "fato, não palpite".

A saída óbvia seria o cliente mandar um cabeçalho dizendo "isto veio da IA". Não
serve: seria o cliente **afirmando** autoria, e afirmação de cliente é
exatamente o que o modelo de segurança deste projeto não aceita em lugar nenhum
(defesa D5, decisão D-13). Um log de auditoria que confia no auditado não audita.

Aqui o servidor guarda o que ele mesmo propôs, entrega um bilhete, e só aceita o
bilhete de volta se ele corresponder à **mesma rota e ao mesmo método** que a
proposta continha. Ninguém consegue inventar autoria de IA para uma ação que a
IA nunca propôs — e ninguém consegue reaproveitar um bilhete para outra coisa.

Vive em memória, e isso é deliberado: proposta é objeto de segundos. Sobreviver
a um reinício do processo não é qualidade nenhuma para ela — seria só uma tabela
a mais para podar.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.base import utcnow

#: Quanto tempo um bilhete vale. Dez minutos é folgado para quem leu o cartão e
#: decidiu; curto o bastante para o registro não virar depósito.
VALIDADE = timedelta(minutes=10)

#: Teto de propostas guardadas ao mesmo tempo. Uma pessoa, um painel: se passar
#: disto, alguém está chamando `/ai/propose` em laço, e o mais antigo cai.
TETO = 64


@dataclass(frozen=True)
class PropostaPendente:
    """O que o servidor precisa lembrar para reconhecer a própria proposta."""

    id: str
    action: str
    method: str
    path: str
    project_id: str | None
    reason: str
    #: "regra" ou "modelo" — quem decidiu a ação. Vai para a auditoria, e é o
    #: que permite saber depois quanto do sistema depende do modelo.
    origem: str
    criada_em: datetime

    def expirada(self, agora: datetime) -> bool:
        return agora - self.criada_em > VALIDADE


class RegistroDePropostas:
    """Guarda propostas emitidas, e as devolve **uma única vez**.

    Uso único porque a alternativa é pior: um bilhete reutilizável transformaria
    uma confirmação em quantas execuções o cliente quisesse, todas gravadas como
    autorizadas por aquela única confirmação.
    """

    def __init__(self) -> None:
        self._itens: dict[str, PropostaPendente] = {}
        # O servidor é assíncrono e os handlers rodam em threads do pool: sem
        # trava, duas confirmações simultâneas podem resgatar o mesmo bilhete.
        self._trava = threading.Lock()

    def registrar(
        self,
        *,
        action: str,
        method: str,
        path: str,
        project_id: str | None,
        reason: str,
        origem: str,
    ) -> PropostaPendente:
        agora = utcnow()
        proposta = PropostaPendente(
            id=secrets.token_urlsafe(16),
            action=action,
            method=method.upper(),
            path=path,
            project_id=project_id,
            reason=reason,
            origem=origem,
            criada_em=agora,
        )

        with self._trava:
            # Poda **depois** de inserir: podar antes deixava o registro em
            # TETO + 1, porque a inserção acontecia sobre um registro já cheio.
            self._itens[proposta.id] = proposta
            self._podar(agora)

        return proposta

    def resgatar(self, identificador: str, *, method: str, path: str) -> PropostaPendente | None:
        """Devolve a proposta se o bilhete for válido **para esta requisição**.

        A conferência de rota é o que impede um bilhete de "ver o log do
        projeto A" autorizar "desligar o projeto B".
        """
        if not identificador:
            return None

        agora = utcnow()
        with self._trava:
            self._podar(agora)
            proposta = self._itens.get(identificador)

            if proposta is None:
                return None
            if proposta.method != method.upper() or proposta.path != path:
                return None

            del self._itens[identificador]
            return proposta

    def _podar(self, agora: datetime) -> None:
        """Remove o que expirou e, se ainda passar do teto, o mais antigo."""
        for chave in [k for k, v in self._itens.items() if v.expirada(agora)]:
            del self._itens[chave]

        if len(self._itens) <= TETO:
            return

        antigos = sorted(self._itens.values(), key=lambda p: p.criada_em)
        for proposta in antigos[: len(self._itens) - TETO]:
            self._itens.pop(proposta.id, None)

    def __len__(self) -> int:
        with self._trava:
            return len(self._itens)


#: Um registro por processo. O painel é de um usuário só, numa máquina só.
REGISTRO = RegistroDePropostas()
