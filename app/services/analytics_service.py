"""Análise histórica do painel (gráficos do dashboard).

O dashboard responde "agora": quantos no ar, qual porta em conflito. Este
serviço responde "e antes?" — a pergunta que separa rotina de aviso. 80% de
erro numa ação é grave; 80% de erro numa ação executada duas vezes na semana
passada é ruído.

Duas fontes, com naturezas diferentes, e a diferença aparece na resposta:

* `activity_log` é **registro de fato**: cada linha é uma ação que aconteceu.
  Agregar é contar;
* `health_snapshot` é **amostragem**: o poller olha de tempos em tempos, e
  entre duas amostras ninguém sabe. Por isso a disponibilidade é ponderada por
  tempo e vem acompanhada de `coverage_pct` — quanto da janela tem dado. Sem
  isso, um serviço verificado duas vezes viraria "100% no ar" com a mesma
  autoridade de um verificado o dia inteiro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.models.base import utcnow
from app.repositories.analytics_repository import AnalyticsRepository, HealthRow

#: Falha, para efeito de gráfico, é tudo que não terminou bem. `DENIED` entra
#: separado nos totais porque significa outra coisa (tentativa recusada pela
#: allowlist), mas conta como falha na taxa: foi uma ação que não fez o que
#: quem clicou queria.
FALHAS = frozenset({"FAILED", "TIMEOUT", "DENIED"})

MAX_ACOES = 12
MAX_TECNOLOGIAS = 12
BUCKETS_LATENCIA = 24

CACHE_KEY = "analytics"


@dataclass
class DiaDeAtividade:
    day: str
    success: int = 0
    failed: int = 0
    timeout: int = 0
    denied: int = 0

    @property
    def total(self) -> int:
        return self.success + self.failed + self.timeout + self.denied


@dataclass
class ResumoDeAcao:
    action: str
    total: int
    failures: int
    error_rate: float
    p50_ms: int | None
    p95_ms: int | None


@dataclass
class Tecnologia:
    category: str
    name: str
    projects: int


@dataclass
class DisponibilidadeDeServico:
    project_id: str
    project_name: str
    service_key: str
    samples: int
    uptime_pct: float | None
    coverage_pct: float
    last_state: str
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    latency_series: list[float | None]


@dataclass
class Analytics:
    days: int
    since: datetime
    until: datetime
    activity_daily: list[DiaDeAtividade] = field(default_factory=list)
    activity_by_hour: list[int] = field(default_factory=list)
    actions: list[ResumoDeAcao] = field(default_factory=list)
    technologies: list[Tecnologia] = field(default_factory=list)
    uptime: list[DisponibilidadeDeServico] = field(default_factory=list)
    activity_total: int = 0
    failure_rate: float = 0.0
    truncated: bool = False
    generated_at: datetime = field(default_factory=utcnow)
    from_cache: bool = False


def percentil(valores: list[int], p: float) -> int | None:
    """Percentil por posto mais próximo.

    Sem interpolação de propósito: o valor devolvido é uma duração que
    realmente aconteceu, não uma média entre duas. Num conjunto de seis
    medições, interpolar inventa um número que ninguém observou.
    """
    if not valores:
        return None
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, round(p * (len(ordenados) - 1))))
    return int(ordenados[indice])


class AnalyticsService:
    def __init__(
        self,
        session: Session,
        cache: TTLCache,
        *,
        max_gap_s: float = 600.0,
    ) -> None:
        self.repo = AnalyticsRepository(session)
        self.cache = cache
        #: Distância máxima que uma amostra pode "cobrir". Uma amostra às 9h e
        #: a seguinte às 15h não provam seis horas no ar — provam dois
        #: instantes, e o painel esteve desligado no meio. O que passa daqui
        #: vira buraco de cobertura, não disponibilidade.
        self.max_gap_s = max_gap_s

    def build(self, days: int = 14) -> Analytics:
        chave = f"{CACHE_KEY}:{days}"
        cached = self.cache.get(chave)
        if cached is not None:
            cached.from_cache = True
            return cached

        until = utcnow()
        since = until - timedelta(days=days)

        atividade, truncou_atividade = self.repo.activity_since(since)
        saude, truncou_saude = self.repo.health_since(since)

        resultado = Analytics(
            days=days,
            since=since,
            until=until,
            activity_daily=self._por_dia(atividade, since, until),
            activity_by_hour=self._por_hora(atividade),
            actions=self._por_acao(atividade),
            technologies=self._tecnologias(),
            uptime=self._disponibilidade(saude, since, until),
            activity_total=len(atividade),
            failure_rate=self._taxa_de_falha(atividade),
            truncated=truncou_atividade or truncou_saude,
        )
        self.cache.set(chave, resultado)
        return resultado

    def invalidate(self) -> None:
        for days in range(1, 91):
            self.cache.invalidate(f"{CACHE_KEY}:{days}")

    # --- atividade ---

    def _por_dia(self, linhas, since: datetime, until: datetime) -> list[DiaDeAtividade]:
        """Contagem por dia **local**, com os dias vazios presentes.

        Omitir dia sem atividade encolheria o eixo e faria uma sexta-feira
        parada parecer colada na segunda seguinte — o gráfico mostraria
        continuidade onde houve silêncio.
        """
        por_dia: dict[date, DiaDeAtividade] = {}

        inicio = since.astimezone().date()
        fim = until.astimezone().date()
        dia = inicio
        while dia <= fim:
            por_dia[dia] = DiaDeAtividade(day=dia.isoformat())
            dia += timedelta(days=1)

        for linha in linhas:
            chave = linha.created_at.astimezone().date()
            alvo = por_dia.get(chave)
            if alvo is None:
                continue
            self._somar(alvo, linha.status)

        return [por_dia[d] for d in sorted(por_dia)]

    @staticmethod
    def _somar(alvo: DiaDeAtividade, status: str) -> None:
        if status == "SUCCESS":
            alvo.success += 1
        elif status == "TIMEOUT":
            alvo.timeout += 1
        elif status == "DENIED":
            alvo.denied += 1
        else:
            alvo.failed += 1

    @staticmethod
    def _por_hora(linhas) -> list[int]:
        horas = [0] * 24
        for linha in linhas:
            horas[linha.created_at.astimezone().hour] += 1
        return horas

    @staticmethod
    def _taxa_de_falha(linhas) -> float:
        if not linhas:
            return 0.0
        falhas = sum(1 for linha in linhas if linha.status in FALHAS)
        return round(100.0 * falhas / len(linhas), 1)

    def _por_acao(self, linhas) -> list[ResumoDeAcao]:
        agrupado: dict[str, list] = {}
        for linha in linhas:
            agrupado.setdefault(linha.action, []).append(linha)

        resumos: list[ResumoDeAcao] = []
        for acao, itens in agrupado.items():
            duracoes = [i.duration_ms for i in itens if i.duration_ms is not None]
            falhas = sum(1 for i in itens if i.status in FALHAS)
            resumos.append(
                ResumoDeAcao(
                    action=acao,
                    total=len(itens),
                    failures=falhas,
                    error_rate=round(100.0 * falhas / len(itens), 1),
                    p50_ms=percentil(duracoes, 0.50),
                    p95_ms=percentil(duracoes, 0.95),
                )
            )

        resumos.sort(key=lambda r: (r.total, r.failures), reverse=True)
        return resumos[:MAX_ACOES]

    def _tecnologias(self) -> list[Tecnologia]:
        return [
            Tecnologia(category=cat, name=nome, projects=qtd)
            for cat, nome, qtd in self.repo.technology_counts()[:MAX_TECNOLOGIAS]
        ]

    # --- disponibilidade ---

    def _disponibilidade(
        self, linhas: list[HealthRow], since: datetime, until: datetime
    ) -> list[DisponibilidadeDeServico]:
        if not linhas:
            return []

        nomes = self.repo.project_names()
        por_servico: dict[tuple[str, str], list[HealthRow]] = {}
        for linha in linhas:
            por_servico.setdefault((linha.project_id, linha.service_key), []).append(linha)

        janela = max(1.0, (until - since).total_seconds())
        saida: list[DisponibilidadeDeServico] = []

        for (project_id, service_key), amostras in por_servico.items():
            amostras.sort(key=lambda linha: linha.checked_at)

            coberto = 0.0
            no_ar = 0.0
            for indice, amostra in enumerate(amostras):
                proxima = amostras[indice + 1].checked_at if indice + 1 < len(amostras) else until
                intervalo = min(
                    self.max_gap_s, max(0.0, (proxima - amostra.checked_at).total_seconds())
                )
                coberto += intervalo
                if amostra.state == "ONLINE":
                    no_ar += intervalo

            # Só a latência de quem respondeu. Uma verificação que estourou o
            # tempo também tem duração — e é sempre o teto do timeout. Misturar
            # as duas faria a latência "piorar" justamente quando o serviço
            # caiu, medindo a paciência do verificador em vez do serviço.
            latencias = [
                a.latency_ms
                for a in amostras
                if a.latency_ms is not None and a.state == "ONLINE"
            ]
            saida.append(
                DisponibilidadeDeServico(
                    project_id=project_id,
                    project_name=nomes.get(project_id, project_id),
                    service_key=service_key,
                    samples=len(amostras),
                    uptime_pct=round(100.0 * no_ar / coberto, 1) if coberto > 0 else None,
                    coverage_pct=round(min(100.0, 100.0 * coberto / janela), 1),
                    last_state=amostras[-1].state,
                    p50_latency_ms=percentil(latencias, 0.50),
                    p95_latency_ms=percentil(latencias, 0.95),
                    latency_series=self._serie_de_latencia(amostras, since, until),
                )
            )

        # Pior disponibilidade primeiro: quem está quebrado é o motivo de a
        # pessoa ter aberto a tela. Serviço sem dado suficiente vai para o fim.
        saida.sort(key=lambda s: (s.uptime_pct is None, s.uptime_pct or 0.0, -s.samples))
        return saida

    @staticmethod
    def _serie_de_latencia(
        amostras: list[HealthRow], since: datetime, until: datetime
    ) -> list[float | None]:
        """Média por balde de tempo, com `None` onde não houve amostra.

        O buraco é dado: uma linha reta atravessando o período em que ninguém
        mediu afirma estabilidade que ninguém observou.
        """
        largura = max(1.0, (until - since).total_seconds() / BUCKETS_LATENCIA)
        somas = [0.0] * BUCKETS_LATENCIA
        contagens = [0] * BUCKETS_LATENCIA

        for amostra in amostras:
            if amostra.latency_ms is None or amostra.state != "ONLINE":
                continue
            indice = int((amostra.checked_at - since).total_seconds() // largura)
            indice = max(0, min(BUCKETS_LATENCIA - 1, indice))
            somas[indice] += amostra.latency_ms
            contagens[indice] += 1

        return [
            round(somas[i] / contagens[i], 1) if contagens[i] else None
            for i in range(BUCKETS_LATENCIA)
        ]
