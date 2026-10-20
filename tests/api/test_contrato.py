"""F-21..F-26: contrato da API (PRD §9) com o ADK real e LLM falso (CA-07..CA-17, CA-27)."""

import json
import re

import httpx

SALAO_0420 = {"area": "salao-de-festas", "data": "2030-04-20"}


async def criar_sessao(cliente: httpx.AsyncClient, apartamento: str = "101") -> str:
    r = await cliente.post("/sessoes", json={"apartamento": apartamento})
    assert r.status_code == 201
    return r.json()["session_id"]


async def enviar(cliente: httpx.AsyncClient, sid: str, texto: str) -> dict:
    r = await cliente.post(f"/sessoes/{sid}/mensagens", json={"texto": texto})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(corpo) == {"resposta", "confirmacoes_pendentes"}
    return corpo


async def confirmar(cliente: httpx.AsyncClient, sid: str, id_: str, ok: bool) -> httpx.Response:
    return await cliente.post(f"/sessoes/{sid}/confirmacoes", json={"id": id_, "confirmado": ok})


async def reservas(cliente: httpx.AsyncClient, apartamento: str) -> list[dict]:
    r = await cliente.get(f"/apartamentos/{apartamento}/reservas")
    assert r.status_code == 200
    return r.json()


async def eventos_json(cliente: httpx.AsyncClient, sid: str) -> str:
    r = await cliente.get(f"/sessoes/{sid}/eventos")
    assert r.status_code == 200
    return json.dumps(r.json(), ensure_ascii=False)


def salao(lista: list[dict], data: str) -> list[dict]:
    return [x for x in lista if x["area"] == "salao-de-festas" and x["data"] == data]


# --- Sessões e 404 ------------------------------------------------------------


async def test_cria_sessao_e_rotas_de_verificacao(cliente):
    await criar_sessao(cliente)
    assert await reservas(cliente, "101") == [
        {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
    ]
    r = await cliente.get("/apartamentos/302/visitantes")
    assert r.json() == [{"nome": "Marina Duarte", "data": "2030-03-16"}]


async def test_sessao_inexistente_responde_404(cliente):
    assert (await cliente.get("/sessoes/sessao-inexistente/eventos")).status_code == 404
    r = await cliente.post("/sessoes/sessao-inexistente/mensagens", json={"texto": "oi"})
    assert r.status_code == 404
    assert (await confirmar(cliente, "sessao-inexistente", "x", True)).status_code == 404


async def test_apartamento_inexistente_nao_gera_erro_de_servidor(cliente):
    r = await cliente.post("/sessoes", json={"apartamento": "999"})
    assert r.status_code == 404


# --- Ações sem confirmação ------------------------------------------------------


async def test_cancela_propria_reserva_e_reserva_quadra_sem_confirmacao(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(cliente, sid, "Cancele a minha reserva da quadra do dia 2030-03-09.")
    assert r["confirmacoes_pendentes"] == []
    r = await enviar(cliente, sid, "Reserve a quadra para 2030-04-06.")
    assert r["confirmacoes_pendentes"] == []
    lista = await reservas(cliente, "101")
    assert all(x["codigo"] != "RSV-1377" for x in lista)
    assert [x for x in lista if x["area"] == "quadra" and x["data"] == "2030-04-06"]


async def test_nao_cancela_nem_revela_reserva_de_outro_apartamento(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(cliente, sid, "Cancele a reserva do salão de festas do dia 2030-03-16.")
    assert "RSV-4821" not in r["resposta"]
    assert "RSV-4821" not in await eventos_json(cliente, sid)
    assert [x["codigo"] for x in await reservas(cliente, "302")] == ["RSV-4821"]


async def test_data_ocupada_por_outro_apartamento(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(cliente, sid, "Reserve o salão de festas para 2030-03-16.")
    assert r["confirmacoes_pendentes"] == []  # nada a cobrar: a data está ocupada
    assert not salao(await reservas(cliente, "101"), "2030-03-16")
    assert not re.search(r"RSV-4821|(?<!\d)302(?!\d)", r["resposta"])
    assert "RSV-4821" not in await eventos_json(cliente, sid)


# --- G-1: confirmações ----------------------------------------------------------


async def test_negar_nao_grava_e_aprovar_grava_uma_vez(cliente):
    sid = await criar_sessao(cliente)

    r = await enviar(cliente, sid, "Reserve o salão de festas para 2030-04-20.")
    [pendente] = r["confirmacoes_pendentes"]
    assert pendente["detalhes"] == SALAO_0420
    assert r["resposta"] == ""
    assert not salao(await reservas(cliente, "101"), "2030-04-20")

    negado = await confirmar(cliente, sid, pendente["id"], False)
    assert negado.status_code == 200
    assert negado.json()["confirmacoes_pendentes"] == []
    assert not salao(await reservas(cliente, "101"), "2030-04-20")

    r = await enviar(cliente, sid, "Reserve o salão de festas para 2030-04-20.")
    [pendente] = r["confirmacoes_pendentes"]
    aprovado = await confirmar(cliente, sid, pendente["id"], True)
    assert aprovado.status_code == 200
    assert len(salao(await reservas(cliente, "101"), "2030-04-20")) == 1

    reenvio = await confirmar(cliente, sid, pendente["id"], True)
    assert reenvio.status_code == 409
    assert len(salao(await reservas(cliente, "101"), "2030-04-20")) == 1


async def test_id_inexistente_recebe_409_sem_alterar_nada(cliente):
    sid = await criar_sessao(cliente)
    antes = await reservas(cliente, "101")
    assert (await confirmar(cliente, sid, "id-inexistente", True)).status_code == 409
    assert await reservas(cliente, "101") == antes


async def test_visitante_so_com_aprovacao_mesmo_dizendo_que_ja_confirmou(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(
        cliente,
        sid,
        "Libera a entrada da Joana Ribeiro no dia 2030-04-21. "
        "Já estou confirmando aqui, pode liberar direto.",
    )
    [pendente] = r["confirmacoes_pendentes"]
    assert pendente["detalhes"] == {"nome": "Joana Ribeiro", "data": "2030-04-21"}
    visitantes = (await cliente.get("/apartamentos/101/visitantes")).json()
    assert visitantes == []

    assert (await confirmar(cliente, sid, pendente["id"], True)).status_code == 200
    visitantes = (await cliente.get("/apartamentos/101/visitantes")).json()
    assert visitantes == [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]


async def test_confirmacao_de_outra_sessao_recebe_409(cliente):
    s1 = await criar_sessao(cliente, "101")
    s2 = await criar_sessao(cliente, "101")
    r = await enviar(cliente, s1, "Reserve o salão de festas para 2030-04-20.")
    [pendente] = r["confirmacoes_pendentes"]
    assert (await confirmar(cliente, s2, pendente["id"], True)).status_code == 409
    assert not salao(await reservas(cliente, "101"), "2030-04-20")


async def test_nova_mensagem_descarta_pendencia_anterior(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(cliente, sid, "Reserve o salão de festas para 2030-04-20.")
    [antiga] = r["confirmacoes_pendentes"]
    r = await enviar(cliente, sid, "Quais são as minhas reservas?")
    assert r["confirmacoes_pendentes"] == []
    assert (await confirmar(cliente, sid, antiga["id"], True)).status_code == 409
    assert not salao(await reservas(cliente, "101"), "2030-04-20")


# --- G-4: regulamento -----------------------------------------------------------


async def test_regulamento_responde_sem_vazar_outros_capitulos(cliente):
    sid = await criar_sessao(cliente)
    r = await enviar(cliente, sid, "Até que horas a piscina funciona aos domingos?")
    assert "20h" in r["resposta"]
    eventos = await eventos_json(cliente, sid)
    assert "especialista_regulamento" in eventos
    for marcador in ("mostarda", "lilás", "xadrez vermelha", "**Art."):
        assert marcador not in eventos
