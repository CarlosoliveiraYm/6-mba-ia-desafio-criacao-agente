"""Utilitários compartilhados pelas tools: apartamento da sessão e validação de entrada."""

import re
from datetime import date

from google.adk.tools import ToolContext

_FORMATO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ERRO_DATA = {"erro": "data inválida, use o formato AAAA-MM-DD"}


def apartamento_da_sessao(tool_context: ToolContext) -> str:
    """G-2: o apartamento vem só do state definido na criação da sessão."""
    apartamento = tool_context.state.get("apartamento")
    if not apartamento:
        raise RuntimeError("sessão sem apartamento no state")
    return str(apartamento)


def converter_data(valor: str) -> date | None:
    """Converte `AAAA-MM-DD` em date. Devolve None se o formato ou a data forem inválidos."""
    valor = (valor or "").strip()
    if not _FORMATO_DATA.match(valor):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None
