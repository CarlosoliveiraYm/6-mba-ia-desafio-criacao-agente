"""Comando `uv run api`: sobe a API em http://localhost:8000 (F-27)."""

import argparse
import logging
import warnings

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="api", description="Sobe a API do Residencial Aurora em http://localhost:8000."
    )
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 (API local do desafio)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Avisos de recursos experimentais do ADK poluem o log sem informação útil.
    warnings.filterwarnings("ignore", message=r"\[EXPERIMENTAL\]")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
