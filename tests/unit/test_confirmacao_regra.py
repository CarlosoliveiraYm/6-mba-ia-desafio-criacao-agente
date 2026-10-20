"""F-10 e F-13: quando a confirmação pelo sistema é exigida (RN-2, RN-3, G-1)."""

import pytest

from app.tools.reservas import precisa_confirmar_reserva, reservar_area_tool
from app.tools.visitantes import autorizar_visitante_tool, precisa_confirmar_visitante


@pytest.mark.parametrize(
    ("area", "data", "esperado"),
    [
        ("salao-de-festas", "2030-04-20", True),  # taxa 150, livre
        ("churrasqueira", "2030-04-20", True),  # taxa 80, livre
        ("quadra", "2030-04-06", False),  # taxa 0: sem cobrança
        ("salao-de-festas", "2030-03-16", False),  # ocupada: nada será cobrado
        ("piscina", "2030-04-20", False),  # área inexistente: a tool devolve erro
        ("salao-de-festas", "20/04/2030", False),  # data inválida: a tool devolve erro
    ],
)
async def test_regra_de_confirmacao_da_reserva(banco, contexto, area, data, esperado):
    assert await precisa_confirmar_reserva(area, data, contexto("101")) is esperado


@pytest.mark.parametrize(
    ("nome", "data", "esperado"),
    [
        ("Joana Ribeiro", "2030-04-21", True),
        ("   ", "2030-04-21", False),
        ("Joana Ribeiro", "amanhã", False),
    ],
)
async def test_regra_de_confirmacao_do_visitante(banco, contexto, nome, data, esperado):
    assert await precisa_confirmar_visitante(nome, data, contexto("101")) is esperado


def test_tools_confirmaveis_estao_registradas_com_a_regra():
    """As tools de cobrança e de acesso usam a regra de confirmação do código, não do prompt."""
    assert reservar_area_tool._require_confirmation is precisa_confirmar_reserva
    assert autorizar_visitante_tool._require_confirmation is precisa_confirmar_visitante
