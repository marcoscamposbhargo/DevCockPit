"""Base do SQLAlchemy e sessão."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTimeType(TypeDecorator):
    """DateTime que sempre entra e sai com timezone UTC.

    O SQLite não guarda timezone: `DateTime(timezone=True)` grava certo, mas
    devolve datetime **ingênuo**. Comparar isso com `utcnow()` levanta
    `TypeError: can't compare offset-naive and offset-aware datetimes`.

    Descoberto quando o poller de health quebrava em todo ciclo — e a exceção
    era engolida pelo `except` que impede o poller de derrubar o servidor. Ou
    seja: falha silenciosa, o pior tipo. A conversão fica aqui, num lugar só,
    em vez de espalhar `if dt.tzinfo is None` por toda comparação.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


UtcDateTime = UtcDateTimeType()


def create_session_factory(database_url: str, echo: bool = False) -> sessionmaker[Session]:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # WAL reduz contenção entre requisição e tarefas de background (ADR-002).
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # Espera em vez de falhar quando outro escritor está no meio de uma
            # transação. O padrão do driver são 5 s, e o poller de health mais a
            # requisição do usuário já se cruzaram dentro dessa janela. Não
            # substitui transação curta — só evita que um pico vire erro na tela.
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
