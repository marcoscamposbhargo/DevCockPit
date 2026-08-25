"""Memória de projeto e memória global do desenvolvedor.

A regra que impede memória virar ficção está no campo `source`:

* `observed` — o DevCockpit mediu (sessão, atividade, saúde);
* `human` — a pessoa escreveu ou confirmou;
* `ai_suggested` — proposta que ninguém confirmou ainda.

Os três existem lado a lado e a interface mostra a diferença. Sugestão não
confirmada nunca aparece como afirmação do projeto — é a mesma doutrina que fez
o painel parar de dizer "no ar" sem prova.

Memória **não** guarda estado vivo: porta, container, branch e saúde são
consultados na hora, de quem já os conhece. Copiar isso para cá criaria uma
segunda verdade que envelhece.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.ai import AiMemory, MemoryKind, MemorySource
from app.models.base import utcnow
from app.repositories.ai_repository import MemoryRepository

#: Tipos que só fazem sentido sem projeto — são sobre quem desenvolve, não
#: sobre o que está sendo construído.
APENAS_GLOBAIS = frozenset(
    {MemoryKind.PREFERENCE.value, MemoryKind.PATTERN.value, MemoryKind.COMMAND.value}
)

#: Sugestão que ninguém confirmou some depois disto. Memória confirmada nunca
#: é podada por rotina: o que a pessoa afirmou só ela apaga.
DIAS_ATE_PODAR_SUGESTAO = 30


class MemoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = MemoryRepository(session)

    def list(
        self,
        *,
        project_id: str | None = None,
        global_only: bool = False,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[AiMemory]:
        return self.repo.list(
            project_id=project_id, global_only=global_only, kind=kind, limit=limit
        )

    def write(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        project_id: str | None = None,
        source: str = MemorySource.HUMAN.value,
        session_id: str | None = None,
    ) -> AiMemory:
        kind = self._validar_kind(kind, project_id)
        source = self._validar_source(source)

        titulo = (title or "").strip()
        if not titulo:
            raise ValidationError("Toda memória precisa de um título.")

        registro = AiMemory(
            project_id=project_id,
            kind=kind,
            title=titulo[:200],
            body=(body or "").strip(),
            source=source,
            # Escrita por humano já nasce confirmada: quem digitou afirmou.
            # Sugestão da IA nasce pendente, e é isso que a distingue.
            confirmed_at=utcnow() if source != MemorySource.AI_SUGGESTED.value else None,
            session_id=session_id,
        )
        return self.repo.add(registro)

    def confirm(self, memory_id: int) -> AiMemory:
        registro = self._buscar(memory_id)
        registro.confirmed_at = registro.confirmed_at or utcnow()
        registro.source = MemorySource.HUMAN.value
        self.session.flush()
        return registro

    def update(
        self, memory_id: int, *, title: str | None = None, body: str | None = None
    ) -> AiMemory:
        registro = self._buscar(memory_id)
        if title is not None:
            novo = title.strip()
            if not novo:
                raise ValidationError("Toda memória precisa de um título.")
            registro.title = novo[:200]
        if body is not None:
            registro.body = body.strip()
        # Editar é afirmar: o que passou pela mão de alguém deixa de ser palpite.
        registro.confirmed_at = registro.confirmed_at or utcnow()
        self.session.flush()
        return registro

    def delete(self, memory_id: int) -> None:
        self.repo.delete(self._buscar(memory_id))

    def prune(self, days: int = DIAS_ATE_PODAR_SUGESTAO) -> int:
        return self.repo.prune_unconfirmed(utcnow() - timedelta(days=days))

    # --- validação ---

    def _buscar(self, memory_id: int) -> AiMemory:
        registro = self.repo.get(memory_id)
        if registro is None:
            raise ValidationError(f"Memória {memory_id} não encontrada.")
        return registro

    @staticmethod
    def _validar_kind(kind: str, project_id: str | None) -> str:
        conhecidos = {item.value for item in MemoryKind}
        if kind not in conhecidos:
            raise ValidationError(
                f"Tipo de memória inválido: {kind!r}. Conhecidos: {', '.join(sorted(conhecidos))}."
            )
        if kind in APENAS_GLOBAIS and project_id is not None:
            raise ValidationError(
                f"{kind!r} é memória do desenvolvedor, não de um projeto — "
                "grave sem projeto para valer em todos."
            )
        return kind

    @staticmethod
    def _validar_source(source: str) -> str:
        conhecidos = {item.value for item in MemorySource}
        if source not in conhecidos:
            raise ValidationError(f"Origem de memória inválida: {source!r}.")
        return source
