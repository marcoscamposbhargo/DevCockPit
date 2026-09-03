"""Registro declarativo de providers e modelos, lido de `configs/ai.yml`.

Hoje a camada de modelo cabe em duas variáveis de ambiente: um provider e um
nome de modelo. Isso responde "com quem falo", nunca "qual modelo serve para
qual tarefa, quanto custa e quem tenta quando o primeiro cai". Essas perguntas
são de catálogo, e catálogo cabe mal em `.env`: são listas, com ordem, e a
ordem importa.

O arquivo é **opcional** de propósito. Sem ele o Cockpit AI se comporta como
antes desta mudança, montando um provider único a partir do `.env` (REQ-04) —
uma instalação existente não pode quebrar na primeira atualização por causa de
um arquivo que ela nunca teve.

O que nunca entra aqui é o valor de uma chave. O arquivo nomeia a variável de
ambiente (`api_key_env`) e nada mais; a carga recusa qualquer campo que se
pareça com segredo, porque um arquivo de configuração é copiado, versionado e
colado em issue com muito mais naturalidade que um `.env` (P-05, defesa D-A5).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)


class AiConfigInvalida(DomainError):
    """Erro de carga do registro. Sempre nomeia o arquivo que o causou."""

    code = "AI_CONFIG_INVALID"
    status_code = 500
    default_message = "O registro de IA está inválido."


#: Nomes de campo que só podem existir como referência ao ambiente. `api_key`
#: não está aqui por engano: é justamente o nome mais provável de aparecer com
#: o valor dentro. O aceito é `api_key_env`, que carrega o *nome* da variável.
CAMPOS_DE_SEGREDO = frozenset(
    {"api_key", "apikey", "api-key", "key", "token", "secret", "password", "chave", "senha"}
)

#: Prefixos que denunciam uma chave colada no arquivo. Lista explícita, não
#: heurística de entropia: um falso positivo aqui trava a inicialização da IA,
#: e recusar `sk-...` cobre OpenAI, DeepSeek e Moonshot, que são os que este
#: ciclo declara.
PADROES_DE_SEGREDO = (
    re.compile(r"^sk[-_]"),
    re.compile(r"^ghp_|^gho_|^github_pat_"),
    re.compile(r"^xox[baprs]-"),
    re.compile(r"^AIza[0-9A-Za-z_-]{10,}$"),
    re.compile(r"^bearer\s+\S", re.IGNORECASE),
)

TIPOS_DE_PROVIDER = frozenset({"local", "cloud"})
NIVEIS_DE_CUSTO = frozenset({"free", "low", "high"})


@dataclass(frozen=True)
class ProviderDeclarado:
    """Quem serve modelo. `api_key_env` é o nome da variável, nunca o valor."""

    id: str
    enabled: bool
    type: str  # local | cloud
    base_url: str
    api_key_env: str = ""

    @property
    def local(self) -> bool:
        return self.type == "local"


@dataclass(frozen=True)
class ModeloDeclarado:
    """Identificador lógico nosso, nome real do fornecedor, e para que serve.

    A separação entre `id` e `model` é o que permite corrigir o nome real do
    modelo — que muda com o fornecedor — sem tocar em nada que o referencie.
    """

    id: str
    model: str
    capabilities: tuple[str, ...]
    providers: tuple[str, ...]
    cost_tier: str
    context_window: int = 0


@dataclass(frozen=True)
class Preco:
    """Preço por milhão de tokens, com a data em que foi anotado.

    A data não é enfeite: preço de modelo muda, e um custo exibido sem dizer de
    quando é o preço afirma o que não mediu (P-02). Preço ausente vira
    `estimated_cost = null`, nunca zero.
    """

    input_por_milhao: float
    output_por_milhao: float
    anotado_em: str


@dataclass(frozen=True)
class Roteamento:
    """Limiares do router. São configuração, não constante espalhada (REQ-07)."""

    limiar_complexidade: int = 40
    modelo_padrao: str = ""


class AiConfig:
    """O registro carregado. Vazio é estado normal, não falha."""

    def __init__(
        self,
        providers: tuple[ProviderDeclarado, ...] = (),
        modelos: tuple[ModeloDeclarado, ...] = (),
        precos: dict[str, Preco] | None = None,
        fallback: tuple[str, ...] = (),
        roteamento: Roteamento | None = None,
        origem: Path | None = None,
        erro: str = "",
    ) -> None:
        self.providers = providers
        self.modelos = modelos
        self.precos = dict(precos or {})
        self.fallback = fallback
        self.roteamento = roteamento or Roteamento()
        self.origem = origem
        #: Mensagem da carga que falhou, para a tela dizer *por que* a IA está
        #: sem registro em vez de só dizer que está.
        self.erro = erro

    @property
    def ativo(self) -> bool:
        """Há registro utilizável? Arquivo ausente ou inválido responde não."""
        return not self.erro and bool(self.providers)

    # --- consultas -------------------------------------------------------

    def provider(self, provider_id: str) -> ProviderDeclarado | None:
        return next((item for item in self.providers if item.id == provider_id), None)

    def modelo(self, modelo_id: str) -> ModeloDeclarado | None:
        return next((item for item in self.modelos if item.id == modelo_id), None)

    def providers_habilitados(self) -> tuple[ProviderDeclarado, ...]:
        return tuple(item for item in self.providers if item.enabled)

    def providers_do_modelo(self, modelo_id: str) -> tuple[ProviderDeclarado, ...]:
        """Quem sabe servir o modelo, na ordem declarada e só os habilitados.

        A ordem é a preferência de quem escreveu o arquivo; o runner consome de
        cima para baixo.
        """
        modelo = self.modelo(modelo_id)
        if modelo is None:
            return ()
        candidatos = (self.provider(nome) for nome in modelo.providers)
        return tuple(item for item in candidatos if item is not None and item.enabled)

    def modelos_por_capacidade(self, capacidade: str) -> tuple[ModeloDeclarado, ...]:
        """Modelos que declaram a capacidade e ainda têm provider de pé.

        Modelo cujos providers estão todos desligados não aparece: provider com
        `enabled: false` não participa de decisão de roteamento nenhuma
        (REQ-01), e devolvê-lo aqui só empurraria a exclusão para quem chama.
        """
        return tuple(
            modelo
            for modelo in self.modelos
            if capacidade in modelo.capabilities and self.providers_do_modelo(modelo.id)
        )

    def preco(self, modelo_id: str) -> Preco | None:
        """Preço declarado, ou `None` quando não há — nunca um zero de aparência."""
        return self.precos.get(modelo_id)

    def cadeia_fallback(self) -> tuple[ModeloDeclarado, ...]:
        """A cadeia declarada, já sem os modelos que não têm provider de pé."""
        modelos = (self.modelo(nome) for nome in self.fallback)
        return tuple(
            modelo
            for modelo in modelos
            if modelo is not None and self.providers_do_modelo(modelo.id)
        )

    # --- carga -----------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> AiConfig:
        """Lê o arquivo. Ausente devolve registro vazio; inválido levanta.

        Levantar em vez de degradar em silêncio é decisão de REQ-03: um arquivo
        com segredo dentro precisa de alguém corrigindo, não de um aviso que
        ninguém lê. Quem chama pela fábrica não sente o erro na inicialização —
        `get_ai_config` o converte em registro vazio com motivo.
        """
        if not path.exists():
            return cls()

        try:
            bruto = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as exc:
            raise AiConfigInvalida(f"Não consegui ler {path}: {exc}") from exc

        if not isinstance(bruto, dict):
            raise AiConfigInvalida(f"{path} não descreve um mapeamento de configuração.")

        _recusar_segredo(bruto, path)

        providers = tuple(_ler_provider(item, path) for item in _lista(bruto, "providers", path))
        _recusar_duplicado([item.id for item in providers], "provider", path)

        modelos = tuple(_ler_modelo(item, path) for item in _lista(bruto, "modelos", path))
        _recusar_duplicado([item.id for item in modelos], "modelo", path)

        conhecidos = {item.id for item in providers}
        for modelo in modelos:
            desconhecidos = [nome for nome in modelo.providers if nome not in conhecidos]
            if desconhecidos:
                raise AiConfigInvalida(
                    f"{path}: o modelo {modelo.id!r} aponta para provider não declarado: "
                    f"{', '.join(desconhecidos)}."
                )

        declarados = {item.id for item in modelos}
        fallback = tuple(str(nome) for nome in _lista(bruto, "fallback", path))
        for nome in fallback:
            if nome not in declarados:
                raise AiConfigInvalida(
                    f"{path}: a cadeia de fallback cita o modelo {nome!r}, que não foi declarado."
                )

        precos = _ler_precos(bruto.get("precos"), declarados, path)
        roteamento = _ler_roteamento(bruto.get("roteamento"), declarados, path)

        return cls(
            providers=providers,
            modelos=modelos,
            precos=precos,
            fallback=fallback,
            roteamento=roteamento,
            origem=path,
        )


# --- leitura de cada bloco ------------------------------------------------


def _lista(dados: dict, chave: str, path: Path) -> list:
    valor = dados.get(chave) or []
    if not isinstance(valor, list):
        raise AiConfigInvalida(f"{path}: o campo {chave!r} precisa ser uma lista.")
    return valor


def _recusar_duplicado(ids: list[str], contexto: str, path: Path) -> None:
    """Id repetido é sempre engano de edição, e o segundo venceria em silêncio."""
    repetidos = sorted({nome for nome in ids if ids.count(nome) > 1})
    if repetidos:
        raise AiConfigInvalida(
            f"{path}: há mais de um {contexto} com o mesmo id: {', '.join(repetidos)}."
        )


def _mapa(valor: object, contexto: str, path: Path) -> dict:
    if not isinstance(valor, dict):
        raise AiConfigInvalida(f"{path}: cada {contexto} precisa ser um mapeamento de campos.")
    return valor


def _obrigatorio(dados: dict, campo: str, contexto: str, path: Path) -> str:
    valor = str(dados.get(campo) or "").strip()
    if not valor:
        raise AiConfigInvalida(f"{path}: {contexto} sem {campo!r}.")
    return valor


def _ler_provider(bruto: object, path: Path) -> ProviderDeclarado:
    dados = _mapa(bruto, "provider", path)
    provider_id = _obrigatorio(dados, "id", "provider", path)
    tipo = str(dados.get("type") or "").strip().lower()
    if tipo not in TIPOS_DE_PROVIDER:
        raise AiConfigInvalida(
            f"{path}: o provider {provider_id!r} tem type={tipo!r}; use 'local' ou 'cloud'."
        )
    return ProviderDeclarado(
        id=provider_id,
        enabled=bool(dados.get("enabled", True)),
        type=tipo,
        base_url=str(dados.get("base_url") or "").strip(),
        api_key_env=str(dados.get("api_key_env") or "").strip(),
    )


def _ler_modelo(bruto: object, path: Path) -> ModeloDeclarado:
    dados = _mapa(bruto, "modelo", path)
    modelo_id = _obrigatorio(dados, "id", "modelo", path)
    custo = str(dados.get("cost_tier") or "").strip().lower()
    if custo not in NIVEIS_DE_CUSTO:
        raise AiConfigInvalida(
            f"{path}: o modelo {modelo_id!r} tem cost_tier={custo!r}; "
            "use 'free', 'low' ou 'high'."
        )
    providers = tuple(str(nome).strip() for nome in dados.get("providers") or [])
    if not providers:
        raise AiConfigInvalida(f"{path}: o modelo {modelo_id!r} não declara nenhum provider.")
    return ModeloDeclarado(
        id=modelo_id,
        model=_obrigatorio(dados, "model", f"o modelo {modelo_id!r}", path),
        capabilities=tuple(str(item).strip() for item in dados.get("capabilities") or []),
        providers=providers,
        cost_tier=custo,
        context_window=int(dados.get("context_window") or 0),
    )


def _ler_precos(bruto: object, declarados: set[str], path: Path) -> dict[str, Preco]:
    if bruto is None:
        return {}
    tabela = _mapa(bruto, "tabela de preço", path)
    precos: dict[str, Preco] = {}
    for modelo_id, valores in tabela.items():
        nome = str(modelo_id)
        if nome not in declarados:
            raise AiConfigInvalida(
                f"{path}: há preço para o modelo {nome!r}, que não foi declarado."
            )
        dados = _mapa(valores, f"preço de {nome!r}", path)
        anotado_em = _obrigatorio(dados, "anotado_em", f"o preço de {nome!r}", path)
        try:
            precos[nome] = Preco(
                input_por_milhao=float(dados["input_por_milhao"]),
                output_por_milhao=float(dados["output_por_milhao"]),
                anotado_em=anotado_em,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AiConfigInvalida(
                f"{path}: o preço de {nome!r} precisa de 'input_por_milhao' e "
                f"'output_por_milhao' numéricos ({exc})."
            ) from exc
    return precos


def _ler_roteamento(bruto: object, declarados: set[str], path: Path) -> Roteamento:
    if bruto is None:
        return Roteamento()
    dados = _mapa(bruto, "bloco de roteamento", path)
    padrao = str(dados.get("modelo_padrao") or "").strip()
    if padrao and padrao not in declarados:
        raise AiConfigInvalida(
            f"{path}: modelo_padrao={padrao!r} não foi declarado em 'modelos'."
        )
    try:
        limiar = int(dados.get("limiar_complexidade", Roteamento.limiar_complexidade))
    except (TypeError, ValueError) as exc:
        raise AiConfigInvalida(f"{path}: 'limiar_complexidade' precisa ser inteiro.") from exc
    if not 0 <= limiar <= 100:
        raise AiConfigInvalida(f"{path}: 'limiar_complexidade' fora da faixa 0–100: {limiar}.")
    return Roteamento(limiar_complexidade=limiar, modelo_padrao=padrao)


# --- a varredura por segredo ----------------------------------------------


def _recusar_segredo(bruto: object, path: Path, caminho: str = "") -> None:
    """Percorre o arquivo inteiro atrás de chave colada dentro (REQ-03).

    A mensagem nomeia o arquivo e o campo, e nunca o valor: o erro vira linha
    de log, e um erro que ecoa a chave vaza a chave exatamente onde ela não
    podia estar.
    """
    if isinstance(bruto, dict):
        for chave, valor in bruto.items():
            nome = str(chave)
            onde = f"{caminho}.{nome}" if caminho else nome
            if nome.strip().lower() in CAMPOS_DE_SEGREDO:
                raise AiConfigInvalida(
                    f"{path} declara o campo {onde!r}, que carregaria uma chave de API. "
                    "Use 'api_key_env' com o nome da variável de ambiente: o valor da "
                    "chave vive só no ambiente."
                )
            _recusar_segredo(valor, path, onde)
        return

    if isinstance(bruto, list):
        for indice, item in enumerate(bruto):
            _recusar_segredo(item, path, f"{caminho}[{indice}]")
        return

    if isinstance(bruto, str) and any(p.search(bruto.strip()) for p in PADROES_DE_SEGREDO):
        raise AiConfigInvalida(
            f"{path} tem, em {caminho!r}, um valor com cara de chave de API. "
            "Nenhuma chave pode ser versionada: declare 'api_key_env' e mantenha "
            "o valor no ambiente."
        )


@lru_cache
def get_ai_config() -> AiConfig:
    """O registro desta instalação. Erro de carga vira registro vazio com motivo.

    A IA quebrada não pode impedir o painel de abrir (P-06): o resto do
    DevCockpit — projetos, git, docker, jobs — não depende de nada disto.
    """
    settings = get_settings()
    path = settings.resolve(settings.ai_config_file)
    try:
        return AiConfig.load(path)
    except AiConfigInvalida as exc:
        logger.warning("Registro de IA ignorado: %s", exc.message)
        return AiConfig(origem=path, erro=exc.message)
