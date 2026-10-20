"""Fixtures compartilhadas (F-28).

Os testes usam o database `aurora_test`, criado do zero no mesmo container do
PostgreSQL a cada execução do pytest. Nenhum teste desta pasta chama o Gemini.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google.adk.tools import ToolContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Config, carregar_config
from app.db import encerrar_engine, iniciar_engine
from scripts.restaurar import restaurar_dados

NOME_BANCO_TESTE = "aurora_test"


@pytest.fixture(scope="session")
def config() -> Config:
    return carregar_config()


@pytest.fixture(scope="session")
async def engine(config: Config) -> AsyncIterator[AsyncEngine]:
    url = make_url(config.database_url)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {NOME_BANCO_TESTE} WITH (FORCE)"))
        await conn.execute(text(f"CREATE DATABASE {NOME_BANCO_TESTE}"))
    await admin.dispose()

    url_teste = url.set(database=NOME_BANCO_TESTE).render_as_string(hide_password=False)
    yield iniciar_engine(url_teste)
    await encerrar_engine()


@pytest.fixture
async def banco(engine: AsyncEngine, config: Config) -> AsyncEngine:
    """Banco de teste restaurado ao estado de `dados/` antes de cada teste."""
    await restaurar_dados(engine, config.dir_dados)
    return engine


@pytest.fixture
def contexto() -> Callable[[str], ToolContext]:
    """Cria um ToolContext falso com o apartamento da sessão no state."""

    def _criar(apartamento: str) -> ToolContext:
        return cast(ToolContext, SimpleNamespace(state={"apartamento": apartamento}))

    return _criar


def sem_dados_do_302(valor: Any) -> bool:
    """True se o valor serializado não contém o código RSV-4821, Marina Duarte nem `302` isolado."""
    texto = json.dumps(valor, ensure_ascii=False)
    return (
        "RSV-4821" not in texto
        and "Marina Duarte" not in texto
        and re.search(r"(?<!\d)302(?!\d)", texto) is None
    )
