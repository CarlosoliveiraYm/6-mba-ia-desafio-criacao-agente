"""G-2 / CA-18: nenhuma tool aceita apartamento escolhido pelo modelo."""

import inspect

import pytest
from google.adk.tools import FunctionTool

from app.tools.reservas import TOOLS_RESERVAS
from app.tools.visitantes import TOOLS_VISITANTES

PARAMETROS_PROIBIDOS = {"apartamento", "apto", "apartment", "numero_apartamento", "unidade"}


def _funcao(tool):
    return tool.func if isinstance(tool, FunctionTool) else tool


@pytest.mark.parametrize(
    "tool", TOOLS_RESERVAS + TOOLS_VISITANTES, ids=lambda t: _funcao(t).__name__
)
def test_tool_nao_recebe_apartamento_e_usa_tool_context(tool):
    parametros = set(inspect.signature(_funcao(tool)).parameters)
    assert not parametros & PARAMETROS_PROIBIDOS
    assert "tool_context" in parametros
