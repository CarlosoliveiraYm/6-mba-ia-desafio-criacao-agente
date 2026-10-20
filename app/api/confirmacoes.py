"""Confirmações pendentes derivadas dos eventos persistidos da sessão (F-23, G-1).

A fonte da verdade é o histórico do ADK: uma confirmação está pendente quando existe a
function call `adk_request_confirmation` e ainda não existe a function response com o
mesmo id. Depois de respondida, ela some daqui, e um reenvio do mesmo id recebe 409.
"""

from dataclasses import dataclass
from typing import Any

from google.adk.events import Event
from google.genai import types

NOME_CONFIRMACAO = "adk_request_confirmation"


@dataclass(frozen=True)
class ConfirmacaoPendente:
    id: str
    acao: str
    detalhes: dict[str, Any]


def extrair_pendencias(eventos: list[Event]) -> list[ConfirmacaoPendente]:
    pedidas: dict[str, types.FunctionCall] = {}  # preserva a ordem dos pedidos
    respondidas: set[str] = set()
    for evento in eventos:
        for chamada in evento.get_function_calls():
            if chamada.name == NOME_CONFIRMACAO and chamada.id:
                pedidas[chamada.id] = chamada
        for resposta in evento.get_function_responses():
            if resposta.name == NOME_CONFIRMACAO and resposta.id:
                respondidas.add(resposta.id)

    pendentes = []
    for id_, chamada in pedidas.items():
        if id_ in respondidas:
            continue
        original = (chamada.args or {}).get("originalFunctionCall", {})
        pendentes.append(
            ConfirmacaoPendente(
                id=id_,
                acao=str(original.get("name", "")),
                detalhes=dict(original.get("args") or {}),
            )
        )
    return pendentes


def resposta_de_confirmacao(id_: str, confirmado: bool) -> types.Content:
    """Mensagem que devolve ao Runner a decisão do morador (variante (a) do spike F-00)."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=id_, name=NOME_CONFIRMACAO, response={"confirmed": confirmado}
                )
            )
        ],
    )
