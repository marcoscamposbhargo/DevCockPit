"""Fase 3.6 — a auditoria diz quem pediu a ação, e não acredita no cliente.

O que estes testes protegem não é uma funcionalidade: é a honestidade do log.
Até a 3.4, ação proposta pela IA e confirmada pela pessoa era gravada como ação
da pessoa. Verdade parcial num painel cuja tese é "fato, não palpite".

A tentação era deixar o cliente mandar `actor=ai`. Metade destes testes existe
para provar que essa porta está fechada.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.base import utcnow
from app.services.ai import propostas
from app.services.ai.propostas import REGISTRO, RegistroDePropostas
from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.unit


# --- o registro de propostas -----------------------------------------------


def _registrar(registro: RegistroDePropostas, **extra):
    dados = {
        "action": "server.logs",
        "method": "GET",
        "path": "/api/projects/alpha/server/logs",
        "project_id": "alpha",
        "reason": "reconhecido pelo que você escreveu",
        "origem": "regra",
    }
    dados.update(extra)
    return registro.registrar(**dados)


def test_bilhete_vale_uma_vez_só() -> None:
    """Bilhete reutilizável transformaria uma confirmação em N execuções."""
    registro = RegistroDePropostas()
    pendente = _registrar(registro)

    primeira = registro.resgatar(
        pendente.id, method="GET", path="/api/projects/alpha/server/logs"
    )
    segunda = registro.resgatar(
        pendente.id, method="GET", path="/api/projects/alpha/server/logs"
    )

    assert primeira is not None
    assert segunda is None


def test_bilhete_não_vale_para_outra_rota() -> None:
    """É o que impede "ver o log do alpha" autorizar "desligar o beta"."""
    registro = RegistroDePropostas()
    pendente = _registrar(registro)

    outra_rota = "/api/projects/beta/server/stop"
    mesma_rota = "/api/projects/alpha/server/logs"

    assert registro.resgatar(pendente.id, method="POST", path=outra_rota) is None
    assert registro.resgatar(pendente.id, method="POST", path=mesma_rota) is None
    # O bilhete continua válido para a rota certa: recusar não é consumir.
    assert registro.resgatar(pendente.id, method="GET", path=mesma_rota)


def test_bilhete_inventado_não_resgata_nada() -> None:
    registro = RegistroDePropostas()
    _registrar(registro)

    rota = "/api/projects/alpha/server/logs"

    assert registro.resgatar("nao-existe", method="GET", path=rota) is None
    assert registro.resgatar("", method="GET", path=rota) is None


def test_bilhete_vencido_não_resgata(monkeypatch: pytest.MonkeyPatch) -> None:
    registro = RegistroDePropostas()
    pendente = _registrar(registro)

    futuro = utcnow() + propostas.VALIDADE + timedelta(seconds=1)
    monkeypatch.setattr(propostas, "utcnow", lambda: futuro)

    assert registro.resgatar(pendente.id, method="GET", path=pendente.path) is None


def test_registro_não_cresce_sem_limite() -> None:
    """Chamar /ai/propose em laço não pode virar depósito de memória."""
    registro = RegistroDePropostas()
    for i in range(propostas.TETO + 20):
        _registrar(registro, path=f"/api/projects/p{i}/server/logs")

    assert len(registro) <= propostas.TETO


# --- ponta a ponta, pela API ------------------------------------------------


def _criar_projeto(client: TestClient, caminho) -> dict:
    resposta = client.post("/api/projects", json={"path": str(caminho)}, headers=WRITE_HEADERS)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _acao_auditada(client: TestClient, projeto_id: str, **cabecalhos) -> None:
    """Uma ação que **grava auditoria e não executa comando nenhum**.

    `open/folder` seria mais parecido com o uso real, mas abre o Explorer de
    verdade a cada rodada da suíte. Renomear um projeto passa exatamente pelo
    mesmo caminho de auditoria sem tocar na máquina.
    """
    resposta = client.patch(
        f"/api/projects/{projeto_id}",
        json={"description": "auditoria"},
        headers={**WRITE_HEADERS, **cabecalhos},
    )
    assert resposta.status_code == 200, resposta.text


def test_acao_sem_bilhete_e_gravada_como_do_usuario(client: TestClient, sample_project) -> None:
    projeto = _criar_projeto(client, sample_project)

    _acao_auditada(client, projeto["id"])

    entrada = client.get("/api/activity", params={"limit": 1}).json()["items"][0]
    assert entrada["action"] == "project.update"
    assert entrada["actor"] == "user"
    assert entrada["reason"] is None


def test_bilhete_forjado_nao_vira_autoria_de_ia(client: TestClient, sample_project) -> None:
    """O caminho que este mecanismo inteiro existe para fechar.

    Se bastasse o cliente mandar um cabeçalho, o log de auditoria estaria
    confiando no auditado.
    """
    projeto = _criar_projeto(client, sample_project)

    _acao_auditada(client, projeto["id"], **{"X-DevCockpit-Proposal": "bilhete-inventado"})

    entrada = client.get("/api/activity", params={"limit": 1}).json()["items"][0]
    assert entrada["actor"] == "user", "cabeçalho do cliente não pode declarar autoria"


def test_propose_emite_bilhete(client: TestClient, sample_project) -> None:
    """A regra resolve a frase e o servidor entrega o bilhete junto."""
    projeto = _criar_projeto(client, sample_project)

    proposta = client.post(
        "/api/ai/propose",
        json={"question": f"git do {projeto['id']}", "model": "default"},
        headers=WRITE_HEADERS,
    ).json()["proposal"]

    assert proposta is not None, "a regra deveria ter reconhecido a frase"
    assert proposta["id"], "sem bilhete, a auditoria não teria como reconhecer a autoria"
    assert proposta["action"] == "git.status"


def test_proposta_confirmada_fica_marcada_como_da_ia(client: TestClient, sample_project) -> None:
    projeto = _criar_projeto(client, sample_project)

    # A proposta é registrada como o servidor a registra em `/ai/propose`; o que
    # este teste cobre é o outro lado, da confirmação até a linha do log.
    pendente = REGISTRO.registrar(
        action="project.update",
        method="PATCH",
        path=f"/api/projects/{projeto['id']}",
        project_id=projeto["id"],
        reason="reconhecido pelo que você escreveu",
        origem="regra",
    )

    _acao_auditada(client, projeto["id"], **{"X-DevCockpit-Proposal": pendente.id})

    entrada = client.get("/api/activity", params={"limit": 1}).json()["items"][0]
    assert entrada["actor"] == "ai"
    assert entrada["agent"] == "project.update"
    assert "regra" in (entrada["reason"] or ""), "o log precisa dizer quem decidiu"


def test_bilhete_serve_uma_vez_tambem_pela_api(client: TestClient, sample_project) -> None:
    """Confirmar uma vez não autoriza executar duas."""
    projeto = _criar_projeto(client, sample_project)

    pendente = REGISTRO.registrar(
        action="project.update",
        method="PATCH",
        path=f"/api/projects/{projeto['id']}",
        project_id=projeto["id"],
        reason="reconhecido pelo que você escreveu",
        origem="regra",
    )

    _acao_auditada(client, projeto["id"], **{"X-DevCockpit-Proposal": pendente.id})
    _acao_auditada(client, projeto["id"], **{"X-DevCockpit-Proposal": pendente.id})

    itens = client.get("/api/activity", params={"limit": 2}).json()["items"]
    assert [e["actor"] for e in itens] == ["user", "ai"], "a segunda vez é ação da pessoa"


def test_filtro_por_autor_separa_o_que_a_ia_fez(client: TestClient, sample_project) -> None:
    projeto = _criar_projeto(client, sample_project)
    _acao_auditada(client, projeto["id"])

    so_ia = client.get("/api/activity", params={"actor": "ai"}).json()
    so_usuario = client.get("/api/activity", params={"actor": "user"}).json()

    assert so_ia["total"] == 0
    assert so_usuario["total"] >= 1


# --- os atalhos do especialista (Fase 3.2) ---------------------------------


def test_atalho_que_precisa_de_projeto_some_quando_nao_ha_um(client: TestClient) -> None:
    """Ação de projeto, sem projeto, seria proposta no vazio. A global fica."""
    dados = client.get("/api/ai/specialists").json()

    oferecidos = {a["action"] for p in dados["items"] for a in p["atalhos"]}
    assert "environment.up" not in oferecidos, "ação de projeto sem projeto"
    assert "ports.map" in oferecidos, "o mapa de portas é da máquina, não do projeto"
    assert dados["padrao"] == "fullstack"


def test_atalho_ja_vem_com_bilhete_e_caminho_resolvido(
    client: TestClient, sample_project
) -> None:
    projeto = _criar_projeto(client, sample_project)

    dados = client.get("/api/ai/specialists", params={"project_id": projeto["id"]}).json()
    devops = next(p for p in dados["items"] if p["key"] == "devops")

    assert devops["atalhos"], "com projeto, o DevOps tem botões"
    for atalho in devops["atalhos"]:
        assert atalho["id"], "sem bilhete, o clique não teria como ser marcado como da IA"
        assert "{project_id}" not in atalho["path"], "o cliente não monta caminho (D-13)"
        assert atalho["path"].startswith("/api/")

    # `ports.map` é da máquina e não leva projeto no caminho; `server.logs` é
    # do projeto e leva. As duas formas convivem na mesma barra de atalhos.
    do_projeto = next(a for a in devops["atalhos"] if a["action"] == "server.logs")
    assert projeto["id"] in do_projeto["path"]


def test_o_clique_no_atalho_e_auditado_como_acao_da_ia(
    client: TestClient, sample_project
) -> None:
    """O botão do especialista não é um atalho para fora da auditoria."""
    projeto = _criar_projeto(client, sample_project)

    pendente = REGISTRO.registrar(
        action="project.update",
        method="PATCH",
        path=f"/api/projects/{projeto['id']}",
        project_id=projeto["id"],
        reason="atalho do especialista",
        origem="atalho",
    )
    _acao_auditada(client, projeto["id"], **{"X-DevCockpit-Proposal": pendente.id})

    entrada = client.get("/api/activity", params={"limit": 1}).json()["items"][0]
    assert entrada["actor"] == "ai"
    assert "atalho" in (entrada["reason"] or "")
