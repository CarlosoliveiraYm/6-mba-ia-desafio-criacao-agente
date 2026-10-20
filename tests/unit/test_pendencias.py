"""F-23: extração das confirmações pendentes a partir de eventos sintéticos."""

from google.adk.events import Event
from google.genai import types

from app.api.confirmacoes import NOME_CONFIRMACAO, extrair_pendencias, resposta_de_confirmacao


def _pedido(id_: str, tool: str, args: dict) -> Event:
    chamada = types.FunctionCall(
        id=id_,
        name=NOME_CONFIRMACAO,
        args={
            "originalFunctionCall": {"id": f"orig-{id_}", "name": tool, "args": args},
            "toolConfirmation": {"hint": "aprove", "confirmed": False},
        },
    )
    return Event(
        author="especialista_reservas",
        content=types.Content(role="model", parts=[types.Part(function_call=chamada)]),
    )


def _resposta(id_: str) -> Event:
    return Event(author="user", content=resposta_de_confirmacao(id_, True))


RESERVA = {"area": "salao-de-festas", "data": "2030-04-20"}
VISITANTE = {"nome": "Joana Ribeiro", "data": "2030-04-21"}


def test_pedido_sem_resposta_fica_pendente_com_detalhes():
    [p] = extrair_pendencias([_pedido("c1", "reservar_area", RESERVA)])
    assert (p.id, p.acao, p.detalhes) == ("c1", "reservar_area", RESERVA)


def test_pedido_respondido_deixa_de_ser_pendente():
    assert extrair_pendencias([_pedido("c1", "reservar_area", RESERVA), _resposta("c1")]) == []


def test_varios_pedidos_mantem_a_ordem_e_ignoram_os_respondidos():
    eventos = [
        _pedido("c1", "reservar_area", RESERVA),
        _resposta("c1"),
        _pedido("c2", "autorizar_visitante", VISITANTE),
        _pedido("c3", "reservar_area", RESERVA),
    ]
    assert [p.id for p in extrair_pendencias(eventos)] == ["c2", "c3"]


def _texto_do_morador(texto: str) -> Event:
    return Event(author="user", content=types.Content(role="user", parts=[types.Part(text=texto)]))


def test_nova_mensagem_do_morador_descarta_pendencias_anteriores():
    eventos = [
        _pedido("c1", "reservar_area", RESERVA),
        _texto_do_morador("Libera a entrada da Joana Ribeiro no dia 2030-04-21."),
        _pedido("c2", "autorizar_visitante", VISITANTE),
    ]
    assert [p.id for p in extrair_pendencias(eventos)] == ["c2"]


def test_resposta_de_confirmacao_nao_descarta_pendencias():
    """A FunctionResponse do morador não é texto: só resolve a própria pendência."""
    eventos = [
        _pedido("c1", "reservar_area", RESERVA),
        _pedido("c2", "autorizar_visitante", VISITANTE),
        _resposta("c1"),
    ]
    assert [p.id for p in extrair_pendencias(eventos)] == ["c2"]


def test_eventos_sem_confirmacao():
    texto = Event(author="user", content=types.Content(role="user", parts=[types.Part(text="oi")]))
    assert extrair_pendencias([texto]) == []
