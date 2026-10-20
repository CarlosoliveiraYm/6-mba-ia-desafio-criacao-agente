"""F-06: restauração do estado inicial (RF-13, RN-5)."""

import json
from datetime import date

from sqlalchemy import text

from app.db import repositorio as repo
from app.db.conexao import transacao
from scripts.restaurar import restaurar_dados


def _numero(codigo: str) -> int:
    return int(codigo.removeprefix("RSV-"))


async def test_carrega_reservas_e_visitantes_de_dados(banco, config):
    async with transacao(banco) as conn:
        assert await repo.listar_reservas(conn, "101") == [
            {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
        ]
        assert await repo.listar_visitantes(conn, "302") == [
            {"nome": "Marina Duarte", "data": "2030-03-16"}
        ]
        total = (await conn.execute(text("SELECT count(*) FROM reservas"))).scalar_one()
    esperado = json.loads((config.dir_dados / "reservas.json").read_text(encoding="utf-8"))
    assert total == len(esperado)


async def test_desfaz_mudancas_e_apaga_sessoes(banco, config):
    async with transacao(banco) as conn:
        await repo.cancelar_reserva(conn, "101", "quadra", date(2030, 3, 9))
        await repo.inserir_reserva(conn, "101", "quadra", date(2030, 4, 6))
        await repo.inserir_visitante(conn, "101", "Joana Ribeiro", date(2030, 4, 21))
        await conn.execute(
            text("INSERT INTO sessoes_apartamento (session_id, apartamento) VALUES ('s1', '101')")
        )

    await restaurar_dados(banco, config.dir_dados)

    async with transacao(banco) as conn:
        assert await repo.listar_reservas(conn, "101") == [
            {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
        ]
        assert await repo.listar_visitantes(conn, "101") == []
        sessoes = (
            await conn.execute(text("SELECT count(*) FROM sessoes_apartamento"))
        ).scalar_one()
        canceladas = (
            await conn.execute(text("SELECT count(*) FROM reservas WHERE status = 'cancelada'"))
        ).scalar_one()
    assert sessoes == 0
    assert canceladas == 0


async def test_restaurar_duas_vezes_da_o_mesmo_resultado(banco, config):
    await restaurar_dados(banco, config.dir_dados)
    async with transacao(banco) as conn:
        assert await repo.listar_reservas(conn, "302") == [
            {"codigo": "RSV-4821", "area": "salao-de-festas", "data": "2030-03-16"}
        ]


async def test_sequence_nao_reinicia_na_restauracao(banco, config):
    async with transacao(banco) as conn:
        antes = await repo.inserir_reserva(conn, "101", "quadra", date(2030, 6, 1))
    await restaurar_dados(banco, config.dir_dados)
    async with transacao(banco) as conn:
        depois = await repo.inserir_reserva(conn, "101", "quadra", date(2030, 6, 1))
    assert antes and depois
    assert _numero(depois) > _numero(antes)
