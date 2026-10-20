"""Leitura das configurações a partir do `.env` (F-03)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROJETO = Path(__file__).resolve().parent.parent


class ConfigErro(RuntimeError):
    """Configuração ausente ou inválida."""


@dataclass(frozen=True)
class Config:
    database_url: str
    google_api_key: str = ""
    modelo_principal: str = ""
    modelo_especialistas: str = ""
    app_name: str = "residencial_aurora"
    dir_dados: Path = RAIZ_PROJETO / "dados"

    def validar_gemini(self) -> None:
        """Exige as variáveis do Gemini. Só a API e os agentes precisam delas."""
        faltando = [
            nome
            for nome, valor in (
                ("GOOGLE_API_KEY", self.google_api_key),
                ("MODELO_PRINCIPAL", self.modelo_principal),
                ("MODELO_ESPECIALISTAS", self.modelo_especialistas),
            )
            if not valor
        ]
        if faltando:
            raise ConfigErro(_mensagem_faltando(faltando))


def carregar_config() -> Config:
    """Carrega o `.env` da raiz do projeto e devolve a configuração.

    `DATABASE_URL` é sempre obrigatória. As variáveis do Gemini são validadas por
    `Config.validar_gemini()`, para que `uv run restaurar` funcione sem a chave.
    """
    load_dotenv(RAIZ_PROJETO / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigErro(_mensagem_faltando(["DATABASE_URL"]))
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ConfigErro("DATABASE_URL deve usar o driver async: postgresql+asyncpg://...")
    return Config(
        database_url=database_url,
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        modelo_principal=os.getenv("MODELO_PRINCIPAL", "").strip(),
        modelo_especialistas=os.getenv("MODELO_ESPECIALISTAS", "").strip(),
    )


def _mensagem_faltando(nomes: list[str]) -> str:
    return (
        f"Variável(is) de ambiente ausente(s): {', '.join(nomes)}. "
        "Copie .env.example para .env e preencha os valores."
    )
