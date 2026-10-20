"""Conexões assíncronas com o PostgreSQL (F-05)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

ARQUIVO_SCHEMA = Path(__file__).with_name("schema.sql")


def criar_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


@asynccontextmanager
async def transacao(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Abre uma conexão com transação: commit ao sair, rollback em exceção."""
    async with engine.begin() as conn:
        yield conn


def _comandos_do_schema() -> list[str]:
    """Separa o schema.sql em comandos (o asyncpg executa um comando por vez)."""
    linhas = [
        linha.split("--", 1)[0] for linha in ARQUIVO_SCHEMA.read_text(encoding="utf-8").splitlines()
    ]
    return [cmd.strip() for cmd in "\n".join(linhas).split(";") if cmd.strip()]


async def aplicar_schema(engine: AsyncEngine) -> None:
    """Cria tabelas, sequence e índices do condomínio, se ainda não existirem."""
    async with transacao(engine) as conn:
        for comando in _comandos_do_schema():
            await conn.execute(text(comando))
