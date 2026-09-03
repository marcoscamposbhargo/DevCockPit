"""A classificação por regra que decide para onde a pergunta vai (REQ-06).

Três coisas se protegem aqui, e não são a mesma:

1. **O tipo.** Errar `task_type` custa um modelo mal escolhido — irritante,
   reversível.
2. **A faixa de `complexity`.** O router compara o número com limiares vindos do
   YAML; um valor fora de 0–100 não levanta erro em lugar nenhum, só escolhe
   errado em silêncio.
3. **`privacy`.** Errar para `internal` significa mandar para a nuvem o que não
   podia sair da máquina. É o único erro aqui que não dá para desfazer, e por
   isso o teste cobra o desempate conservador.

E o tempo: o classificador existe na forma que tem porque classificar com modelo
custou de 3 a 26 segundos na Fase 3. O teste de 100 perguntas é o que impede
alguém de reintroduzir uma chamada de rede aqui sem perceber.
"""

from __future__ import annotations

import time
from itertools import cycle, islice

import pytest

from app.services.ai.classifier import TIPOS, Classificacao, classificar

pytestmark = pytest.mark.unit


#: Tabela de casos: pergunta real em português, tipo esperado. Ao menos uma
#: por `task_type` do REQ-06 — o teste seguinte falha se algum ficar de fora.
CASOS: tuple[tuple[str, str], ...] = (
    # simple_task — ordem que o painel já faz por botão, e o padrão de quem não
    # deu sinal nenhum
    ("sobe o ambiente do zapcrm", "simple_task"),
    ("mostra as portas ocupadas", "simple_task"),
    ("desliga o kiteasy", "simple_task"),
    ("qual a diferença entre uvicorn e gunicorn?", "simple_task"),
    ("o que significa lru_cache?", "simple_task"),
    # coding
    ("implementa a rota de exportação em app/api/routes/projects.py", "coding"),
    ("cria um componente de tabela para a tela de consumo", "coding"),
    # debugging
    ("o servidor do smartdash quebrou com traceback ao subir, por quê?", "debugging"),
    ("por que o docker não conecta no banco depois do último commit?", "debugging"),
    # architecture
    ("vale separar o context engine em camada própria ou o acoplamento está ok?", "architecture"),
    ("qual arquitetura faz sentido para o registro de providers?", "architecture"),
    # documentation
    ("atualiza o README com a seção de instalação", "documentation"),
    ("qual docstring essa função deveria ter?", "documentation"),
    # testing
    ("escreve um teste unitário para o classificador com pytest", "testing"),
    ("como faço fixture de sessão sem tocar no banco de produção?", "testing"),
    # qa — quality assurance: avaliar, não escrever nem consertar
    ("quais casos de borda faltam no fluxo de fallback?", "qa"),
    ("quais os critérios de aceite dessa tela?", "qa"),
    ("o que pode quebrar se eu mudar o teto de contexto?", "qa"),
    ("a cobertura do runner está boa ou faltou testar alguma coisa?", "qa"),
    # planning
    ("por onde começo o próximo ciclo? o que priorizar primeiro?", "planning"),
    ("monta um roadmap das ondas que faltam", "planning"),
    # refactoring
    ("essa função está repetida em três arquivos, dá pra refatorar?", "refactoring"),
    ("simplifica o fluxo de fallback sem mudar comportamento", "refactoring"),
)


@pytest.mark.parametrize("pergunta,esperado", CASOS)
def test_tabela_de_casos(pergunta: str, esperado: str) -> None:
    assert classificar(pergunta).task_type == esperado


def test_todo_task_type_tem_exemplo() -> None:
    """Tipo sem exemplo é tipo que ninguém sabe se o classificador produz."""
    cobertos = {esperado for _, esperado in CASOS}
    assert cobertos == set(TIPOS), f"sem exemplo na tabela: {sorted(set(TIPOS) - cobertos)}"


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        # avaliar
        ("faltou testar o caminho de erro?", "qa"),
        ("qual o risco de regressão nessa mudança?", "qa"),
        ("isso está coberto pelos critérios de aceite?", "qa"),
        # escrever teste
        ("escreve o teste do runner com fixture de sessão", "testing"),
        ("monta um teste de contrato para o provider genérico", "testing"),
        # consertar defeito
        ("o teste do runner quebrou com traceback depois do merge", "debugging"),
        ("a rota de saúde não conecta e não sei por quê", "debugging"),
    ],
)
def test_fronteira_entre_qa_testing_e_debugging(pergunta: str, esperado: str) -> None:
    """Os três vizinhos usam as mesmas palavras e querem coisas diferentes.

    `qa` avalia, `testing` escreve, `debugging` conserta. É a fronteira que a
    ordem de `GATILHOS` existe para arbitrar, e a que mais dói quando erra: `qa`
    virando `testing` manda uma pergunta de risco para quem escreve `assert`.

    O sentido de `qa` aqui é o mesmo do especialista `QA` de `especialistas.py`
    e o do PRD §24 — quality assurance, não "pergunta e resposta".
    """
    assert classificar(pergunta).task_type == esperado


def test_pergunta_sem_sinal_nenhum_cai_em_simple_task() -> None:
    """O padrão é `simple_task`, e isso não é detalhe de implementação.

    Se o padrão fosse `qa`, toda dúvida solta do chat — que é a maioria do que
    se digita ali — seria classificada como avaliação de qualidade e roteada
    para o chapéu de testes.
    """
    for pergunta in (
        "qual a diferença entre uvicorn e gunicorn?",
        "o que significa lru_cache?",
        "me explica o que esse projeto faz",
    ):
        assert classificar(pergunta).task_type == "simple_task"


# --- complexity ------------------------------------------------------------


@pytest.mark.parametrize("pergunta,_esperado", CASOS)
def test_complexidade_fica_na_faixa(pergunta: str, _esperado: str) -> None:
    resultado = classificar(pergunta)
    assert isinstance(resultado.complexity, int)
    assert 0 <= resultado.complexity <= 100


def test_complexidade_nunca_estoura_a_faixa_no_pior_caso() -> None:
    """Todo ajuste somando ao mesmo tempo continua parando em 100."""
    pergunta = (
        "revê a arquitetura de camadas e o acoplamento entre "
        "app/services/ai/runner.py e app/services/ai/model_router.py, "
        "que o teste quebrou com traceback:\n```\nboom\n```\n" + "detalhe. " * 80
    )
    assert classificar(pergunta).complexity == 100


def test_ordem_curta_pesa_menos_que_decisao_de_arquitetura() -> None:
    """A escala precisa separar o que o router vai separar."""
    simples = classificar("sobe o ambiente do zapcrm")
    dificil = classificar("qual arquitetura faz sentido para o registro de providers?")
    assert simples.complexity < 40 < dificil.complexity


# --- privacy ---------------------------------------------------------------


@pytest.mark.parametrize(
    "pergunta",
    [
        "#local me ajuda a entender esse trecho",
        "isso é confidencial, não envie para fora",
        "qual senha o compose está usando?",
        "o .env do zapcrm está com a variável certa?",
        "quero resposta só local, sem nuvem",
        "essa chave está no lugar certo?",
    ],
)
def test_gatilho_explicito_marca_local(pergunta: str) -> None:
    assert classificar(pergunta).privacy == "local"


@pytest.mark.parametrize(
    "pergunta",
    [
        "qual a diferença entre uvicorn e gunicorn?",
        "implementa a rota de exportação em app/api/routes/projects.py",
        "sobe o ambiente do zapcrm",
    ],
)
def test_sem_gatilho_a_pergunta_e_interna(pergunta: str) -> None:
    assert classificar(pergunta).privacy == "internal"


def test_caminho_de_arquivo_sozinho_nao_marca_local() -> None:
    """Se citar arquivo bastasse, todo trabalho de código iria para o local.

    Nesta máquina o local roda a 24–32 tok/s: seria minutos por resposta em
    troca de nenhum ganho de privacidade.
    """
    resultado = classificar("olha o app/services/ai/runner.py e me diz o que falta")
    assert resultado.privacy == "internal"


def test_marca_no_estado_vence_o_texto() -> None:
    """Quem chamou pode dizer 'isto não sai daqui' sem depender de palavra."""
    assert classificar("qual a versão do python?", estado={"privacy": "local"}).privacy == "local"
    assert classificar("qual a versão do python?", estado={"privado": True}).privacy == "local"
    assert classificar("qual a versão do python?", estado={"servers": []}).privacy == "internal"


def test_privacy_e_sempre_um_dos_dois_valores() -> None:
    for pergunta, _esperado in CASOS:
        assert classificar(pergunta).privacy in ("local", "internal")


# --- tools_required --------------------------------------------------------


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        ("mostra o log do servidor do kiteasy", True),
        ("sobe o ambiente do zapcrm", True),
        ("quais portas estão ocupadas?", True),
        ("qual a diferença entre uvicorn e gunicorn?", False),
        ("o que significa lru_cache?", False),
    ],
)
def test_tools_required_segue_o_catalogo_fechado(pergunta: str, esperado: bool) -> None:
    """Ferramenta aqui é o catálogo de ações do painel, nada além (P-01)."""
    assert classificar(pergunta).tools_required is esperado


# --- bordas e contrato -----------------------------------------------------


@pytest.mark.parametrize("pergunta", ["", "   ", "?"])
def test_pergunta_vazia_nao_levanta(pergunta: str) -> None:
    """Classificar é o primeiro passo do fluxo; ele não pode ser o que quebra."""
    resultado = classificar(pergunta)
    assert resultado.task_type in TIPOS
    assert 0 <= resultado.complexity <= 100


def test_acento_e_caixa_nao_mudam_o_resultado() -> None:
    assert classificar("REFATORAÇÃO desse módulo") == classificar("refatoracao desse modulo")


def test_classificacao_e_determinista() -> None:
    """Duas chamadas iguais dão o mesmo objeto — é o que 'por regra' significa."""
    pergunta = "o teste de fallback quebrou depois da migração"
    assert classificar(pergunta) == classificar(pergunta)


def test_to_dict_traz_os_quatro_campos_do_req_06() -> None:
    saida = classificar("sobe o ambiente do zapcrm").to_dict()
    assert set(saida) == {"task_type", "complexity", "privacy", "tools_required"}


# --- o teto de 50 ms -------------------------------------------------------


def test_cem_perguntas_ficam_abaixo_de_50ms_cada() -> None:
    """REQ-06: menos de 50 ms por pergunta, medido em 100 perguntas.

    A margem real é de três ordens de grandeza — o valor medido fica em
    microssegundos. Este teste não afina desempenho: ele falha no dia em que
    alguém puser uma chamada de modelo, de rede ou de disco neste caminho, que
    foi exatamente o desenho descartado no plano.
    """
    perguntas = [
        f"{pergunta} (variação {i})"
        for i, (pergunta, _esperado) in enumerate(islice(cycle(CASOS), 100))
    ]
    assert len(perguntas) == 100

    tempos: list[float] = []
    for pergunta in perguntas:
        comeco = time.perf_counter()
        resultado = classificar(pergunta)
        tempos.append(time.perf_counter() - comeco)
        assert isinstance(resultado, Classificacao)

    media = sum(tempos) / len(tempos)
    assert media < 0.050, f"média de {media * 1000:.1f} ms por pergunta"
    assert max(tempos) < 0.050, f"pior caso de {max(tempos) * 1000:.1f} ms"
