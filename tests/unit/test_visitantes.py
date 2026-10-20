"""F-13, F-14: tools de visitantes (RN-3, G-2, idempotência A-2)."""

from sqlalchemy import text

from app.db.conexao import transacao
from app.tools.visitantes import autorizar_visitante, listar_meus_visitantes
from tests.conftest import sem_dados_do_302


async def test_autoriza_visitante_com_nome_e_data(banco, contexto):
    r = await autorizar_visitante("  Joana   Ribeiro ", "2030-04-21", contexto("101"))
    assert r == {"autorizado": True, "nome": "Joana Ribeiro", "data": "2030-04-21"}
    assert await listar_meus_visitantes(contexto("101")) == {
        "visitantes": [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]
    }


async def test_autorizacao_repetida_nao_duplica(banco, contexto):
    """V-7: a retomada do ADK é at-least-once; a PK composta evita duplicidade."""
    await autorizar_visitante("Joana Ribeiro", "2030-04-21", contexto("101"))
    await autorizar_visitante("Joana Ribeiro", "2030-04-21", contexto("101"))
    async with transacao(banco) as conn:
        total = (
            await conn.execute(text("SELECT count(*) FROM visitantes WHERE apartamento = '101'"))
        ).scalar_one()
    assert total == 1


async def test_entrada_invalida_nao_grava(banco, contexto):
    assert "erro" in await autorizar_visitante("   ", "2030-04-21", contexto("101"))
    assert "erro" in await autorizar_visitante("Joana Ribeiro", "21/04/2030", contexto("101"))
    assert (await listar_meus_visitantes(contexto("101")))["visitantes"] == []


async def test_listagem_nao_traz_visitantes_de_outro_apartamento(banco, contexto):
    r = await listar_meus_visitantes(contexto("101"))
    assert r == {"visitantes": []}
    assert sem_dados_do_302(r)
