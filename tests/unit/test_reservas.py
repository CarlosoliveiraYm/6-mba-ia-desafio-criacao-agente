"""F-07, F-08, F-09, F-11, F-12: tools de reservas (RN-1, RN-4, RN-5, G-2)."""

from app.db import repositorio as repo
from app.db.conexao import transacao
from app.tools.reservas import (
    cancelar_reserva,
    listar_minhas_reservas,
    reservar_area,
    verificar_disponibilidade,
)
from tests.conftest import sem_dados_do_302

CODIGOS_INICIAIS = {"RSV-1377", "RSV-4821", "RSV-2950"}


async def test_disponibilidade_ocupada_nao_revela_dono(banco, contexto):
    r = await verificar_disponibilidade("salao-de-festas", "2030-03-16", contexto("101"))
    assert r["disponivel"] is False
    assert sem_dados_do_302(r)


async def test_disponibilidade_livre(banco, contexto):
    r = await verificar_disponibilidade("salao-de-festas", "2030-04-20", contexto("101"))
    assert r == {"area": "salao-de-festas", "data": "2030-04-20", "disponivel": True, "taxa": 150.0}


async def test_entrada_invalida_devolve_erro_sem_excecao(banco, contexto):
    assert "erro" in await verificar_disponibilidade("piscina", "2030-04-20", contexto("101"))
    assert "erro" in await reservar_area("quadra", "20/04/2030", contexto("101"))
    assert "erro" in await reservar_area("quadra", "2030-02-30", contexto("101"))
    assert "erro" in await cancelar_reserva("quadra", "amanhã", contexto("101"))


async def test_reserva_area_livre_com_codigo_novo(banco, contexto):
    r = await reservar_area("quadra", "2030-04-06", contexto("101"))
    assert r["reservada"] is True
    assert r["cobranca"] is False
    assert r["codigo"] not in CODIGOS_INICIAIS
    minhas = await listar_minhas_reservas(contexto("101"))
    assert {"codigo": r["codigo"], "area": "quadra", "data": "2030-04-06"} in minhas["reservas"]


async def test_reserva_em_data_ocupada_recusa_sem_vazar_dados(banco, contexto):
    r = await reservar_area("salao-de-festas", "2030-03-16", contexto("101"))
    assert r["reservada"] is False
    assert r["motivo"] == "data ocupada"
    assert sem_dados_do_302(r)
    async with transacao(banco) as conn:
        assert await repo.listar_reservas(conn, "101") == [
            {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
        ]


async def test_cancela_reserva_propria(banco, contexto):
    r = await cancelar_reserva("quadra", "2030-03-09", contexto("101"))
    assert r == {"cancelada": True, "codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
    assert (await listar_minhas_reservas(contexto("101")))["reservas"] == []


async def test_nao_cancela_reserva_de_outro_apartamento(banco, contexto):
    r = await cancelar_reserva("salao-de-festas", "2030-03-16", contexto("101"))
    assert r["cancelada"] is False
    assert sem_dados_do_302(r)
    async with transacao(banco) as conn:
        assert await repo.listar_reservas(conn, "302") == [
            {"codigo": "RSV-4821", "area": "salao-de-festas", "data": "2030-03-16"}
        ]


async def test_codigo_nunca_repete_apos_cancelamento(banco, contexto):
    primeira = await reservar_area("quadra", "2030-04-06", contexto("101"))
    await cancelar_reserva("quadra", "2030-04-06", contexto("101"))
    segunda = await reservar_area("quadra", "2030-04-06", contexto("101"))
    assert primeira["reservada"] and segunda["reservada"]
    assert primeira["codigo"] != segunda["codigo"]


async def test_codigos_unicos_em_varias_reservas(banco, contexto):
    codigos = set()
    for dia in range(1, 21):
        r = await reservar_area("quadra", f"2030-07-{dia:02d}", contexto("101"))
        codigos.add(r["codigo"])
    assert len(codigos) == 20
    assert not codigos & CODIGOS_INICIAIS


async def test_listagem_traz_so_o_apartamento_da_sessao(banco, contexto):
    r = await listar_minhas_reservas(contexto("101"))
    assert r == {"reservas": [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]}
    assert sem_dados_do_302(r)
