"""Comando `uv run api`: sobe a API em http://localhost:8000 (F-27)."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="api", description="Sobe a API do Residencial Aurora em http://localhost:8000."
    )
    parser.parse_args()
    # A aplicação FastAPI (app.main) é implementada na iteração I-5 (F-21..F-27).
    sys.exit("A API ainda não foi implementada (F-27, iteração I-5).")


if __name__ == "__main__":
    main()
