"""F-29: passos 13–14 do fluxo de validação, depois de reiniciar a API (sem restaurar).

Pré-requisito: `test_antes_do_reinicio.py` executado, Ctrl+C na API e `uv run api` de novo.
"""

import asyncio

import pytest

from tests.e2e.comum import (
    CODIGOS_INICIAIS,
    cliente,
    confirmar,
    criar_sessao,
    da_area,
    enviar,
    enviar_ate_pendencia,
    eventos,
    ler_estado,
    reservas,
    visitantes,
)

pytestmark = pytest.mark.e2e


async def test_passo_13_nada_se_perde_no_reinicio():
    estado = ler_estado()
    s1 = estado["s1"]
    async with cliente() as c:
        assert len(await eventos(c, s1)) == estado["eventos_s1"]

        await enviar(c, s1, "Quais são as minhas reservas agora?")
        assert len(await eventos(c, s1)) > estado["eventos_s1"]

        lista = await reservas(c, "101")
        assert da_area(lista, "quadra", "2030-04-06")
        assert da_area(lista, "salao-de-festas", "2030-04-20")
        assert all(x["codigo"] != "RSV-1377" for x in lista)
        assert {"nome": "Joana Ribeiro", "data": "2030-04-21"} in await visitantes(c, "101")

        criados = estado["codigos_criados"]
        assert len(set(criados)) == len(criados) == 2
        assert not set(criados) & CODIGOS_INICIAIS
        assert [x["codigo"] for x in await reservas(c, "302")] == ["RSV-4821"]


async def test_passo_14_dois_moradores_uma_reserva():
    pedido = "Reserve o salão de festas para 2030-05-11."
    async with cliente() as c:
        s3 = await criar_sessao(c, "101")
        s4 = await criar_sessao(c, "201")
        _, p3 = await enviar_ate_pendencia(c, s3, pedido)
        _, p4 = await enviar_ate_pendencia(c, s4, pedido)
        assert len(p3) == 1 and len(p4) == 1

        r3, r4 = await asyncio.gather(
            confirmar(c, s3, p3[0]["id"], True), confirmar(c, s4, p4[0]["id"], True)
        )
        assert (r3.status_code, r4.status_code) == (200, 200)

        total = da_area(await reservas(c, "101"), "salao-de-festas", "2030-05-11") + da_area(
            await reservas(c, "201"), "salao-de-festas", "2030-05-11"
        )
        assert len(total) == 1
