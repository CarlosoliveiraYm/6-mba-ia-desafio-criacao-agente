"""Tools de reservas de áreas comuns (F-07, F-09, F-10, F-11, F-12).

Garantias implementadas aqui:
- G-1: `reservar_area` só grava área com taxa depois da aprovação pelo sistema
  (`FunctionTool(..., require_confirmation=precisa_confirmar_reserva)`).
- G-2: o apartamento vem de `apartamento_da_sessao`; nenhum retorno traz dados de terceiros.
- G-5: a exclusividade é do banco (`repositorio.inserir_reserva`).
"""

from google.adk.tools import FunctionTool, ToolContext

from app.db import obter_engine
from app.db import repositorio as repo
from app.db.conexao import transacao
from app.tools._sessao import ERRO_DATA, apartamento_da_sessao, converter_data


async def _erro_area(conn) -> dict:
    validas = ", ".join(area.id for area in await repo.listar_areas(conn))
    return {"erro": f"área inválida; use uma destas: {validas}"}


async def verificar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict:
    """Informa se uma área comum está livre numa data.

    Args:
        area: salao-de-festas | churrasqueira | quadra
        data: data no formato AAAA-MM-DD
    """
    apartamento_da_sessao(tool_context)  # exige sessão válida
    dia = converter_data(data)
    if dia is None:
        return ERRO_DATA
    async with transacao(obter_engine()) as conn:
        area_obj = await repo.obter_area(conn, area)
        if area_obj is None:
            return await _erro_area(conn)
        ocupada = await repo.data_ocupada(conn, area, dia)
    return {
        "area": area,
        "data": dia.isoformat(),
        "disponivel": not ocupada,
        "taxa": float(area_obj.taxa),
    }


async def precisa_confirmar_reserva(area: str, data: str, tool_context: ToolContext) -> bool:
    """G-1 / RN-2: decide se `reservar_area` precisa de aprovação do morador.

    Tem a mesma assinatura de `reservar_area`, porque o ADK chama esta função com os
    mesmos argumentos da tool. Só pede confirmação quando a reserva vai gerar
    cobrança de fato: a área tem taxa e a data está livre. Entrada inválida ou data
    ocupada não pedem confirmação, porque a tool devolverá erro/recusa sem gravar nada.
    """
    apartamento_da_sessao(tool_context)
    dia = converter_data(data)
    if dia is None:
        return False
    async with transacao(obter_engine()) as conn:
        area_obj = await repo.obter_area(conn, area)
        if area_obj is None or not area_obj.gera_cobranca:
            return False
        return not await repo.data_ocupada(conn, area, dia)


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador numa data.

    Áreas com taxa só são reservadas depois que o morador aprova a cobrança pelo app.

    Args:
        area: salao-de-festas | churrasqueira | quadra
        data: data no formato AAAA-MM-DD
    """
    apartamento = apartamento_da_sessao(tool_context)
    dia = converter_data(data)
    if dia is None:
        return ERRO_DATA
    async with transacao(obter_engine()) as conn:
        area_obj = await repo.obter_area(conn, area)
        if area_obj is None:
            return await _erro_area(conn)
        codigo = await repo.inserir_reserva(conn, apartamento, area, dia)
    if codigo is None:
        return {"reservada": False, "area": area, "data": dia.isoformat(), "motivo": "data ocupada"}
    return {
        "reservada": True,
        "codigo": codigo,
        "area": area,
        "data": dia.isoformat(),
        "cobranca": area_obj.gera_cobranca,
        "taxa": float(area_obj.taxa),
    }


async def cancelar_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do próprio apartamento do morador.

    Args:
        area: salao-de-festas | churrasqueira | quadra
        data: data da reserva no formato AAAA-MM-DD
    """
    apartamento = apartamento_da_sessao(tool_context)
    dia = converter_data(data)
    if dia is None:
        return ERRO_DATA
    async with transacao(obter_engine()) as conn:
        if await repo.obter_area(conn, area) is None:
            return await _erro_area(conn)
        codigo = await repo.cancelar_reserva(conn, apartamento, area, dia)
    if codigo is None:
        return {
            "cancelada": False,
            "motivo": "nenhuma reserva sua encontrada para essa área e data",
        }
    return {"cancelada": True, "codigo": codigo, "area": area, "data": dia.isoformat()}


async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador."""
    apartamento = apartamento_da_sessao(tool_context)
    async with transacao(obter_engine()) as conn:
        reservas = await repo.listar_reservas(conn, apartamento)
    return {"reservas": reservas}


# O ADK aguarda (await) callables async em require_confirmation (FunctionTool._invoke_callable),
# mas anota o parâmetro como Callable[..., bool].
reservar_area_tool = FunctionTool(
    reservar_area,
    require_confirmation=precisa_confirmar_reserva,  # pyright: ignore[reportArgumentType]
)

TOOLS_RESERVAS = [
    verificar_disponibilidade,
    reservar_area_tool,
    cancelar_reserva,
    listar_minhas_reservas,
]
