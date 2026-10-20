"""Acesso ao PostgreSQL. O engine é único por processo e compartilhado pelas tools."""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.conexao import criar_engine

_engine: AsyncEngine | None = None


def iniciar_engine(database_url: str) -> AsyncEngine:
    """Cria o engine do processo (chamado no lifespan da API e nos scripts)."""
    global _engine
    if _engine is None:
        _engine = criar_engine(database_url)
    return _engine


def engine_iniciado() -> bool:
    return _engine is not None


def obter_engine() -> AsyncEngine:
    """Engine do processo. Se ninguém o iniciou (ex.: `adk web`), cria a partir do `.env`."""
    if _engine is None:
        from app.config import carregar_config

        return iniciar_engine(carregar_config().database_url)
    return _engine


async def encerrar_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
