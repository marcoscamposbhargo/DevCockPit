"""O funil que separa palpite de ação.

O que se protege aqui não é a qualidade da sugestão — é a garantia de que nada
fora do registro fechado vira ação, e de que uma ação nunca cai no projeto
errado. As duas falhas são de classes diferentes: a primeira é o modelo
alucinando capacidade, a segunda é o modelo acertando a intenção e errando o
alvo. A segunda é pior, porque parece que funcionou.
"""

from __future__ import annotations

import pytest

from app.services.ai.actions import ACOES, POR_CHAVE, Classe
from app.services.ai.orchestrator import Orchestrator

pytestmark = pytest.mark.unit

PROJETOS = [
    ("app-ingresso", "APP INGRESSO"),
    ("kiteasy", "kiteasy"),
    ("zapcrm", "ZapCRM"),
    ("operalaby-saas", "OperaLaby SaaS"),
    ("operalaby-site", "OperaLaby Site"),
]


@pytest.fixture
def orq() -> Orchestrator:
    return Orchestrator(PROJETOS)


class ProvedorFalso:
    """Devolve o JSON que lhe mandarem, como o modelo devolveria."""

    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.pedidos: list = []

    def complete(self, request):  # type: ignore[no-untyped-def]
        self.pedidos.append(request)
        return type("R", (), {"text": self.texto})()


# --- o registro ------------------------------------------------------------


def test_toda_acao_tem_rota_e_descricao() -> None:
    """Ação sem rota é promessa que a tela não consegue cumprir."""
    for acao in ACOES:
        assert acao.path, f"{acao.key} sem rota"
        assert acao.method in ("GET", "POST"), f"{acao.key} com método estranho"
        assert acao.describe, f"{acao.key} sem texto de confirmação"
        if acao.needs_project:
            assert "{project_id}" in acao.path, f"{acao.key} precisa de projeto e não usa o id"


def test_so_leitura_dispensa_confirmacao() -> None:
    """A regra do sistema em uma linha: o que muda estado, pergunta antes."""
    for acao in ACOES:
        assert acao.needs_confirmation == (acao.classe is not Classe.READ)


def test_ligar_ambiente_e_sensivel() -> None:
    """Subir ambiente mexe em container e porta: nunca é SAFE."""
    assert POR_CHAVE["environment.up"].classe is Classe.SENSITIVE_WRITE
    assert POR_CHAVE["environment.up"].needs_confirmation


# --- caminho da regra ------------------------------------------------------


@pytest.mark.parametrize(
    ("frase", "esperado", "projeto"),
    [
        ("sobe o kiteasy", "environment.up", "kiteasy"),
        ("Sobe o ambiente do APP INGRESSO", "environment.up", "app-ingresso"),
        ("desliga o zapcrm", "environment.down", "zapcrm"),
        ("sobe o servidor do kiteasy", "server.start", "kiteasy"),
        ("para o servidor do kiteasy", "server.stop", "kiteasy"),
        ("quem esta usando as portas?", "ports.map", None),
    ],
)
def test_regra_resolve_sem_modelo(
    orq: Orchestrator, frase: str, esperado: str, projeto: str | None
) -> None:
    """O caminho comum não toca no modelo.

    Não é economia de tokens — num provedor local é a diferença entre 0,2 s e
    15 s, que é a diferença entre usar e não usar.
    """
    proposta = orq.propose(frase)

    assert proposta is not None
    assert proposta.acao.key == esperado
    assert proposta.project_id == projeto
    assert proposta.origem == "regra"


def test_servidor_ganha_de_ambiente(orq: Orchestrator) -> None:
    """"sobe o servidor" não pode virar "sobe o ambiente".

    São ações diferentes: uma sobe containers, a outra não. A ordem das regras
    é o que garante isso, e ordem de regra é o tipo de coisa que quebra em
    silêncio numa refatoração.
    """
    assert orq.propose("sobe o servidor do kiteasy").acao.key == "server.start"
    assert orq.propose("sobe o kiteasy").acao.key == "environment.up"


def test_nome_ambiguo_nao_vira_proposta(orq: Orchestrator) -> None:
    """Dois projetos chamados "OperaLaby ..." e a frase diz só "operalaby".

    Sem provedor, a regra desiste em vez de escolher um. Ligar o ambiente do
    projeto errado é o pior erro que este recurso pode cometer, porque parece
    que funcionou.
    """
    assert orq.propose("sobe o operalaby") is None


def test_pergunta_nao_vira_ordem(orq: Orchestrator) -> None:
    """"como desfaço um commit?" é dúvida, e dúvida não move nada."""
    assert orq.propose("como faco para instalar o docker?") is None


# --- caminho do modelo -----------------------------------------------------


def test_modelo_resolve_o_que_a_regra_nao_resolveu(orq: Orchestrator) -> None:
    provedor = ProvedorFalso(
        '{"action": "environment.up", "project_id": "kiteasy", "reason": "voce pediu"}'
    )

    proposta = orq.propose("bota o kit easy no ar", provedor)

    assert proposta is not None
    assert proposta.acao.key == "environment.up"
    assert proposta.project_id == "kiteasy"
    assert proposta.origem == "modelo"


def test_acao_fora_do_registro_e_recusada(orq: Orchestrator) -> None:
    """A defesa D-A3 em um teste.

    O modelo pedindo `deploy.production` não é um pedido a ser negociado: é
    capacidade que não existe. Vira `None`, nunca uma ação parecida.
    """
    provedor = ProvedorFalso(
        '{"action": "deploy.production", "project_id": "kiteasy", "reason": "subir"}'
    )

    assert orq.propose("faz o deploy em producao", provedor) is None


def test_projeto_inventado_e_recusado(orq: Orchestrator) -> None:
    """Ação válida no projeto errado é pior que ação nenhuma."""
    provedor = ProvedorFalso(
        '{"action": "environment.up", "project_id": "folha-de-pagamento", "reason": "x"}'
    )

    assert orq.propose("sobe o sistema de folha", provedor) is None


def test_acao_que_precisa_de_projeto_sem_projeto_e_recusada(orq: Orchestrator) -> None:
    provedor = ProvedorFalso('{"action": "environment.up", "project_id": null, "reason": "x"}')

    assert orq.propose("bota isso no ar", provedor) is None


def test_json_quebrado_nao_derruba_nada(orq: Orchestrator) -> None:
    """Modelo pequeno escreve prosa quando devia escrever JSON."""
    provedor = ProvedorFalso("Claro! Vou subir o ambiente pra voce.")

    assert orq.propose("bota isso no ar", provedor) is None


def test_json_em_cerca_de_codigo_ainda_vale(orq: Orchestrator) -> None:
    """Descartar por causa de dois acentos graves seria perder o acerto."""
    provedor = ProvedorFalso(
        '```json\n{"action": "ports.map", "project_id": null, "reason": "x"}\n```'
    )

    proposta = orq.propose("me da o mapa de coisas ocupadas", provedor)

    assert proposta is not None
    assert proposta.acao.key == "ports.map"


def test_acao_nula_e_resposta_legitima(orq: Orchestrator) -> None:
    """"nenhuma serve" é o que se espera na maior parte das frases."""
    provedor = ProvedorFalso('{"action": null, "reason": "nao e uma ordem"}')

    assert orq.propose("qual a capital da franca?", provedor) is None


# --- o que a tela recebe ---------------------------------------------------


def test_proposta_leva_a_rota_do_botao(orq: Orchestrator) -> None:
    """A tela chama a mesma rota do botão — a IA não abre caminho novo."""
    dados = orq.propose("sobe o kiteasy").to_dict()

    assert dados["path"] == "/api/projects/kiteasy/environment/up"
    assert dados["method"] == "POST"
    assert dados["needs_confirmation"] is True


def test_texto_de_confirmacao_nomeia_o_projeto(orq: Orchestrator) -> None:
    """Quem confirma precisa ver em qual projeto, não só o quê."""
    assert "kiteasy" in orq.propose("sobe o kiteasy").describe


# --- contrato HTTP ---------------------------------------------------------


@pytest.mark.api
def test_propor_exige_guard_de_escrita(client) -> None:  # type: ignore[no-untyped-def]
    """Propor não executa, mas é POST: entra na mesma disciplina do resto."""
    assert client.post("/api/ai/propose", json={"question": "sobe o x"}).status_code == 403


@pytest.mark.api
def test_regra_funciona_com_a_ia_desligada(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """"sobe o <projeto>" não deveria depender de haver modelo configurado.

    É a diferença entre um atalho que funciona sempre e um que só funciona
    quando o Ollama está aberto. A regra é código, não inferência.
    """
    from tests.conftest import WRITE_HEADERS

    caminho = workspace / "kiteasy"
    caminho.mkdir()
    (caminho / "package.json").write_text('{"scripts":{"dev":"vite"}}', encoding="utf-8")
    pid = client.post(
        "/api/projects", json={"path": str(caminho)}, headers=WRITE_HEADERS
    ).json()["id"]

    resposta = client.post(
        "/api/ai/propose", json={"question": f"sobe o {pid}"}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 200
    proposta = resposta.json()["proposal"]
    assert proposta["action"] == "environment.up"
    assert proposta["project_id"] == pid
    assert proposta["origem"] == "regra"
    assert proposta["needs_confirmation"] is True


@pytest.mark.api
def test_sem_modelo_e_sem_regra_devolve_o_motivo(client) -> None:  # type: ignore[no-untyped-def]
    """IA desligada e frase que a regra não entende: a tela recebe explicação.

    Nunca um erro de tela: dependência ausente vira texto (NFR-060).
    """
    from tests.conftest import WRITE_HEADERS

    resposta = client.post(
        "/api/ai/propose",
        json={"question": "qual a capital da franca?"},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 200
    assert resposta.json()["proposal"] is None
    assert resposta.json()["message"]
