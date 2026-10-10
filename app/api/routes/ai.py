"""Sessão de trabalho, memória e briefing do dia.

Fase 1 do Cockpit AI: tudo aqui funciona **sem provedor de IA configurado**.
Nenhuma rota deste arquivo fala com modelo nenhum — o que existe é registro do
que o painel observou e do que a pessoa declarou.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_briefing_service,
    get_chat_service,
    get_memory_service,
    get_project_service,
    get_session,
    get_session_service,
    get_task_service,
)
from app.core.errors import DomainError
from app.models.ai import AiMemory, AiMessage, AiSession
from app.models.base import utcnow
from app.models.task import AiTask
from app.repositories.ai_repository import RunRepository
from app.schemas.ai import (
    AiHealthOut,
    AiModelList,
    AiModelOut,
    AiProviderHealthOut,
    AiProviderList,
    AiProviderOut,
    AiStatusOut,
    AiUsageIndicadores,
    AiUsageOut,
    BriefingOut,
    ChatAsk,
    ChatHistoryOut,
    ChatMessageOut,
    DayItemOut,
    EspecialistaList,
    EspecialistaOut,
    MemoryCreate,
    MemoryList,
    MemoryOut,
    MemoryUpdate,
    ProposalOut,
    ProposeAsk,
    ProposeOut,
    SessionEnd,
    SessionFactsOut,
    SessionList,
    SessionOut,
    SessionStart,
    TaskCreate,
    TaskList,
    TaskOut,
    TaskUpdate,
)
from app.services.ai.actions import POR_CHAVE as ACOES_POR_CHAVE
from app.services.ai.chat_service import ChatService
from app.services.ai.especialistas import (
    ESPECIALISTAS,
    PADRAO,
    VERSAO_DOS_PROMPTS,
)
from app.services.ai.orchestrator import Orchestrator, Proposta
from app.services.ai.propostas import REGISTRO
from app.services.ai.registry import AiConfig, ProviderDeclarado, get_ai_config
from app.services.briefing_service import BriefingService
from app.services.memory_service import MemoryService
from app.services.project_service import ProjectService
from app.services.session_service import SessionService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["ai"])
#: Fora do projeto: o briefing olha todos, e a memória global não pertence a
#: nenhum.
global_router = APIRouter(prefix="/api/ai", tags=["ai"])


def _sessao_out(registro: AiSession) -> SessionOut:
    fatos = SessionService.facts_of(registro)
    return SessionOut(
        id=registro.id,
        project_id=registro.project_id,
        started_at=registro.started_at,
        ended_at=registro.ended_at,
        objective=registro.objective,
        summary=registro.summary,
        next_steps=registro.next_steps,
        is_open=registro.is_open,
        facts=SessionFactsOut(**asdict(fatos)),
    )


def _memoria_out(registro: AiMemory) -> MemoryOut:
    return MemoryOut(
        id=registro.id,
        project_id=registro.project_id,
        kind=registro.kind,
        title=registro.title,
        body=registro.body,
        source=registro.source,
        confirmed=registro.is_confirmed,
        session_id=registro.session_id,
        created_at=registro.created_at,
        updated_at=registro.updated_at,
    )


# --- sessão ---------------------------------------------------------------


@router.get("/sessions", response_model=SessionList)
def list_sessions(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> SessionList:
    project = projects.get(project_id)
    atual = sessions.current(project)
    anterior = sessions.previous(project)
    return SessionList(
        items=[_sessao_out(s) for s in sessions.history(project, limit=limit)],
        current=_sessao_out(atual) if atual else None,
        previous=_sessao_out(anterior) if anterior else None,
    )


@router.post("/sessions/start", response_model=SessionOut)
def start_session(
    project_id: str,
    payload: SessionStart,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
) -> SessionOut:
    """Abre a sessão e registra o marco inicial do Git.

    `touch=True`: abrir sessão é acessar o projeto, e o dashboard usa isso para
    ordenar o que foi mexido por último.
    """
    project = projects.get(project_id, touch=True)
    return _sessao_out(sessions.start(project, objective=payload.objective))


@router.post("/sessions/end", response_model=SessionOut)
def end_session(
    project_id: str,
    payload: SessionEnd,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
) -> SessionOut:
    project = projects.get(project_id)
    return _sessao_out(
        sessions.end(project, summary=payload.summary, next_steps=payload.next_steps)
    )


# --- memória --------------------------------------------------------------


@router.get("/memory", response_model=MemoryList)
def list_memory(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    memory: MemoryService = Depends(get_memory_service),
    kind: str | None = Query(default=None, max_length=20),
) -> MemoryList:
    project = projects.get(project_id)
    itens = memory.list(project_id=project.id, kind=kind)
    return MemoryList(items=[_memoria_out(m) for m in itens])


@router.post("/memory", response_model=MemoryOut, status_code=201)
def create_memory(
    project_id: str,
    payload: MemoryCreate,
    projects: ProjectService = Depends(get_project_service),
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    project = projects.get(project_id)
    registro = memory.write(
        kind=payload.kind,
        title=payload.title,
        body=payload.body,
        project_id=project.id,
        session_id=payload.session_id,
    )
    return _memoria_out(registro)


@global_router.get("/memory", response_model=MemoryList)
def list_global_memory(
    memory: MemoryService = Depends(get_memory_service),
    kind: str | None = Query(default=None, max_length=20),
) -> MemoryList:
    """Memória do desenvolvedor: o que vale em todos os projetos."""
    return MemoryList(items=[_memoria_out(m) for m in memory.list(global_only=True, kind=kind)])


@global_router.post("/memory", response_model=MemoryOut, status_code=201)
def create_global_memory(
    payload: MemoryCreate,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    registro = memory.write(kind=payload.kind, title=payload.title, body=payload.body)
    return _memoria_out(registro)


@global_router.patch("/memory/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    return _memoria_out(memory.update(memory_id, title=payload.title, body=payload.body))


@global_router.post("/memory/{memory_id}/confirm", response_model=MemoryOut)
def confirm_memory(
    memory_id: int,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    """Promove sugestão a afirmação.

    Existe desde já, embora só a Fase 2 vá produzir sugestão: sem este botão, a
    distinção entre `ai_suggested` e `human` seria decorativa.
    """
    return _memoria_out(memory.confirm(memory_id))


@global_router.delete("/memory/{memory_id}", status_code=204)
def delete_memory(
    memory_id: int,
    memory: MemoryService = Depends(get_memory_service),
) -> None:
    memory.delete(memory_id)


# --- tarefas --------------------------------------------------------------


def _tarefa_out(registro: AiTask) -> TaskOut:
    return TaskOut(
        id=registro.id,
        project_id=registro.project_id,
        title=registro.title,
        detail=registro.detail,
        status=registro.status,
        priority=registro.priority,
        source=registro.source,
        session_id=registro.session_id,
        created_at=registro.created_at,
        done_at=registro.done_at,
        is_open=registro.is_open,
    )


@router.get("/tasks", response_model=TaskList)
def list_tasks(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    tasks: TaskService = Depends(get_task_service),
    include_done: bool = Query(default=True),
) -> TaskList:
    project = projects.get(project_id)
    itens = tasks.list(project.id, include_done=include_done)
    return TaskList(
        items=[_tarefa_out(t) for t in itens],
        open_count=sum(1 for t in itens if t.is_open),
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    project_id: str,
    payload: TaskCreate,
    projects: ProjectService = Depends(get_project_service),
    tasks: TaskService = Depends(get_task_service),
) -> TaskOut:
    project = projects.get(project_id)
    return _tarefa_out(
        tasks.create(
            project.id,
            title=payload.title,
            detail=payload.detail,
            priority=payload.priority,
            session_id=payload.session_id,
        )
    )


@global_router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    tasks: TaskService = Depends(get_task_service),
) -> TaskOut:
    return _tarefa_out(
        tasks.update(
            task_id,
            title=payload.title,
            detail=payload.detail,
            status=payload.status,
            priority=payload.priority,
        )
    )


@global_router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, tasks: TaskService = Depends(get_task_service)) -> None:
    """Apagar é para engano. Desistência tem estado próprio (`DROPPED`), que
    preserva a informação de que a ideia foi considerada e descartada."""
    tasks.delete(task_id)


# --- chat -----------------------------------------------------------------


@global_router.get("/status", response_model=AiStatusOut)
def ai_status(chat: ChatService = Depends(get_chat_service)) -> AiStatusOut:
    """Diz se dá para conversar, e o que falta quando não dá.

    Existe para a tela **explicar** em vez de quebrar: sem provedor
    configurado, o painel inteiro continua funcionando e esta aba diz o que
    fazer (NFR-060).
    """
    return AiStatusOut(**chat.status())


@router.get("/chat", response_model=ChatHistoryOut)
def chat_history(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    chat: ChatService = Depends(get_chat_service),
) -> ChatHistoryOut:
    project = projects.get(project_id)
    return ChatHistoryOut(
        items=[_mensagem_out(m) for m in chat.history(project)]
    )


@global_router.get("/specialists", response_model=EspecialistaList)
def listar_especialistas(
    project_id: str | None = None,
    projects: ProjectService = Depends(get_project_service),
) -> EspecialistaList:
    """Os chapéus disponíveis e os botões de cada um.

    Os atalhos vêm do **mesmo registro fechado** das propostas: a tela não ganha
    um caminho de execução próprio por estar dentro da conversa. Quando um
    projeto é informado, o caminho já vem resolvido para ele — e a ação que
    exige projeto some da lista quando não há um (defesa D-A3).
    """
    projeto = projects.get(project_id) if project_id else None

    itens = []
    for especialista in ESPECIALISTAS:
        atalhos = []
        for chave in especialista.atalhos:
            acao = ACOES_POR_CHAVE.get(chave)
            if acao is None or (acao.needs_project and projeto is None):
                continue

            proposta = Proposta(
                acao=acao,
                project_id=projeto.id if projeto else None,
                project_name=projeto.name if projeto else None,
                reason="atalho do especialista",
                origem="atalho",
            )
            dados = proposta.to_dict()
            # Atalho também precisa de bilhete: confirmado, ele vira ação
            # marcada como proposta pela IA, igual à que veio de uma frase.
            pendente = REGISTRO.registrar(
                action=dados["action"],
                method=dados["method"],
                path=dados["path"],
                project_id=dados["project_id"],
                reason=dados["reason"],
                origem=dados["origem"],
            )
            atalhos.append(ProposalOut(**dados, id=pendente.id))

        itens.append(
            EspecialistaOut(
                key=especialista.key,
                label=especialista.label,
                descricao=especialista.descricao,
                atalhos=atalhos,
            )
        )

    return EspecialistaList(
        items=itens, padrao=PADRAO.key, versao_dos_prompts=VERSAO_DOS_PROMPTS
    )


@global_router.post("/propose", response_model=ProposeOut)
def propose_action(
    payload: ProposeAsk,
    projects: ProjectService = Depends(get_project_service),
    chat: ChatService = Depends(get_chat_service),
) -> ProposeOut:
    """O que a IA faria com esta frase — **sem fazer**.

    Devolve uma ação do registro fechado, já validada, e o caminho da rota que
    a tela deve chamar se a pessoa confirmar. Esse caminho é o mesmo do botão:
    a IA não ganha execução própria (defesa D-A3).

    Não é stream porque não é texto: é um objeto pequeno, e a maior parte das
    frases resolve por regra em milissegundos, sem tocar no modelo.
    """
    # Só id e nome, e sem paginar: o catálogo inteiro é o que permite resolver
    # "sobe o kiteasy" sem o usuário dizer em qual projeto está.
    registrados, _ = projects.list(limit=200)
    catalogo_projetos = [(p.id, p.name) for p in registrados]
    orquestrador = Orchestrator(catalogo_projetos)

    # A regra roda sempre. O provedor só é montado se ela não decidir — assim
    # "sobe o kiteasy" responde na hora mesmo com a IA desligada.
    proposta = orquestrador.propose(payload.question)
    if proposta is None:
        try:
            chat.exigir_ia_ligada()
            provedor = chat.provedor_roteado(payload.question, payload.model)
        except DomainError as erro:
            return ProposeOut(message=erro.message)
        try:
            proposta = orquestrador.propose(payload.question, provedor)
        except DomainError as erro:
            return ProposeOut(message=erro.message)

    if proposta is None:
        return ProposeOut(
            message="Não encontrei nenhuma ação do painel que sirva para isso."
        )

    # O bilhete é emitido aqui, e é o que permitirá à auditoria dizer "foi a
    # IA" sem acreditar em nada que o cliente afirme (Fase 3.6).
    dados = proposta.to_dict()
    pendente = REGISTRO.registrar(
        action=dados["action"],
        method=dados["method"],
        path=dados["path"],
        project_id=dados["project_id"],
        reason=dados["reason"],
        origem=dados["origem"],
    )

    return ProposeOut(proposal=ProposalOut(**dados, id=pendente.id))


@global_router.post("/ask")
async def ask_quick(
    payload: ChatAsk,
    chat: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """Pergunta avulsa, sem projeto: o modo "assistente de terminal".

    Mesmo transporte do chat de projeto, e de propósito **sem** o Context
    Engine: dúvida de `git reset` não precisa do README de projeto nenhum, e
    num provedor local carregar contexto à toa triplica a espera.
    """

    def eventos():  # type: ignore[no-untyped-def]
        try:
            for pedaco in chat.ask_quick(
                payload.question, perfil=payload.model, modelo=payload.modelo
            ):
                dados = json.dumps({"text": pedaco}, ensure_ascii=False)
                yield f"event: chunk\ndata: {dados}\n\n"
        except DomainError as erro:
            corpo = json.dumps(
                {"code": erro.code, "message": erro.message}, ensure_ascii=False
            )
            yield f"event: error\ndata: {corpo}\n\n"
            return
        yield from _evento_de_quem_respondeu(chat)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")


@router.post("/chat")
async def chat_ask(
    project_id: str,
    payload: ChatAsk,
    request: Request,
    projects: ProjectService = Depends(get_project_service),
    chat: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """Pergunta com resposta em stream (SSE).

    Mesmo transporte do console de job, que já existe e o painel já sabe
    consumir. As guardas — IA ligada, projeto participante, orçamento do dia —
    rodam **antes** do primeiro byte: recusa vira erro HTTP normal, não um
    stream que começa e morre.
    """
    project = projects.get(project_id, touch=True)

    # O estado vivo entra por aqui, de quem já o conhece: o Context Engine não
    # consulta porta nem saúde, porque é caminho de requisição (NFR-010).
    estado = {
        "serviços declarados": len(project.services),
        "status do projeto": project.status,
    }

    def eventos():  # type: ignore[no-untyped-def]
        try:
            for pedaco in chat.ask(
                project,
                payload.question,
                estado=estado,
                perfil=payload.model,
                agente=payload.agent,
                modelo=payload.modelo,
            ):
                dados = json.dumps({"text": pedaco}, ensure_ascii=False)
                yield f"event: chunk\ndata: {dados}\n\n"
        except DomainError as erro:
            corpo = json.dumps(
                {"code": erro.code, "message": erro.message}, ensure_ascii=False
            )
            yield f"event: error\ndata: {corpo}\n\n"
            return
        yield from _evento_de_quem_respondeu(chat)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _evento_de_quem_respondeu(chat: ChatService):  # type: ignore[no-untyped-def]
    """`event: meta` com quem respondeu, quando se sabe.

    Vai depois do texto, não antes: com fallback, quem responde só é conhecido
    quando a cadeia termina — anunciar o pedido antes seria afirmar o que pode
    não ter acontecido.
    """
    if chat.quem_respondeu:
        dados = json.dumps(chat.quem_respondeu, ensure_ascii=False)
        yield f"event: meta\ndata: {dados}\n\n"


def _mensagem_out(registro: AiMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=registro.id,
        role=registro.role,
        content=registro.content,
        agent=registro.agent,
        context_summary=registro.context_summary,
        context_tokens=registro.context_tokens,
        tokens_in=registro.tokens_in,
        tokens_out=registro.tokens_out,
        created_at=registro.created_at,
    )


# --- o dia ----------------------------------------------------------------


@global_router.get("/day", response_model=BriefingOut)
def start_my_day(briefing: BriefingService = Depends(get_briefing_service)) -> BriefingOut:
    """O que merece atenção hoje, ordenado por motivo declarado."""
    dados = briefing.build()
    return BriefingOut(
        generated_at=dados.generated_at,
        total_projects=dados.total_projects,
        open_sessions=dados.open_sessions,
        # `score` fica de fora: é como a tela decide a ordem, não informação
        # para quem lê. Número de ranking exposto vira discussão sobre o número.
        items=[
            DayItemOut(
                **{
                    k: v
                    for k, v in asdict(item).items()
                    if k not in ("score", "next_task")
                },
                next_task=_tarefa_out(item.next_task) if item.next_task else None,
            )
            for item in dados.items
        ],
        suggestion=dados.suggestion,
    )


# --- registro de providers, modelos e saúde -------------------------------
#
# As três rotas desta seção leem o registro declarativo (`configs/ai.yml`) e
# sondam quem está de pé. Nenhuma delas devolve o valor de uma chave, nem
# parcialmente mascarado: o que sai é o **nome** da variável de ambiente
# (P-05). Sem o arquivo no disco, elas respondem registro vazio — arquivo
# ausente é estado normal, não erro (REQ-04).

#: Teto de espera de uma sondagem de saúde. Conversa espera 120 s porque modelo
#: pensa devagar; sondagem, não: quem espera aqui é a tela de configurações
#: abrindo, e provider fora do ar não pode segurar o painel (REQ-13).
TIMEOUT_HEALTH_S = 2.5

#: Onde cada tipo de provider lista o que serve. É um GET barato, que não gera
#: token nenhum: `/api/tags` no Ollama, `/v1/models` em quem fala o formato
#: OpenAI (DeepSeek e Kimi inclusive).
CAMINHO_DE_SONDAGEM = {"local": "/api/tags", "cloud": "/v1/models"}


@dataclass(frozen=True)
class _Sondagem:
    """O que a sondagem mediu. `motivo` só existe quando não respondeu."""

    disponivel: bool
    motivo: str = ""
    latencia_ms: int | None = None
    modelos: tuple[str, ...] = ()


def _chave_presente(provider: ProviderDeclarado) -> bool:
    """A variável de `api_key_env` existe no ambiente?

    Lê só para saber se está lá. O valor não sai desta função — nem para log,
    nem para mensagem de erro.
    """
    if not provider.api_key_env:
        # Provider local não usa chave: ausência de `api_key_env` é o normal
        # dele, não falta de configuração.
        return True
    return bool(os.environ.get(provider.api_key_env, "").strip())


def _cabecalho_de_sondagem(provider: ProviderDeclarado) -> dict[str, str]:
    """Como autenticar a sondagem, no formato que cada provider entende.

    `Bearer` cobre quem fala o formato OpenAI (DeepSeek, Kimi e afins). A
    Anthropic não: ela usa `x-api-key` e exige `anthropic-version`, e com o
    cabeçalho errado devolveria 401 — a tela mostraria "indisponível" com a
    chave correta no ambiente, que é o pior tipo de erro, o que acusa quem
    não errou.
    """
    chave = os.environ.get(provider.api_key_env, "").strip() if provider.api_key_env else ""
    if not chave:
        return {}
    if provider.id == "anthropic":
        return {"x-api-key": chave, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {chave}"}


def _modelos_listados(dados: object) -> tuple[str, ...]:
    """Os nomes que o provider disse servir, nos dois formatos que existem.

    Formato desconhecido devolve vazio em vez de inventar: a tela mostra que ele
    respondeu, sem afirmar um catálogo que ninguém leu (P-02).
    """
    if not isinstance(dados, dict):
        return ()
    itens = dados.get("data") if isinstance(dados.get("data"), list) else dados.get("models")
    if not isinstance(itens, list):
        return ()
    nomes = []
    for item in itens:
        if isinstance(item, dict):
            nome = item.get("id") or item.get("name") or item.get("model")
            if nome:
                nomes.append(str(nome))
    return tuple(nomes)


def _motivo_do_status(codigo: int, provider: ProviderDeclarado) -> str:
    """Explica o código sem ecoar o corpo da resposta.

    O corpo fica de fora de propósito: há provedor que devolve a requisição
    inteira dentro do erro, cabeçalho de autorização junto, e esta mensagem vira
    linha de log (P-05).
    """
    if codigo in (401, 403):
        variavel = provider.api_key_env or "a chave"
        return f"O provider recusou a chave. Confira {variavel} no seu `.env`."
    if codigo == 404:
        return (
            f"O provider respondeu 404 em {CAMINHO_DE_SONDAGEM[provider.type]}. "
            "Confira `base_url` em configs/ai.yml."
        )
    return f"O provider respondeu {codigo}."


async def _sondar(provider: ProviderDeclarado) -> _Sondagem:
    """Pergunta ao provider o que ele serve. Falha é resposta, não exceção."""
    if not provider.base_url:
        return _Sondagem(False, "O provider não declara `base_url` em configs/ai.yml.")

    url = provider.base_url.rstrip("/") + CAMINHO_DE_SONDAGEM[provider.type]
    inicio = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_HEALTH_S) as cliente:
            resposta = await cliente.get(url, headers=_cabecalho_de_sondagem(provider))
    except (httpx.HTTPError, httpx.InvalidURL) as erro:
        # A mensagem nomeia o tipo do erro, nunca o cabeçalho que foi enviado.
        return _Sondagem(
            False,
            f"Não respondeu em até {TIMEOUT_HEALTH_S:g}s ({type(erro).__name__}).",
        )

    latencia_ms = int((time.perf_counter() - inicio) * 1000)
    if resposta.status_code >= 400:
        return _Sondagem(False, _motivo_do_status(resposta.status_code, provider), latencia_ms)

    try:
        listados = _modelos_listados(resposta.json())
    except ValueError:
        listados = ()
    return _Sondagem(True, "", latencia_ms, listados)


async def _sondar_todos(providers: tuple[ProviderDeclarado, ...]) -> dict[str, _Sondagem]:
    """Sonda em paralelo: três providers em série seriam três timeouts em fila."""
    resultados = await asyncio.gather(*(_sondar(item) for item in providers))
    return {item.id: sonda for item, sonda in zip(providers, resultados, strict=True)}


def _modelos_declarados(config: AiConfig, provider_id: str) -> list[str]:
    return [modelo.id for modelo in config.modelos if provider_id in modelo.providers]


@global_router.get("/providers", response_model=AiProviderList)
async def listar_providers(config: AiConfig = Depends(get_ai_config)) -> AiProviderList:
    """Os providers declarados e o estado de cada um (REQ-14).

    O estado é o que a tela de configurações mostra: conectado, não
    configurado, desligado ou indisponível. O valor da chave não aparece aqui
    nem mascarado — o que sai é o nome da variável de ambiente (P-05).
    """
    sondaveis = tuple(item for item in config.providers_habilitados() if _chave_presente(item))
    sondagens = await _sondar_todos(sondaveis)

    items = []
    for provider in config.providers:
        sonda = sondagens.get(provider.id)
        if not provider.enabled:
            estado, motivo = "desligado", "Desligado em configs/ai.yml (`enabled: false`)."
        elif not _chave_presente(provider):
            estado, motivo = (
                "nao_configurado",
                f"A variável {provider.api_key_env} não está definida no ambiente.",
            )
        elif sonda is not None and sonda.disponivel:
            estado, motivo = "conectado", ""
        else:
            estado, motivo = "indisponivel", sonda.motivo if sonda else ""
        items.append(
            AiProviderOut(
                id=provider.id,
                type=provider.type,
                enabled=provider.enabled,
                base_url=provider.base_url,
                api_key_env=provider.api_key_env,
                estado=estado,
                motivo=motivo or None,
                modelos=_modelos_declarados(config, provider.id),
            )
        )
    return AiProviderList(items=items, ativo=config.ativo, erro=config.erro or None)


@global_router.get("/models", response_model=AiModelList)
def listar_modelos(config: AiConfig = Depends(get_ai_config)) -> AiModelList:
    """O registro de modelos: capacidades, providers em ordem e faixa de custo.

    Sem `configs/ai.yml` a lista vem vazia com `ativo: false`, e nada quebra.
    """
    return AiModelList(
        items=[
            AiModelOut(
                id=modelo.id,
                model=modelo.model,
                capabilities=list(modelo.capabilities),
                providers=list(modelo.providers),
                cost_tier=modelo.cost_tier,
                context_window=modelo.context_window,
            )
            for modelo in config.modelos
        ],
        ativo=config.ativo,
        erro=config.erro or None,
    )


@global_router.get("/health", response_model=AiHealthOut)
async def saude_dos_providers(config: AiConfig = Depends(get_ai_config)) -> AiHealthOut:
    """Quem responde agora, e o que cada um diz servir (REQ-13).

    Devolve 200 mesmo com provider fora do ar: indisponibilidade é dado, e
    transformá-la em erro da rota faria um serviço de que o painel nem depende
    impedir a tela de abrir (P-06). Só entram os habilitados — provider
    `enabled: false` está fora de toda decisão, e sondá-lo seria ruído.
    """
    habilitados = config.providers_habilitados()
    sondaveis = tuple(item for item in habilitados if _chave_presente(item))
    sondagens = await _sondar_todos(sondaveis)

    items = []
    for provider in habilitados:
        sonda = sondagens.get(provider.id) or _Sondagem(
            False, f"A variável {provider.api_key_env} não está definida no ambiente."
        )
        items.append(
            AiProviderHealthOut(
                id=provider.id,
                type=provider.type,
                disponivel=sonda.disponivel,
                motivo=sonda.motivo or None,
                latencia_ms=sonda.latencia_ms,
                modelos=list(sonda.modelos),
            )
        )
    return AiHealthOut(checked_at=utcnow(), timeout_s=TIMEOUT_HEALTH_S, items=items)


# --- consumo do período ----------------------------------------------------
#
# Uma rota, uma leitura agregada e nenhuma regra de negócio: por isso ela fala
# com `RunRepository` direto, sem serviço no meio. O que existe de decisão aqui
# está em duas linhas — quem é "local" e o que conta como "fallback acionado" —
# e as duas estão comentadas onde acontecem.

#: Janela padrão da tela de consumo. Sete dias é o que responde "como foi a
#: semana", que é a pergunta que a tela existe para responder.
DIAS_DE_CONSUMO_PADRAO = 7


def _providers_locais(config: AiConfig) -> list[str]:
    """Quem é `type: local` no registro — **inclusive o desligado**.

    A linha de `ai_run` não guarda se o provedor era local ou de nuvem, de
    propósito: isso é declaração de `configs/ai.yml`, e congelá-la na linha
    criaria uma cópia que envelhece. Em compensação, a classificação é sempre a
    de *agora*.

    Provider `enabled: false` entra assim mesmo: desligar o Ollama hoje não
    transforma em nuvem o que ele processou ontem — isso inverteria o número que
    a tela usa justamente para mostrar quanto ficou na máquina.
    """
    return [provider.id for provider in config.providers if provider.local]


def _motivo_sem_medicao(config: AiConfig, days: int) -> str:
    """O que falta para o período poder ser medido (**P-02**).

    Sem registro utilizável a resposta é outra: não é que não se usou a IA, é
    que ela não tem como rodar — e dizer "0 chamadas" esconderia exatamente a
    causa.
    """
    if not config.ativo:
        return (
            "A IA não tem registro utilizável (configs/ai.yml): nenhuma execução "
            "pode ser registrada até um provider estar declarado e habilitado."
        )
    return (
        f"Nenhuma execução de IA registrada nos últimos {days} dias. "
        "Os indicadores aparecem depois da primeira pergunta respondida."
    )


@global_router.get("/usage", response_model=AiUsageOut)
def consumo_do_periodo(
    days: int = Query(default=DIAS_DE_CONSUMO_PADRAO, ge=1, le=90),
    session: Session = Depends(get_session),
    config: AiConfig = Depends(get_ai_config),
) -> AiUsageOut:
    """Chamadas, tokens, local × nuvem, custo, latência, falhas e fallbacks.

    Período sem nenhuma tentativa gravada devolve `medido: false` e **todos** os
    indicadores em `null`, com o motivo em texto (**P-02**). O caminho do zero
    não existe aqui: um período sem registro não é um período de graça e sem
    erro, é um período que ninguém mediu.

    Custo e latência seguem anuláveis mesmo com dados: o custo é `null` quando
    nenhum modelo do período tinha preço declarado, e `chamadas_sem_custo` diz
    quantas tentativas ficaram de fora da conta, para a tela poder dizer
    "parcial" em vez de apresentar o total como se fosse completo (REQ-11).
    """
    until = utcnow()
    since = until - timedelta(days=days)
    resumo = RunRepository(session).aggregate(
        since=since, until=until, local_providers=_providers_locais(config)
    )

    if resumo.attempts == 0:
        return AiUsageOut(
            since=since,
            until=until,
            days=days,
            medido=False,
            motivo=_motivo_sem_medicao(config, days),
        )

    return AiUsageOut(
        since=since,
        until=until,
        days=days,
        medido=True,
        indicadores=AiUsageIndicadores(
            chamadas=resumo.attempts,
            perguntas=resumo.questions,
            tokens_in=resumo.tokens_in,
            tokens_out=resumo.tokens_out,
            chamadas_local=resumo.local_attempts,
            tokens_local=resumo.local_tokens,
            chamadas_cloud=resumo.cloud_attempts,
            tokens_cloud=resumo.cloud_tokens,
            # `estimated_cost`, `price_date` e `avg_latency_ms` chegam do
            # repositório já podendo ser `None`, e passam assim: trocar por 0
            # aqui seria desfazer, na última linha do caminho, o cuidado que a
            # tabela e a consulta tiveram desde o começo.
            custo_estimado=resumo.estimated_cost,
            price_date=resumo.price_date,
            chamadas_sem_custo=resumo.attempts_without_cost,
            latencia_media_ms=resumo.avg_latency_ms,
            falhas=resumo.failures,
            fallbacks=resumo.fallbacks,
        ),
    )
