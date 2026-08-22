"""Schemas de serviços, health, dashboard e ações de sistema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.project import ServiceIn


class ServiceStateOut(BaseModel):
    key: str
    label: str
    host: str
    port: int | None = None
    url: str | None = None
    health_kind: str
    state: str
    latency_ms: int | None = None
    detail: str | None = None
    checked_at: datetime | None = None


class ServiceList(BaseModel):
    items: list[ServiceStateOut] = Field(default_factory=list)


class ServicesReplace(BaseModel):
    items: list[ServiceIn] = Field(default_factory=list, max_length=50)


class PortUsage(BaseModel):
    port: int
    projects: list[str]
    conflict: bool


class PortBinding(BaseModel):
    """Quem ocupa a porta, no detalhe que a tela precisa para editá-la.

    `PortUsage` responde "esta porta está em conflito?" com nomes de projeto.
    Para *trocar* a porta a tela precisa do id do projeto e da chave do
    serviço — sem isso ela teria que buscar cada projeto para descobrir a
    quem a porta pertence.
    """

    project_id: str
    project_name: str
    service_key: str
    service_label: str
    host: str
    port: int
    url: str | None = None
    conflict: bool = False


class ObservedPortOut(BaseModel):
    """Porta que está escutando na máquina agora, e de quem parece ser.

    Contraparte observada de `PortBinding`, que é o lado declarado. As duas
    juntas são o que permite dizer "você declarou 3003 e o que responde é
    8765" — a divergência que fazia o painel mostrar projeto parado com o
    servidor no ar.
    """

    port: int
    pid: int | None = None
    process_name: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    #: "cwd", "cmdline", "container" ou "unknown". A UI usa isto para dizer
    #: **por que** acha que a porta é daquele projeto, em vez de afirmar.
    matched_by: str = "unknown"
    #: Onde o processo roda. É o que identifica o processo para um humano:
    #: "node.exe" não diz nada, "node.exe em Projetos/AI Procedures" diz tudo.
    cwd: str | None = None
    #: Servidor de desenvolvimento largado — dentro de um root permitido e sem
    #: projeto que o reivindique. Só estes a tela oferece encerrar.
    orphan: bool = False
    #: A atribuição é prova (`cwd`/`cmdline`) e não palpite (`container`, que
    #: infere pelo número declarado). Só com prova a tela afirma "no ar"; com
    #: palpite ela diz "ocupada por", que é verdade sem afirmar dono.
    strong_evidence: bool = False


class PortMismatch(BaseModel):
    """Serviço cujo número declarado não corresponde ao que está no ar."""

    project_id: str
    project_name: str
    service_key: str
    service_label: str
    declared_port: int
    #: Porta em escuta atribuída ao mesmo projeto. `None` quando nada do
    #: projeto está escutando — aí é só "declarado e nada respondendo".
    observed_port: int | None = None
    process_name: str | None = None


class PortMap(BaseModel):
    items: list[PortUsage] = Field(default_factory=list)
    bindings: list[PortBinding] = Field(default_factory=list)
    conflicts: int = 0
    #: Vazio até o primeiro ciclo do poller, e também quando a varredura não
    #: pôde ser feita. `observation_available` separa os dois casos: sem ele,
    #: "não consegui olhar" apareceria como "nada escutando".
    observed: list[ObservedPortOut] = Field(default_factory=list)
    observation_available: bool = True
    mismatches: list[PortMismatch] = Field(default_factory=list)


class OpenBrowserRequest(BaseModel):
    #: Chave do serviço, nunca a URL (decisão D-13).
    service_key: str = Field(min_length=1, max_length=32)


class OpenResult(BaseModel):
    opened: bool
    action: str
    detail: str | None = None


# --- dashboard ---


class TotalsOut(BaseModel):
    projects: int = 0
    running: int = 0
    stopped: int = 0
    missing: int = 0
    with_docker: int = 0
    pinned: int = 0


class PendingChangeOut(BaseModel):
    project_id: str
    name: str
    branch: str | None = None
    dirty_count: int


class ActiveServiceOut(BaseModel):
    project_id: str
    project_name: str
    #: A chave do serviço, e não só o rótulo. O trilho lateral abre o serviço
    #: no navegador mandando a chave — sem ela ia `undefined` na requisição e o
    #: backend recusava com "service_key: Field required", num botão que
    #: parecia perfeitamente clicável.
    key: str
    label: str
    url: str | None = None
    port: int | None = None
    state: str


class PortConflictOut(BaseModel):
    port: int
    projects: list[str]


class RecentProjectOut(BaseModel):
    id: str
    name: str
    status: str
    last_accessed_at: datetime | None = None


class DashboardOut(BaseModel):
    totals: TotalsOut
    pending_changes: list[PendingChangeOut] = Field(default_factory=list)
    active_services: list[ActiveServiceOut] = Field(default_factory=list)
    port_conflicts: list[PortConflictOut] = Field(default_factory=list)
    recent_projects: list[RecentProjectOut] = Field(default_factory=list)
    generated_at: datetime
    #: Explícito de propósito: a UI mostra a idade do dado em vez de fingir
    #: tempo real (decisão D-18).
    from_cache: bool


# --- servidor de desenvolvimento ---


class DevServerOut(BaseModel):
    """Estado do servidor que o painel subiu para este projeto."""

    running: bool
    pid: int | None = None
    #: O comando, como texto, para a tela mostrar o que roda antes do clique.
    #: Ninguém deve descobrir o que o botão faz depois de apertá-lo.
    command: str = ""
    #: "manifest", "node" ou "python" — de onde o comando veio.
    source: str = ""
    #: O arquivo que sustenta a decisão, ex.: "package.json · scripts.dev (pnpm)".
    evidence: str = ""
    started_at: datetime | None = None
    #: Há um comando conhecido, mesmo com nada rodando. Separa "posso ligar" de
    #: "não sei como" — que na tela são um botão e uma explicação, não o mesmo
    #: botão desabilitado sem motivo.
    can_start: bool = False
    #: O comando abre porta diferente da cadastrada — o painel subiria o
    #: servidor num lugar e o verificaria em outro. `None` quando concordam.
    port_warning: str | None = None


class DevServerLogs(BaseModel):
    lines: list[str] = Field(default_factory=list)


class EnvironmentPlanOut(BaseModel):
    """O que "Ligar" faria neste projeto, antes de fazer.

    A tela mostra isto para ninguém descobrir o que o botão faz depois de
    apertá-lo, e usa `app_command` para decidir se "Desligar" para a aplicação
    ou o Compose.
    """

    compose_file: str | None = None
    app_command: str = ""
    app_source: str = ""
    #: Serviços declarados cujas portas a subida espera antes de rodar o app.
    dependencies: list[str] = Field(default_factory=list)
    app_running: bool = False

    @property
    def has_app(self) -> bool:
        return bool(self.app_command)


class EnvironmentStopped(BaseModel):
    #: "app" ou "docker" — o que de fato foi parado.
    stopped: str


class RunningServerOut(BaseModel):
    """Um servidor de desenvolvimento no ar, visto de fora do projeto."""

    project_id: str
    project_name: str
    pid: int
    command: str
    started_at: datetime


class RunningServerList(BaseModel):
    items: list[RunningServerOut] = Field(default_factory=list)


# --- métricas da máquina ---


class MachineMetricsOut(BaseModel):
    cpu_percent: float
    cpu_count: int
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_free_gb: float
    #: `None` quando a máquina não expõe zona térmica — o que vale para muito
    #: desktop e para toda máquina virtual. A tela mostra "—", nunca zero:
    #: "não sei" e "está frio" são coisas diferentes.
    temperature_c: float | None = None


class ServerMetricsOut(BaseModel):
    """Consumo de um servidor de desenvolvimento, com o nome do projeto.

    É o que o Gerenciador de Tarefas não sabe dizer: lá são dezoito `node.exe`
    sem dono. Aqui cada árvore tem projeto, porque foi o painel que a subiu.
    """

    project_id: str
    project_name: str
    pid: int
    #: Fração da máquina inteira, não soma por núcleo — é o que a barra na tela
    #: representa.
    cpu_percent: float
    memory_mb: float
    process_count: int


class MetricsOut(BaseModel):
    machine: MachineMetricsOut
    servers: list[ServerMetricsOut] = Field(default_factory=list)


class ProcessStopped(BaseModel):
    stopped: bool
    pid: int
    port: int
