"""Modelo Gemini com novas tentativas (resultado do spike F-00: 503 por sobrecarga)."""

from google.adk.models import BaseLlm, Gemini
from google.genai import types

__all__ = ["CODIGOS_RETENTAVEIS", "BaseLlm", "criar_modelo"]

CODIGOS_RETENTAVEIS = [429, 500, 503, 504]


def criar_modelo(modelo: str | BaseLlm) -> BaseLlm:
    """Gemini com backoff exponencial para cota excedida e sobrecarga temporária.

    Um `BaseLlm` já pronto (ex.: o LLM falso dos testes) é usado como está.
    """
    if isinstance(modelo, BaseLlm):
        return modelo
    return Gemini(
        model=modelo,
        retry_options=types.HttpRetryOptions(
            attempts=6,
            initial_delay=2,
            max_delay=30,
            exp_base=2,
            jitter=1,
            http_status_codes=CODIGOS_RETENTAVEIS,
        ),
    )
