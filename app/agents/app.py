"""App resumível e Runner do assistente (F-20).

`ResumabilityConfig(is_resumable=True)` é obrigatório: sem ele o Runner não devolve a
resposta da confirmação ao agente que a pediu, e a ação aprovada não executa (FDD V-6).
"""

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService

from app.agents.principal import criar_agente_principal
from app.config import Config


def criar_app(cfg: Config) -> App:
    cfg.validar_gemini()
    return App(
        name=cfg.app_name,
        root_agent=criar_agente_principal(cfg),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


def criar_runner(cfg: Config, session_service: BaseSessionService) -> Runner:
    return Runner(app=criar_app(cfg), session_service=session_service)
