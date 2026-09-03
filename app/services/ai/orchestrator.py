"""Da frase para uma proposta de ação — regra primeiro, modelo só no empate.

A maioria do que se pede a um painel de desenvolvimento cabe num vocabulário
estreito: "sobe", "desliga", "log", "portas". Resolver isso por regra é
instantâneo e de graça. Num provedor local a diferença não é acadêmica — a
regra responde em milissegundos, o modelo leva de 5 a 25 segundos.

O modelo entra onde a regra não decide, e o que ele devolve **não é
confiança**: é um palpite que passa pelo mesmo funil de validação. Nome fora do
registro, projeto inexistente ou JSON quebrado viram recusa, nunca ação.

Nada aqui executa. A saída é uma `Proposta` que a tela mostra para a pessoa
confirmar, e a confirmação chama a rota que o botão já usava.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass

from app.services.ai.actions import POR_CHAVE, Acao, catalogo
from app.services.ai.providers import AIRequest, Message

logger = logging.getLogger(__name__)

#: Verbos que decidem sozinhos, por ordem de especificidade. O primeiro que
#: casar vence, então o que é mais específico vem antes: "sobe o servidor"
#: precisa ganhar de "sobe", senão viraria `environment.up`.
REGRAS: tuple[tuple[str, str], ...] = (
    (r"\b(sobe|subir|liga|ligar|start)\b.*\bservidor\b", "server.start"),
    (r"\b(para|parar|desliga|desligar|stop)\b.*\bservidor\b", "server.stop"),
    (r"\b(sobe|subir|liga|ligar|start|up)\b", "environment.up"),
    (r"\b(desliga|desligar|para|parar|derruba|down)\b", "environment.down"),
    (r"\b(log|logs|saida|cuspiu)\b", "server.logs"),
    (r"\b(porta|portas|port)\b", "ports.map"),
    (r"\b(container|containers|docker|compose)\b", "docker.ps"),
    (r"\b(git|commit|commitar|branch|alteracao|alteracoes)\b", "git.status"),
    (r"\b(vscode|editor|code)\b", "open.vscode"),
    (r"\bterminal\b", "open.terminal"),
)

INSTRUCAO = """Você é o orquestrador do DevCockpit. Sua única saída é um objeto JSON.

Ações permitidas (use exatamente um destes nomes):
{catalogo}

Projetos cadastrados (id = nome):
{projetos}

Responda SOMENTE com JSON:
{{"action": "<nome exato da lista>", "project_id": "<id exato da lista>",
  "reason": "<uma frase curta>"}}

Se a frase não indicar um projeto da lista, use "project_id": null.
Se nenhuma ação da lista servir, use "action": null."""


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para casar 'ALTERAÇÃO' com 'alteracao'.

    Pública porque `classifier.py` normaliza do mesmo jeito, e duas versões
    disso divergiriam na primeira palavra com cedilha.
    """
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


@dataclass
class Proposta:
    acao: Acao
    project_id: str | None
    project_name: str | None
    reason: str
    #: "regra" ou "modelo" — a tela não mostra, mas a auditoria mostra, e é o
    #: que permite saber depois quanto do sistema depende do modelo.
    origem: str

    @property
    def describe(self) -> str:
        return self.acao.describe.format(projeto=self.project_name or "este projeto")

    def to_dict(self) -> dict:
        return {
            "action": self.acao.key,
            "label": self.acao.label,
            "describe": self.describe,
            "classe": str(self.acao.classe),
            "needs_confirmation": self.acao.needs_confirmation,
            "method": self.acao.method,
            "path": self.acao.path.format(project_id=self.project_id or ""),
            "project_id": self.project_id,
            "project_name": self.project_name,
            "reason": self.reason,
            "origem": self.origem,
        }


class Orchestrator:
    def __init__(self, projetos: list[tuple[str, str]]) -> None:
        #: `(id, nome)` de tudo que está cadastrado. Só isso — nome e id são
        #: baratos, e mandar mais que isso ao modelo é pagar leitura à toa.
        self.projetos = projetos
        self._por_id = dict(projetos)

    # --- caminho 1: regra ---

    def _por_regra(self, pergunta: str) -> Acao | None:
        texto = normalizar(pergunta)
        for padrao, chave in REGRAS:
            if re.search(padrao, texto):
                return POR_CHAVE[chave]
        return None

    def _projeto_citado(self, pergunta: str) -> tuple[str, str] | None:
        """Projeto cujo nome aparece na frase. Ambíguo devolve `None`.

        Casa pelo nome e pelo id, sem acento e em minúsculas, e exige o mais
        longo quando dois casam — "OperaLaby SaaS" tem que ganhar de
        "OperaLaby" numa frase que diz "operalaby saas".

        Se dois projetos casam com o mesmo trecho, ninguém vence: propor no
        projeto errado é pior que não propor.
        """
        texto = normalizar(pergunta)
        casados = [
            (pid, nome)
            for pid, nome in self.projetos
            if normalizar(nome) in texto or normalizar(pid) in texto
        ]
        if not casados:
            return None
        if len(casados) == 1:
            return casados[0]

        # Empate: vence o nome mais longo, mas só se for estritamente maior.
        casados.sort(key=lambda p: len(p[1]), reverse=True)
        if len(casados[0][1]) == len(casados[1][1]):
            return None
        return casados[0]

    # --- caminho 2: modelo ---

    def _por_modelo(self, pergunta: str, provedor) -> dict | None:  # type: ignore[no-untyped-def]
        catalogo_projetos = "\n".join(f"{pid} = {nome}" for pid, nome in self.projetos)
        pedido = AIRequest(
            messages=[Message(role="user", content=pergunta)],
            system=INSTRUCAO.format(catalogo=catalogo(), projetos=catalogo_projetos),
            # Uma proposta cabe em poucas dezenas de tokens. O teto existe para
            # o caso em que o modelo resolve escrever prosa: melhor cortar do
            # que esperar dois minutos por algo que vai ser descartado.
            max_output_tokens=200,
            temperature=0,
        )
        bruto = provedor.complete(pedido).text.strip()

        # Modelo pequeno às vezes embrulha o JSON em cerca de código, mesmo
        # mandado não fazer. Descartar por causa disso seria perder uma
        # resposta correta por causa de dois acentos graves.
        if bruto.startswith("```"):
            bruto = bruto.strip("`").lstrip("json").strip()

        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            logger.info(
                "orquestrador: resposta não era JSON",
                extra={"extra_fields": {"bruto": bruto[:120]}},
            )
            return None

    # --- entrada ---

    def propose(self, pergunta: str, provedor=None) -> Proposta | None:  # type: ignore[no-untyped-def]
        """Uma proposta validada, ou `None` quando nada da lista serve.

        `None` é resposta legítima e frequente: a maior parte do que se digita
        na pergunta rápida é dúvida de terminal, não ordem. Propor ação para
        "como desfaço um commit?" seria transformar pergunta em comando.
        """
        acao = self._por_regra(pergunta)
        if acao is not None:
            citado = self._projeto_citado(pergunta)
            if citado is not None or not acao.needs_project:
                pid, nome = citado or (None, None)
                return Proposta(acao, pid, nome, "reconhecido pelo que você escreveu", "regra")
            # Regra achou o verbo mas não o projeto. Cai para o modelo, que sabe
            # lidar com apelido e erro de digitação — foi medido acertando
            # "smartdah" para `smartdash`.

        if provedor is None:
            return None

        obj = self._por_modelo(pergunta, provedor)
        if not obj:
            return None
        return self._validar(obj)

    def _validar(self, obj: dict) -> Proposta | None:
        """O funil que separa palpite de ação.

        Tudo o que o modelo diz passa por aqui. Nome fora do registro é o sinal
        de alucinação que `docs/07-security-model.md` trata como o mais
        importante do sistema — e vira `None`, nunca uma ação aproximada.
        """
        chave = obj.get("action")
        if not chave or chave not in POR_CHAVE:
            if chave:
                logger.warning(
                    "orquestrador: ação fora do registro",
                    extra={"extra_fields": {"acao": str(chave)[:60]}},
                )
            return None

        acao = POR_CHAVE[chave]
        pid = obj.get("project_id") or None
        if pid is not None and pid not in self._por_id:
            logger.warning(
                "orquestrador: projeto inexistente",
                extra={"extra_fields": {"project_id": str(pid)[:60]}},
            )
            return None
        if acao.needs_project and pid is None:
            # Ação que precisa de projeto sem projeto resolvido não é oferecida.
            # O usuário pergunta de novo dizendo o nome, e isso custa menos que
            # ligar o ambiente errado.
            return None

        razao = str(obj.get("reason") or "").strip()[:200] or "proposto pelo modelo"
        return Proposta(acao, pid, self._por_id.get(pid or ""), razao, "modelo")
