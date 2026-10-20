"""G-1: depois de uma recusa, o modelo não consegue repetir a ação na mesma invocação."""

from types import SimpleNamespace
from typing import cast

from google.adk.tools import BaseTool, ToolContext

from app.agents.callbacks import (
    ERRO_RECUSA_ADK,
    RESPOSTA_RECUSA,
    ajustar_resposta,
    bloquear_repeticao,
)

ARGS = {"area": "salao-de-festas", "data": "2030-04-20"}


def _tool(nome: str) -> BaseTool:
    return cast(BaseTool, SimpleNamespace(name=nome))


def _contexto() -> ToolContext:
    return cast(ToolContext, SimpleNamespace(state={}))


def test_recusa_vira_resposta_explicita_e_bloqueia_repeticao():
    tool, ctx = _tool("reservar_area"), _contexto()
    assert bloquear_repeticao(tool, ARGS, ctx) is None

    assert ajustar_resposta(tool, ARGS, ctx, {"error": ERRO_RECUSA_ADK}) == RESPOSTA_RECUSA
    assert bloquear_repeticao(tool, dict(ARGS), ctx) == RESPOSTA_RECUSA


def test_outra_acao_ou_outros_argumentos_nao_sao_bloqueados():
    tool, ctx = _tool("reservar_area"), _contexto()
    ajustar_resposta(tool, ARGS, ctx, {"error": ERRO_RECUSA_ADK})
    assert bloquear_repeticao(tool, {**ARGS, "data": "2030-04-21"}, ctx) is None
    assert bloquear_repeticao(_tool("autorizar_visitante"), ARGS, ctx) is None


def test_respostas_normais_nao_sao_alteradas():
    tool, ctx = _tool("reservar_area"), _contexto()
    assert ajustar_resposta(tool, ARGS, ctx, {"reservada": True, "codigo": "RSV-10000"}) is None
    assert bloquear_repeticao(tool, ARGS, ctx) is None


def test_aprovacao_marca_resultado_como_concluido():
    tool = _tool("reservar_area")
    ctx = cast(
        ToolContext,
        SimpleNamespace(state={}, tool_confirmation=SimpleNamespace(confirmed=True)),
    )
    resultado = ajustar_resposta(tool, ARGS, ctx, {"reservada": True, "codigo": "RSV-10001"})
    assert resultado is not None
    assert resultado["codigo"] == "RSV-10001"
    assert resultado["aprovada_pelo_morador"] is True
    assert resultado["situacao"] == "concluida"
