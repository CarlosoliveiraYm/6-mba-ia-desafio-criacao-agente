"""Comando `uv run restaurar`: volta o condomínio ao estado de `dados/` (F-06).

1. Aplica o schema (idempotente).
2. Faz upsert de apartamentos e áreas.
3. Recarrega reservas e visitantes a partir de `dados/`.
4. Apaga todas as sessões (tabelas do ADK e `sessoes_apartamento`).
5. NÃO reinicia `seq_codigo_reserva`, para códigos novos nunca repetirem (RN-5).

Os arquivos de `dados/` só são lidos, nunca alterados.
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.config import ConfigErro, carregar_config
from app.db import encerrar_engine, iniciar_engine
from app.db.conexao import aplicar_schema, transacao

# Ordem respeita as chaves estrangeiras do ADK (events → sessions).
TABELAS_SESSAO_ADK = ("events", "sessions", "app_states", "user_states")


def _ler_json(dir_dados: Path, nome: str) -> list[dict]:
    return json.loads((dir_dados / nome).read_text(encoding="utf-8"))


async def _tabela_existe(conn: AsyncConnection, tabela: str) -> bool:
    resultado = await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{tabela}"})
    return resultado.scalar_one() is not None


async def apagar_sessoes(conn: AsyncConnection) -> None:
    """Apaga sessões do ADK (se as tabelas já existirem) e os vínculos sessão → apartamento."""
    for tabela in TABELAS_SESSAO_ADK:
        if await _tabela_existe(conn, tabela):
            await conn.execute(text(f"DELETE FROM {tabela}"))  # noqa: S608 (nome fixo)
    await conn.execute(text("DELETE FROM sessoes_apartamento"))


async def restaurar_dados(engine: AsyncEngine, dir_dados: Path) -> None:
    await aplicar_schema(engine)
    apartamentos = _ler_json(dir_dados, "apartamentos.json")
    areas = _ler_json(dir_dados, "areas.json")
    reservas = _ler_json(dir_dados, "reservas.json")
    visitantes = _ler_json(dir_dados, "visitantes.json")

    async with transacao(engine) as conn:
        await apagar_sessoes(conn)
        await conn.execute(text("DELETE FROM reservas"))
        await conn.execute(text("DELETE FROM visitantes"))
        await conn.execute(
            text(
                "INSERT INTO apartamentos (numero, morador) VALUES (:numero, :morador) "
                "ON CONFLICT (numero) DO UPDATE SET morador = EXCLUDED.morador"
            ),
            apartamentos,
        )
        await conn.execute(
            text(
                "INSERT INTO areas (id, nome, taxa) VALUES (:id, :nome, :taxa) "
                "ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, taxa = EXCLUDED.taxa"
            ),
            areas,
        )
        await conn.execute(
            text(
                "INSERT INTO reservas (codigo, apartamento, area, data, status) "
                "VALUES (:codigo, :apartamento, :area, :data, 'ativa')"
            ),
            [{**r, "data": date.fromisoformat(r["data"])} for r in reservas],
        )
        await conn.execute(
            text(
                "INSERT INTO visitantes (apartamento, nome, data) "
                "VALUES (:apartamento, :nome, :data)"
            ),
            [{**v, "data": date.fromisoformat(v["data"])} for v in visitantes],
        )


async def restaurar() -> None:
    cfg = carregar_config()
    engine = iniciar_engine(cfg.database_url)
    try:
        await restaurar_dados(engine, cfg.dir_dados)
    finally:
        await encerrar_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="restaurar",
        description="Restaura reservas e visitantes ao estado de dados/ e apaga as sessões.",
    )
    parser.parse_args()
    try:
        asyncio.run(restaurar())
    except ConfigErro as erro:
        sys.exit(str(erro))
    print("Dados restaurados a partir de dados/ e sessões apagadas.")


if __name__ == "__main__":
    main()
