"""A regra de porta única, num lugar só.

Duas escritas gravam serviço: a edição pela tela e a importação de manifesto. A
detecção também sugere. Se cada uma tivesse sua cópia da regra, elas
divergiriam — foi o que aconteceu: a tela passou a recusar duplicata e as
outras duas continuaram criando a mesma duplicata pela porta de trás.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.errors import ValidationError


def exigir_portas_distintas(pares: Iterable[tuple[str, int | None]]) -> None:
    """Dois serviços do mesmo projeto na mesma porta é estado impossível.

    Uma porta tem um ouvinte. Aceitar a duplicata fazia o painel verificar três
    vezes o mesmo endereço, atribuir a resposta a três serviços e ainda avisar,
    na tela de Ports, sobre a inconsistência que ele mesmo tinha gravado.
    Recusar na escrita é onde isso custa menos.

    Recebe pares `(chave, porta)` em vez de objetos porque quem chama tem
    formas diferentes na mão: schema de requisição num caso, modelo do banco
    misturado com entrada de manifesto no outro.
    """
    vistos: dict[int, str] = {}
    for chave, porta in pares:
        if porta is None:
            continue
        anterior = vistos.get(porta)
        if anterior is not None and anterior != chave:
            raise ValidationError(
                f"A porta {porta} já é do serviço '{anterior}'. "
                "Uma porta tem um ouvinte só — troque a de um dos dois."
            )
        vistos[porta] = chave
