"""Modelo Gemini com novas tentativas (resultado do spike F-00: 503 por sobrecarga)."""

from google.adk.models import Gemini
from google.genai import types

CODIGOS_RETENTAVEIS = [429, 500, 503, 504]


def criar_modelo(nome: str) -> Gemini:
    """Gemini com backoff exponencial para cota excedida e sobrecarga temporária."""
    return Gemini(
        model=nome,
        retry_options=types.HttpRetryOptions(
            attempts=6,
            initial_delay=2,
            max_delay=30,
            exp_base=2,
            jitter=1,
            http_status_codes=CODIGOS_RETENTAVEIS,
        ),
    )
