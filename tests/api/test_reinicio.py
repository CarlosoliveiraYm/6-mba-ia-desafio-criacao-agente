"""G-3: reiniciar a API não perde conversas nem dados (passo 13, CA-19, CA-20)."""

from tests.api.conftest import api_rodando
from tests.api.test_contrato import confirmar, criar_sessao, enviar, reservas, salao


async def test_reinicio_preserva_eventos_e_permite_aprovar_pendencia_anterior(banco, config_teste):
    async with api_rodando(config_teste) as antes:
        sid = await criar_sessao(antes)
        await enviar(antes, sid, "Reserve a quadra para 2030-04-06.")
        r = await enviar(antes, sid, "Reserve o salão de festas para 2030-04-20.")
        [pendente] = r["confirmacoes_pendentes"]
        eventos_antes = (await antes.get(f"/sessoes/{sid}/eventos")).json()

    # Nova instância da API (novo Runner, novo DatabaseSessionService): como um Ctrl+C.
    async with api_rodando(config_teste) as depois:
        eventos_depois = (await depois.get(f"/sessoes/{sid}/eventos")).json()
        assert eventos_depois == eventos_antes

        aprovado = await confirmar(depois, sid, pendente["id"], True)
        assert aprovado.status_code == 200
        lista = await reservas(depois, "101")
        assert len(salao(lista, "2030-04-20")) == 1
        assert [x for x in lista if x["area"] == "quadra" and x["data"] == "2030-04-06"]

        r = await enviar(depois, sid, "Quais são as minhas reservas agora?")
        assert r["confirmacoes_pendentes"] == []
        total = len((await depois.get(f"/sessoes/{sid}/eventos")).json())
        assert total > len(eventos_antes)
