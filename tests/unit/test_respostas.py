"""F-22: texto da resposta a partir dos eventos do turno."""

from google.adk.events import Event, EventActions
from google.genai import types

from app.api.respostas import texto_da_resposta


def _texto(autor: str, texto: str) -> Event:
    return Event(author=autor, content=types.Content(role="model", parts=[types.Part(text=texto)]))


def test_ultimo_texto_dos_agentes():
    eventos = [
        _texto("user", "Reserve a quadra"),
        _texto("aurora_principal", "Vou verificar."),
        _texto("especialista_reservas", "Quadra reservada."),
    ]
    assert texto_da_resposta(eventos) == "Quadra reservada."


def test_resultado_de_agent_tool_com_skip_summarization():
    resposta = types.FunctionResponse(
        id="x", name="especialista_regulamento", response={"result": "Até as 20h (Art. 22)."}
    )
    evento = Event(
        author="aurora_principal",
        content=types.Content(role="user", parts=[types.Part(function_response=resposta)]),
        actions=EventActions(skip_summarization=True),
    )
    assert texto_da_resposta([_texto("user", "piscina?"), evento]) == "Até as 20h (Art. 22)."


def test_pausa_para_confirmacao_devolve_vazio():
    chamada = types.FunctionCall(id="c1", name="adk_request_confirmation", args={})
    evento = Event(
        author="especialista_reservas",
        content=types.Content(role="model", parts=[types.Part(function_call=chamada)]),
    )
    assert texto_da_resposta([_texto("user", "Reserve o salão"), evento]) == ""
