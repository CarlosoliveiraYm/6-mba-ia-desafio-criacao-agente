"""Tools de visitantes (F-13, F-14).

- G-1 / RN-3: autorizar um visitante libera acesso; só grava depois da aprovação pelo
  sistema. A frase "já confirmei" na conversa não tem efeito.
- G-2: o apartamento vem de `apartamento_da_sessao`.
"""

from google.adk.tools import FunctionTool, ToolContext

from app.db import obter_engine
from app.db import repositorio as repo
from app.db.conexao import transacao
from app.tools._sessao import ERRO_DATA, apartamento_da_sessao, converter_data

ERRO_NOME = {"erro": "informe o nome completo do visitante"}


def _normalizar_nome(nome: str) -> str:
    return " ".join((nome or "").split())


async def precisa_confirmar_visitante(nome: str, data: str, tool_context: ToolContext) -> bool:
    """G-1: toda autorização válida de visitante exige aprovação do morador.

    Entrada inválida não pede confirmação: a tool devolve erro sem liberar acesso.
    """
    apartamento_da_sessao(tool_context)
    return bool(_normalizar_nome(nome)) and converter_data(data) is not None


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio numa data.

    A autorização só é gravada depois que o morador aprova pelo app.

    Args:
        nome: nome completo do visitante
        data: data da visita no formato AAAA-MM-DD
    """
    apartamento = apartamento_da_sessao(tool_context)
    nome_limpo = _normalizar_nome(nome)
    if not nome_limpo:
        return ERRO_NOME
    dia = converter_data(data)
    if dia is None:
        return ERRO_DATA
    async with transacao(obter_engine()) as conn:
        await repo.inserir_visitante(conn, apartamento, nome_limpo, dia)
    return {"autorizado": True, "nome": nome_limpo, "data": dia.isoformat()}


async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados do apartamento do morador."""
    apartamento = apartamento_da_sessao(tool_context)
    async with transacao(obter_engine()) as conn:
        visitantes = await repo.listar_visitantes(conn, apartamento)
    return {"visitantes": visitantes}


# Ver nota em app/tools/reservas.py sobre callables async em require_confirmation.
autorizar_visitante_tool = FunctionTool(
    autorizar_visitante,
    require_confirmation=precisa_confirmar_visitante,  # pyright: ignore[reportArgumentType]
)

TOOLS_VISITANTES = [autorizar_visitante_tool, listar_meus_visitantes]
