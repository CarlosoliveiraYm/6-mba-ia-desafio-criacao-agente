"""G-5: dois moradores aprovam a mesma área e data ao mesmo tempo (passo 14, CA-24, CA-25)."""

import asyncio

from tests.api.test_contrato import confirmar, criar_sessao, enviar, reservas, salao

PEDIDO = "Reserve o salão de festas para 2030-05-11."


async def test_aprovacoes_simultaneas_gravam_uma_unica_reserva(cliente):
    s3 = await criar_sessao(cliente, "101")
    s4 = await criar_sessao(cliente, "201")
    [p3] = (await enviar(cliente, s3, PEDIDO))["confirmacoes_pendentes"]
    [p4] = (await enviar(cliente, s4, PEDIDO))["confirmacoes_pendentes"]

    r3, r4 = await asyncio.gather(
        confirmar(cliente, s3, p3["id"], True),
        confirmar(cliente, s4, p4["id"], True),
    )

    assert (r3.status_code, r4.status_code) == (200, 200)
    total = salao(await reservas(cliente, "101"), "2030-05-11") + salao(
        await reservas(cliente, "201"), "2030-05-11"
    )
    assert len(total) == 1
