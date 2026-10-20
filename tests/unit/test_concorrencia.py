"""F-09 / G-5: duas (ou mais) gravações simultâneas da mesma área e data."""

import asyncio
from datetime import date

from sqlalchemy import text

from app.db import repositorio as repo
from app.db.conexao import transacao
from app.tools.reservas import reservar_area

APARTAMENTOS = ["101", "102", "201", "202", "301", "302"]


async def _ativas(engine, area: str, dia: date) -> int:
    async with transacao(engine) as conn:
        resultado = await conn.execute(
            text(
                "SELECT count(*) FROM reservas WHERE area = :a AND data = :d AND status = 'ativa'"
            ),
            {"a": area, "d": dia},
        )
        return resultado.scalar_one()


async def test_insercoes_concorrentes_gravam_uma_unica_reserva(banco):
    dia = date(2030, 5, 11)

    async def tentar(apartamento: str) -> str | None:
        async with transacao(banco) as conn:
            return await repo.inserir_reserva(conn, apartamento, "salao-de-festas", dia)

    resultados = await asyncio.gather(*(tentar(a) for a in APARTAMENTOS * 2))

    assert len([r for r in resultados if r]) == 1
    assert await _ativas(banco, "salao-de-festas", dia) == 1


async def test_tools_concorrentes_um_vence_e_o_outro_recebe_recusa_normal(banco, contexto):
    r101, r201 = await asyncio.gather(
        reservar_area("salao-de-festas", "2030-05-11", contexto("101")),
        reservar_area("salao-de-festas", "2030-05-11", contexto("201")),
    )
    assert sorted([r101["reservada"], r201["reservada"]]) == [False, True]
    perdedor = r101 if not r101["reservada"] else r201
    assert perdedor["motivo"] == "data ocupada"
    assert await _ativas(banco, "salao-de-festas", date(2030, 5, 11)) == 1
