"""Fixtures da API: app real (FastAPI + ADK + PostgreSQL de teste) com LLM falso."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Config
from app.main import criar_api
from tests.stub_llm import LlmRoteirizado


@pytest.fixture(scope="session")
def config_teste(config: Config, engine: AsyncEngine) -> Config:
    return replace(config, database_url=engine.url.render_as_string(hide_password=False))


@asynccontextmanager
async def api_rodando(config: Config) -> AsyncIterator[httpx.AsyncClient]:
    """Sobe uma instância nova da API (lifespan completo): equivale a iniciar o processo."""
    api = criar_api(config, LlmRoteirizado())
    async with api.router.lifespan_context(api):
        transporte = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as cliente:
            yield cliente


@pytest.fixture
async def cliente(banco: AsyncEngine, config_teste: Config) -> AsyncIterator[httpx.AsyncClient]:
    async with api_rodando(config_teste) as c:
        yield c
