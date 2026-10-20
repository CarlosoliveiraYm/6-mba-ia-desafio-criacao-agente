"""Comando `uv run restaurar`: volta o condomínio ao estado de `dados/` (F-06).

Na iteração I-0 só aplica o schema. A carga de `dados/` e a limpeza das sessões
entram na F-06 (iteração I-2).
"""

import argparse
import asyncio
import sys

from app.config import ConfigErro, carregar_config
from app.db import encerrar_engine, iniciar_engine
from app.db.conexao import aplicar_schema


async def restaurar() -> None:
    cfg = carregar_config()
    engine = iniciar_engine(cfg.database_url)
    try:
        await aplicar_schema(engine)
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
    print("Schema aplicado. Carga de dados/ ainda não implementada (F-06, iteração I-2).")


if __name__ == "__main__":
    main()
