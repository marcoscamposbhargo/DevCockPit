"""Sessão de trabalho, memória e briefing — a Fase 1 do Cockpit AI.

O que estes testes protegem é a promessa da fase: **isto funciona sem IA**. E,
dentro dela, a regra que sustenta tudo o que vier depois — o resumo é montado
do que foi observado, não redigido de memória.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.ai import AiSession, MemoryKind, MemorySource
from app.models.base import utcnow
from app.models.project import ActivityLog, HealthSnapshot, Project
from app.services.briefing_service import BriefingService
from app.services.memory_service import MemoryService
from app.services.session_service import SessionService
from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.unit


@pytest.fixture
def projeto(session: Session) -> Project:
    project = Project(id="p1", name="App Web", path="C:/tmp/app-web")
    session.add(project)
    session.commit()
    return project


class GitFalso:
    """Git dublê: dois estados, antes e depois, e uma lista de commits."""

    def __init__(self, estados=None, commits=None) -> None:  # type: ignore[no-untyped-def]
        self.estados = list(estados or [])
        self._commits = commits or []

    def status(self, project_id, path):  # type: ignore[no-untyped-def]
        return self.estados.pop(0) if self.estados else Estado(is_repo=False)

    def commits(self, project_id, path, limit=20):  # type: ignore[no-untyped-def]
        return self._commits

    def invalidate(self, project_id):  # type: ignore[no-untyped-def]
        pass


class Estado:
    def __init__(self, is_repo=True, branch="main", sha="abc1234", dirty=0) -> None:  # type: ignore[no-untyped-def]
        self.is_repo = is_repo
        self.current_branch = branch
        self.head_sha = sha
        self.dirty_count = dirty


# --- abrir e encerrar -----------------------------------------------------


def test_abrir_registra_o_marco_do_git(session: Session, projeto: Project) -> None:
    servico = SessionService(session, git=GitFalso([Estado(sha="aaa1111", dirty=2)]))

    registro = servico.start(projeto, objective="Terminar o import")

    fatos = SessionService.facts_of(registro)
    assert registro.is_open
    assert registro.objective == "Terminar o import"
    assert fatos.git_start.head_sha == "aaa1111"
    assert fatos.git_start.dirty_count == 2


def test_so_existe_uma_sessao_aberta_por_projeto(session: Session, projeto: Project) -> None:
    """Sessão esquecida aberta por três dias não mede nada."""
    servico = SessionService(session, git=GitFalso([Estado(), Estado(), Estado()]))

    primeira = servico.start(projeto)
    segunda = servico.start(projeto)
    session.flush()

    assert primeira.id != segunda.id
    assert primeira.ended_at is not None, "a anterior é encerrada, não recusada"
    assert servico.current(projeto).id == segunda.id


def test_encerrar_sem_sessao_aberta_recusa_com_instrucao(
    session: Session, projeto: Project
) -> None:
    servico = SessionService(session, git=GitFalso())

    with pytest.raises(ValidationError, match="Inicie uma antes"):
        servico.end(projeto)


# --- o resumo sai dos fatos -----------------------------------------------


def test_resumo_conta_commits_do_periodo(session: Session, projeto: Project) -> None:
    """O corte é pelo sha do início, não por data: rebase e fuso mentem."""
    commits = [
        {"sha": "ddd4444", "subject": "valida entrada"},
        {"sha": "ccc3333", "subject": "extrai serviço"},
        {"sha": "aaa1111", "subject": "commit anterior à sessão"},
    ]
    git = GitFalso([Estado(sha="aaa1111"), Estado(sha="ddd4444", dirty=1)], commits)
    servico = SessionService(session, git=git)

    servico.start(projeto)
    encerrada = servico.end(projeto)

    fatos = SessionService.facts_of(encerrada)
    assert [c["sha"] for c in fatos.commits] == ["ddd4444", "ccc3333"]
    assert "2 commit(s)" in encerrada.summary
    assert "valida entrada" in encerrada.summary
    assert "1 arquivo(s) sem commit" in encerrada.summary


def test_resumo_registra_acoes_e_quedas(session: Session, projeto: Project) -> None:
    servico = SessionService(session, git=GitFalso([Estado(), Estado()]))
    servico.start(projeto)

    session.add(
        ActivityLog(project_id=projeto.id, action="docker.up", status="SUCCESS")
    )
    session.add(
        ActivityLog(project_id=projeto.id, action="server.start", status="FAILED")
    )
    session.add(
        HealthSnapshot(project_id=projeto.id, service_key="backend", state="OFFLINE")
    )
    session.flush()

    encerrada = servico.end(projeto)

    fatos = SessionService.facts_of(encerrada)
    assert len(fatos.actions) == 2
    assert [q["service"] for q in fatos.services_down] == ["backend"]
    assert "1 sem sucesso" in encerrada.summary
    assert "Saiu do ar durante a sessão: backend" in encerrada.summary


def test_resumo_escrito_por_humano_vence_o_montado(
    session: Session, projeto: Project
) -> None:
    """Quem viveu a sessão sabe coisas que log nenhum registra."""
    servico = SessionService(session, git=GitFalso([Estado(), Estado()]))
    servico.start(projeto)

    encerrada = servico.end(projeto, summary="Descobri que o bug era de fuso.")

    assert encerrada.summary == "Descobri que o bug era de fuso."


def test_projeto_sem_git_nao_inventa_marco(session: Session, projeto: Project) -> None:
    servico = SessionService(session, git=None)

    servico.start(projeto)
    encerrada = servico.end(projeto)

    fatos = SessionService.facts_of(encerrada)
    assert fatos.git_start.is_repo is False
    assert fatos.commits == []
    assert "commit" not in encerrada.summary


def test_fatos_ilegiveis_nao_quebram_a_leitura() -> None:
    registro = AiSession(id="s_x", project_id="p1", started_at=utcnow(), facts="{quebrado")

    fatos = SessionService.facts_of(registro)

    assert fatos.commits == []


# --- memória --------------------------------------------------------------


def test_memoria_humana_nasce_confirmada(session: Session, projeto: Project) -> None:
    servico = MemoryService(session)

    registro = servico.write(
        kind=MemoryKind.DECISION.value,
        title="Sessão em vez de JWT",
        body="Refresh token exigiria armazenamento que este projeto não tem.",
        project_id=projeto.id,
    )

    assert registro.is_confirmed, "quem digitou, afirmou"
    assert registro.source == MemorySource.HUMAN.value


def test_sugestao_da_ia_nasce_pendente(session: Session, projeto: Project) -> None:
    servico = MemoryService(session)

    registro = servico.write(
        kind=MemoryKind.ARCHITECTURE.value,
        title="Parece Clean Architecture",
        body="Deduzido da estrutura de pastas.",
        project_id=projeto.id,
        source=MemorySource.AI_SUGGESTED.value,
    )

    assert not registro.is_confirmed
    servico.confirm(registro.id)
    assert registro.is_confirmed
    assert registro.source == MemorySource.HUMAN.value


def test_memoria_do_desenvolvedor_nao_aceita_projeto(
    session: Session, projeto: Project
) -> None:
    servico = MemoryService(session)

    with pytest.raises(ValidationError, match="memória do desenvolvedor"):
        servico.write(
            kind=MemoryKind.PREFERENCE.value,
            title="pytest, não unittest",
            body="",
            project_id=projeto.id,
        )


def test_tipo_desconhecido_e_recusado(session: Session) -> None:
    with pytest.raises(ValidationError, match="Tipo de memória inválido"):
        MemoryService(session).write(kind="chute", title="x", body="")


def test_poda_leva_sugestao_velha_e_poupa_confirmada(
    session: Session, projeto: Project
) -> None:
    servico = MemoryService(session)
    antiga = servico.write(
        kind=MemoryKind.BUG.value,
        title="talvez seja o cache",
        body="",
        project_id=projeto.id,
        source=MemorySource.AI_SUGGESTED.value,
    )
    antiga.created_at = utcnow() - timedelta(days=60)
    confirmada = servico.write(
        kind=MemoryKind.BUG.value, title="é o cache", body="", project_id=projeto.id
    )
    confirmada.created_at = utcnow() - timedelta(days=60)
    session.flush()

    assert servico.prune(days=30) == 1
    restantes = [m.title for m in servico.list(project_id=projeto.id)]
    assert restantes == ["é o cache"]


# --- briefing do dia ------------------------------------------------------


def test_sessao_aberta_vem_primeiro(session: Session) -> None:
    """Sessão aberta é o sinal mais urgente: alguém parou no meio."""
    for indice in range(3):
        session.add(Project(id=f"p{indice}", name=f"Projeto {indice}", path=f"C:/tmp/p{indice}"))
    session.flush()

    sessoes = SessionService(session, git=None)
    parado = session.get(Project, "p0")
    ativo = session.get(Project, "p2")
    encerrada = sessoes.start(parado)
    sessoes.end(parado, next_steps="Implementar validação")
    assert encerrada.ended_at is not None
    sessoes.start(ativo)
    session.flush()

    dados = BriefingService(session).build()

    assert dados.items[0].project_id == "p2"
    assert dados.items[0].open_session is True
    assert "sessão aberta" in dados.items[0].reason
    assert dados.suggestion == "Projeto 2"


def test_proximo_passo_declarado_pesa_mais_que_silencio(session: Session) -> None:
    session.add(Project(id="com-passo", name="Com passo", path="C:/tmp/a"))
    session.add(Project(id="sem-nada", name="Sem nada", path="C:/tmp/b"))
    session.flush()

    sessoes = SessionService(session, git=None)
    alvo = session.get(Project, "com-passo")
    sessoes.start(alvo)
    sessoes.end(alvo, next_steps="Criar o ValidationEngine")
    session.flush()

    dados = BriefingService(session).build()

    assert dados.items[0].project_id == "com-passo"
    assert dados.items[0].next_step == "Criar o ValidationEngine"


def test_projeto_sem_diretorio_fica_de_fora(session: Session) -> None:
    session.add(Project(id="sumiu", name="Sumiu", path="C:/tmp/x", status="MISSING"))
    session.add(Project(id="existe", name="Existe", path="C:/tmp/y"))
    session.flush()

    dados = BriefingService(session).build()

    assert [item.project_id for item in dados.items] == ["existe"]


# --- contrato HTTP --------------------------------------------------------


def test_ciclo_completo_pela_api(client: TestClient, workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace / "api-app"
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    projeto_id = client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()["id"]

    aberta = client.post(
        f"/api/projects/{projeto_id}/sessions/start",
        json={"objective": "Subir o ambiente"},
        headers=WRITE_HEADERS,
    )
    assert aberta.status_code == 200
    assert aberta.json()["is_open"] is True

    client.post(
        f"/api/projects/{projeto_id}/memory",
        json={"kind": "decision", "title": "SQLite basta", "body": "Um usuário só."},
        headers=WRITE_HEADERS,
    )

    encerrada = client.post(
        f"/api/projects/{projeto_id}/sessions/end",
        json={"next_steps": "Escrever os testes"},
        headers=WRITE_HEADERS,
    )
    assert encerrada.status_code == 200
    corpo = encerrada.json()
    assert corpo["is_open"] is False
    assert corpo["summary"], "encerrar sempre produz resumo"
    assert corpo["next_steps"] == "Escrever os testes"

    listagem = client.get(f"/api/projects/{projeto_id}/sessions").json()
    assert listagem["current"] is None
    assert listagem["previous"]["id"] == corpo["id"]

    memoria = client.get(f"/api/projects/{projeto_id}/memory").json()["items"]
    assert memoria[0]["title"] == "SQLite basta"
    assert memoria[0]["confirmed"] is True

    dia = client.get("/api/ai/day").json()
    assert dia["total_projects"] >= 1
    assert any(item["project_id"] == projeto_id for item in dia["items"])


def test_briefing_funciona_sem_nenhuma_sessao(client: TestClient) -> None:
    """A tela do dia precisa valer no primeiro dia de uso, não no décimo."""
    resposta = client.get("/api/ai/day")

    assert resposta.status_code == 200
    assert resposta.json()["items"] == []


def test_memoria_global_e_de_projeto_nao_se_misturam(
    client: TestClient, workspace
) -> None:  # type: ignore[no-untyped-def]
    path = workspace / "outro"
    path.mkdir()
    (path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    projeto_id = client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()["id"]

    client.post(
        "/api/ai/memory",
        json={"kind": "preference", "title": "Comenta o porquê", "body": ""},
        headers=WRITE_HEADERS,
    )
    client.post(
        f"/api/projects/{projeto_id}/memory",
        json={"kind": "context", "title": "É um SaaS de ingressos", "body": ""},
        headers=WRITE_HEADERS,
    )

    globais = client.get("/api/ai/memory").json()["items"]
    do_projeto = client.get(f"/api/projects/{projeto_id}/memory").json()["items"]

    assert [m["title"] for m in globais] == ["Comenta o porquê"]
    assert [m["title"] for m in do_projeto] == ["É um SaaS de ingressos"]


def test_fatos_guardados_sobrevivem_ao_json(session: Session, projeto: Project) -> None:
    """O que vai para o banco precisa voltar igual — é o que a Fase 2 vai ler."""
    servico = SessionService(session, git=GitFalso([Estado(sha="f00"), Estado(sha="bar")]))
    servico.start(projeto)
    encerrada = servico.end(projeto)

    bruto = json.loads(encerrada.facts)

    assert bruto["git_start"]["head_sha"] == "f00"
    assert bruto["git_end"]["head_sha"] == "bar"
    assert "duration_minutes" in bruto
