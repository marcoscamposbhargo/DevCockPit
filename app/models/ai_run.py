"""Uma linha por **tentativa** de execução — o registro que explica a resposta.

Com cadeia de fallback, uma pergunta deixa de ter uma execução e passa a ter
várias: o local deu timeout, o primeiro provedor de nuvem devolveu 429, o
segundo respondeu. Guardar só a que deu certo apaga exatamente a parte que
interessa quando alguém pergunta "por que isso demorou 40 segundos?" ou "por que
essa pergunta foi para a nuvem?".

Tabela nova, e não colunas em `ai_message`, porque tentativa que falhou não tem
mensagem associada: ela caberia mal numa linha de conversa que nunca existiu.

Duas ausências são de propósito, e não descuido:

- **não há coluna de prompt nem de resposta** (REQ-10). O conteúdo da conversa
  vive em `ai_message`; repeti-lo aqui espalharia o texto do usuário por mais um
  lugar sem nenhum ganho de diagnóstico;
- **`estimated_cost` e `price_date` são anuláveis** (**P-02**). Modelo sem preço
  declarado grava `null`, que a tela mostra como "não medido". Gravar `0` seria
  afirmar que a chamada foi de graça, e ninguém mediu isso.

`error` guarda mensagem **já mascarada** por `app/services/ai/redaction.py`:
mensagem de erro de provedor carrega URL com token dentro mais vezes do que
parece (**P-05**).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UtcDateTime, utcnow


class RunStatus(StrEnum):
    """Como a tentativa terminou.

    `SKIPPED` não é falha: é o candidato que a cadeia nem chegou a tentar,
    porque outro respondeu antes ou porque o orçamento interrompeu. Contá-lo
    como erro inflaria a taxa de falha da tela de consumo.
    """

    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


#: Os dois status que contam como falha de execução (REQ-12).
STATUS_DE_FALHA = frozenset({RunStatus.TIMEOUT.value, RunStatus.ERROR.value})


class RunDecision(StrEnum):
    """Quem escolheu o modelo desta tentativa.

    `MANUAL` é escolha explícita da pessoa, que vence o roteador (REQ-08). Sem
    esta coluna, uma escolha ruim do roteador e uma escolha ruim do usuário
    ficariam indistinguíveis no registro.
    """

    AUTO = "auto"
    MANUAL = "manual"


class AiRun(Base):
    """Uma tentativa de execução: quem foi chamado, quanto custou e como acabou."""

    __tablename__ = "ai_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Comum a todas as tentativas da mesma pergunta. É o que permite ler a
    #: cadeia inteira em ordem depois que ela terminou — daí o índice.
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    #: 1, 2, 3... na ordem em que a cadeia tentou.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(
        String(8), nullable=False, default=RunDecision.AUTO.value
    )

    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(8), nullable=False)

    #: `null` = não medido, nunca `0` (**P-02**). Modelo sem preço declarado em
    #: `configs/ai.yml` chega aqui sem custo, e a tela diz isso.
    #:
    #: `asdecimal=False` porque o SQLite não tem decimal nativo: pedir `Decimal`
    #: faz o SQLAlchemy avisar em toda leitura, e o valor é estimativa a partir
    #: de uma tabela de preço datada, não saldo contábil.
    estimated_cost: Mapped[float | None] = mapped_column(
        Numeric(12, 6, asdecimal=False), nullable=True
    )
    #: A data em que o preço usado foi anotado. Vai junto do custo aonde ele
    #: aparecer (REQ-11) — custo sem data envelhece sem avisar.
    price_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    #: Mensagem já mascarada. Nulo quando a tentativa deu certo.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_ai_run_correlation", "correlation_id", "attempt"),)

    @property
    def falhou(self) -> bool:
        return self.status in STATUS_DE_FALHA
