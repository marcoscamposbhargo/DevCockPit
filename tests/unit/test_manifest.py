"""US-090 e US-091 — manifesto `devcockpit.yml`.

Dois eixos importam aqui: o arquivo nunca pode derrubar o projeto (regra 1 da
spec 08) e nada é escrito na pasta do projeto sem confirmação (FR-112).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WRITE_HEADERS = {"X-DevCockpit-Client": "web", "Origin": "http://127.0.0.1:8765"}

MANIFESTO_COMPLETO = """
version: 1
name: Dashboard Contábil
description: Painel de indicadores
stack:
  - python
  - fastapi
docker:
  enabled: true
  compose_file: docker-compose.yml
  project_name: dashboard-contabil
services:
  frontend:
    label: Frontend
    port: 5173
    url: http://localhost:5173
    health: http://localhost:5173
  database:
    label: PostgreSQL
    port: 5432
    health_kind: TCP
"""


def _cadastra(client, path: Path, **extra):  # type: ignore[no-untyped-def]
    payload = {"path": str(path), "run_detection": False, **extra}
    response = client.post("/api/projects", json=payload, headers=WRITE_HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


# --- leitura tolerante ---


def test_projeto_sem_manifesto_devolve_200(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.get(f"/api/projects/{projeto['id']}/manifest")

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["exists"] is False
    assert corpo["valid"] is False
    assert corpo["diff"] == []


def test_yaml_invalido_vira_aviso_e_nao_erro(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text("version: 1\n  name: [", encoding="utf-8")
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.get(f"/api/projects/{projeto['id']}/manifest")

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["exists"] is True
    assert corpo["valid"] is False
    assert any("YAML inválido" in aviso for aviso in corpo["warnings"])


def test_versao_desconhecida_ignora_arquivo_com_aviso(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(
        "version: 99\nname: Projeto do Futuro\n", encoding="utf-8"
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)

    corpo = client.get(f"/api/projects/{projeto['id']}/manifest").json()

    assert corpo["valid"] is False
    assert any("Versão de schema desconhecida" in aviso for aviso in corpo["warnings"])
    # O nome do banco continua valendo: arquivo ignorado é arquivo ignorado.
    assert client.get(f"/api/projects/{projeto['id']}").json()["name"] != "Projeto do Futuro"


def test_campo_desconhecido_gera_aviso_e_nao_invalida(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(
        "version: 1\nname: Projeto\ncampo_inventado: 42\n", encoding="utf-8"
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)

    corpo = client.get(f"/api/projects/{projeto['id']}/manifest").json()

    assert corpo["valid"] is True
    assert any("campo_inventado" in aviso for aviso in corpo["warnings"])


def test_url_de_host_externo_invalida_o_manifesto(client, sample_project: Path) -> None:
    """Defesa central: manifesto de repo clonado não vira cliente HTTP arbitrário."""
    (sample_project / "devcockpit.yml").write_text(
        "version: 1\nname: Projeto\nservices:\n"
        "  api:\n    health: http://evil.example.com/ping\n",
        encoding="utf-8",
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)

    corpo = client.get(f"/api/projects/{projeto['id']}/manifest").json()

    assert corpo["valid"] is False
    assert any("inválido" in aviso.lower() for aviso in corpo["warnings"])

    recusa = client.post(
        f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS
    )
    assert recusa.status_code == 422


def test_compose_file_que_escapa_do_projeto_e_recusado(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(
        "version: 1\nname: Projeto\ndocker:\n"
        "  enabled: true\n  compose_file: ../../fora/docker-compose.yml\n",
        encoding="utf-8",
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.post(
        f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PATH_NOT_ALLOWED"


# --- importação ---


def test_importa_manifesto_completo(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(MANIFESTO_COMPLETO, encoding="utf-8")
    (sample_project / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.post(
        f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS
    )

    assert response.status_code == 200
    corpo = response.json()
    assert "name" in corpo["applied"]
    assert "docker" in corpo["applied"]
    assert {"service:frontend", "service:database"} <= set(corpo["applied"])

    detalhe = client.get(f"/api/projects/{projeto['id']}").json()
    assert detalhe["name"] == "Dashboard Contábil"
    assert detalhe["description"] == "Painel de indicadores"
    assert {tech["name"] for tech in detalhe["technologies"]} >= {"python", "fastapi"}

    por_chave = {service["key"]: service for service in detalhe["services"]}
    assert por_chave["frontend"]["port"] == 5173
    assert por_chave["frontend"]["health_kind"] == "HTTP"
    assert por_chave["database"]["health_kind"] == "TCP"


def test_importacao_nao_apaga_servico_ausente_no_manifesto(client, sample_project: Path) -> None:
    """FR-112: o que o arquivo não menciona não é resolvido automaticamente."""
    (sample_project / "devcockpit.yml").write_text(MANIFESTO_COMPLETO, encoding="utf-8")
    projeto = _cadastra(client, sample_project, import_manifest=False)

    client.put(
        f"/api/projects/{projeto['id']}/services",
        json={"items": [{"key": "custom", "label": "Custom", "port": 9999}]},
        headers=WRITE_HEADERS,
    )
    client.post(f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS)

    chaves = {
        service["key"]
        for service in client.get(f"/api/projects/{projeto['id']}").json()["services"]
    }
    assert chaves == {"custom", "frontend", "database"}


def test_stack_do_manifesto_sobrevive_a_nova_deteccao(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(
        "version: 1\nname: Projeto\nstack:\n  - kafka\n", encoding="utf-8"
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)
    client.post(f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS)

    client.post(f"/api/projects/{projeto['id']}/detect", headers=WRITE_HEADERS)

    detalhe = client.get(f"/api/projects/{projeto['id']}").json()
    kafka = next(tech for tech in detalhe["technologies"] if tech["name"] == "kafka")
    assert kafka["source"] == "MANUAL"


def test_cadastro_importa_manifesto_quando_existe(client, sample_project: Path) -> None:
    """FR-110: importação é o padrão no cadastro de projeto que já tem o arquivo."""
    (sample_project / "devcockpit.yml").write_text(MANIFESTO_COMPLETO, encoding="utf-8")

    projeto = _cadastra(client, sample_project)

    assert projeto["name"] == "Dashboard Contábil"
    assert {service["key"] for service in projeto["services"]} >= {"frontend", "database"}


def test_cadastro_com_manifesto_quebrado_nao_falha(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text("{{{", encoding="utf-8")

    projeto = _cadastra(client, sample_project)

    assert projeto["id"]


def test_importar_sem_arquivo_devolve_422(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.post(
        f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- exportação ---


def test_exportar_sem_confirmacao_nao_escreve_nada(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.post(
        f"/api/projects/{projeto['id']}/manifest/export",
        json={"confirm": False},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 422
    assert not (sample_project / "devcockpit.yml").exists()


def test_exportar_com_confirmacao_escreve_yaml_valido(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)
    client.put(
        f"/api/projects/{projeto['id']}/services",
        json={
            "items": [
                {
                    "key": "backend",
                    "label": "Backend",
                    "port": 8000,
                    "url": "http://localhost:8000",
                    "health_kind": "HTTP",
                }
            ]
        },
        headers=WRITE_HEADERS,
    )

    response = client.post(
        f"/api/projects/{projeto['id']}/manifest/export",
        json={"confirm": True},
        headers=WRITE_HEADERS,
    )

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["overwritten"] is False
    assert corpo["bytes_written"] > 0

    escrito = (sample_project / "devcockpit.yml").read_text(encoding="utf-8")
    documento = yaml.safe_load(escrito)
    assert documento["version"] == 1
    assert documento["services"]["backend"]["port"] == 8000
    assert escrito.startswith("# devcockpit.yml")


def test_exportar_sobre_arquivo_existente_marca_substituicao(
    client, sample_project: Path
) -> None:
    (sample_project / "devcockpit.yml").write_text("version: 1\nname: Antigo\n", encoding="utf-8")
    projeto = _cadastra(client, sample_project, import_manifest=False)

    corpo = client.post(
        f"/api/projects/{projeto['id']}/manifest/export",
        json={"confirm": True},
        headers=WRITE_HEADERS,
    ).json()

    assert corpo["overwritten"] is True


def test_preview_nao_escreve_arquivo(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)

    response = client.get(f"/api/projects/{projeto['id']}/manifest/preview")

    assert response.status_code == 200
    assert "version: 1" in response.json()["content"]
    assert not (sample_project / "devcockpit.yml").exists()


def test_ida_e_volta_deixa_projeto_em_sincronia(client, sample_project: Path) -> None:
    projeto = _cadastra(client, sample_project, import_manifest=False)
    client.post(
        f"/api/projects/{projeto['id']}/manifest/export",
        json={"confirm": True},
        headers=WRITE_HEADERS,
    )

    corpo = client.get(f"/api/projects/{projeto['id']}/manifest").json()

    assert corpo["valid"] is True
    assert corpo["in_sync"] is True, corpo["diff"]


# --- comparação ---


def test_divergencia_aparece_campo_a_campo_sem_alterar_nada(
    client, sample_project: Path
) -> None:
    (sample_project / "devcockpit.yml").write_text(
        "version: 1\nname: Nome do Arquivo\n", encoding="utf-8"
    )
    projeto = _cadastra(client, sample_project, import_manifest=False)
    nome_antes = client.get(f"/api/projects/{projeto['id']}").json()["name"]

    corpo = client.get(f"/api/projects/{projeto['id']}/manifest").json()

    assert corpo["in_sync"] is False
    campos = {item["field"] for item in corpo["diff"]}
    assert "name" in campos
    nome = next(item for item in corpo["diff"] if item["field"] == "name")
    assert nome["manifest"] == "Nome do Arquivo"
    assert nome["database"] == nome_antes

    # Comparar não altera nada.
    assert client.get(f"/api/projects/{projeto['id']}").json()["name"] == nome_antes


def test_manifesto_registra_auditoria(client, sample_project: Path) -> None:
    (sample_project / "devcockpit.yml").write_text(MANIFESTO_COMPLETO, encoding="utf-8")
    projeto = _cadastra(client, sample_project, import_manifest=False)
    client.post(f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS)
    client.post(
        f"/api/projects/{projeto['id']}/manifest/export",
        json={"confirm": True},
        headers=WRITE_HEADERS,
    )

    acoes = {
        item["action"]
        for item in client.get(f"/api/activity?project_id={projeto['id']}").json()["items"]
    }

    assert {"manifest.import", "manifest.export"} <= acoes


def test_manifesto_nao_importa_porta_ja_ocupada(client, sample_project: Path) -> None:
    """A terceira porta de entrada da mesma tabela.

    A tela recusa porta duplicada e a detecção a pula; a importação de
    manifesto escrevia. Três caminhos para a mesma tabela e a regra vivendo em
    um só — exatamente o formato de defeito que este projeto produz.
    """
    projeto = _cadastra(client, sample_project)
    client.put(
        f"/api/projects/{projeto['id']}/services",
        json={"items": [{"key": "db", "label": "Banco", "port": 5433, "health_kind": "TCP"}]},
        headers=WRITE_HEADERS,
    )

    manifesto = yaml.safe_dump(
        {
            "version": 1,
            "name": "App",
            "services": {"api": {"label": "API", "port": 5433}},
        },
        allow_unicode=True,
    )
    (sample_project / "devcockpit.yml").write_text(manifesto, encoding="utf-8")

    resposta = client.post(
        f"/api/projects/{projeto['id']}/manifest/import", headers=WRITE_HEADERS
    )

    assert resposta.status_code == 422, resposta.text
    assert "5433" in resposta.text

    servicos = client.get(f"/api/projects/{projeto['id']}").json()["services"]
    assert [s["key"] for s in servicos] == ["db"], "nada foi gravado pela metade"
