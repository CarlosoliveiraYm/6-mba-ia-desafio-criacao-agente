"""Spike F-00: retomada da confirmação de tool com sessão PostgreSQL e reinício.

Código descartável, fora do pacote `app`. Uso:

    # mesmo processo (pede e responde)
    uv run python -m spikes.confirmacao.spike completo --variante a --confirmado sim

    # reinício: pede num processo, responde em outro
    uv run python -m spikes.confirmacao.spike pedir
    uv run python -m spikes.confirmacao.spike responder --variante a --confirmado sim

Variantes:
    a = só new_message com a FunctionResponse
    b = new_message + invocation_id do evento de confirmação
"""

import argparse
import asyncio
import json
import logging
import uuid
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import Event
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import FunctionTool, ToolContext
from google.genai import types
from sqlalchemy import text

from app.config import carregar_config
from app.db import encerrar_engine, iniciar_engine, obter_engine
from app.db.conexao import transacao

APP_NAME = "spike_confirmacao"
USER_ID = "101"
NOME_CONFIRMACAO = "adk_request_confirmation"
ARQUIVO_ESTADO = Path(__file__).with_name("estado.json")

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("aurora.spike")

chamadas_llm = 0


def contar_chamada(callback_context, llm_request):  # noqa: ARG001
    global chamadas_llm
    chamadas_llm += 1
    return None


async def acao_cobrada(descricao: str, tool_context: ToolContext) -> dict:
    """Executa uma ação que gera cobrança. descricao: identificador da ação."""
    async with transacao(obter_engine()) as conn:
        await conn.execute(
            text("INSERT INTO spike_acoes (descricao) VALUES (:d)"), {"d": descricao}
        )
    return {"executada": True, "descricao": descricao}


def criar_modelo(nome: str) -> Gemini:
    """Gemini com novas tentativas e backoff exponencial para sobrecarga e cota."""
    return Gemini(
        model=nome,
        retry_options=types.HttpRetryOptions(
            attempts=6,
            initial_delay=2,
            max_delay=30,
            exp_base=2,
            jitter=1,
            http_status_codes=[429, 500, 503, 504],
        ),
    )


def criar_runner(nome_modelo: str, database_url: str, travar_parent: bool) -> Runner:
    modelo = criar_modelo(nome_modelo)
    especialista = LlmAgent(
        name="especialista_cobrancas",
        model=modelo,
        description="Executa ações que geram cobrança.",
        instruction=(
            "Quando pedirem para executar uma ação cobrada, chame a tool acao_cobrada "
            "com a descrição informada. Não peça confirmação por texto."
        ),
        tools=[FunctionTool(acao_cobrada, require_confirmation=True)],
        disallow_transfer_to_peers=True,
        disallow_transfer_to_parent=travar_parent,
        before_model_callback=contar_chamada,
    )
    root = LlmAgent(
        name="principal",
        model=modelo,
        description="Agente principal.",
        instruction=("Você só encaminha. Pedidos de ação cobrada vão para especialista_cobrancas."),
        sub_agents=[especialista],
        before_model_callback=contar_chamada,
    )
    app = App(
        name=APP_NAME,
        root_agent=root,
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
    return Runner(app=app, session_service=DatabaseSessionService(database_url))


def pendencias(eventos: list[Event]) -> dict[str, Event]:
    """id da confirmação → evento que a pediu, para as que ainda não têm resposta."""
    pedidas: dict[str, Event] = {}
    respondidas: set[str] = set()
    for ev in eventos:
        for fc in ev.get_function_calls():
            if fc.name == NOME_CONFIRMACAO and fc.id:
                pedidas[fc.id] = ev
        for fr in ev.get_function_responses():
            if fr.name == NOME_CONFIRMACAO and fr.id:
                respondidas.add(fr.id)
    return {k: v for k, v in pedidas.items() if k not in respondidas}


async def contar_execucoes(descricao: str) -> int:
    async with transacao(obter_engine()) as conn:
        r = await conn.execute(
            text("SELECT count(*) FROM spike_acoes WHERE descricao = :d"), {"d": descricao}
        )
        return int(r.scalar_one())


async def rodar(runner: Runner, session_id: str, msg: types.Content, inv: str | None) -> str:
    textos = []
    async for ev in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=msg, invocation_id=inv
    ):
        if ev.content and ev.content.parts and ev.author != "user":
            textos += [p.text for p in ev.content.parts if p.text and not p.thought]
            for fc in ev.get_function_calls():
                log.warning("  [%s] function_call %s", ev.author, fc.name)
            for fr in ev.get_function_responses():
                log.warning("  [%s] function_response %s -> %s", ev.author, fr.name, fr.response)
    return textos[-1] if textos else ""


async def pedir(runner: Runner) -> dict:
    descricao = f"teste-{uuid.uuid4().hex[:8]}"
    sessao = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    msg = types.Content(
        role="user", parts=[types.Part(text=f"Execute a ação cobrada com a descrição {descricao}.")]
    )
    resposta = await rodar(runner, sessao.id, msg, None)
    s = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=sessao.id
    )
    assert s is not None
    pend = pendencias(s.events)
    estado = {
        "session_id": sessao.id,
        "descricao": descricao,
        "pendencias": {k: ev.invocation_id for k, ev in pend.items()},
        "execucoes_antes": await contar_execucoes(descricao),
        "resposta": resposta,
    }
    print(json.dumps(estado, ensure_ascii=False, indent=2))
    return estado


async def responder(runner: Runner, estado: dict, variante: str, confirmado: bool) -> dict:
    session_id = estado["session_id"]
    conf_id, inv = next(iter(estado["pendencias"].items()))
    msg = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=conf_id, name=NOME_CONFIRMACAO, response={"confirmed": confirmado}
                )
            )
        ],
    )
    resposta = await rodar(runner, session_id, msg, inv if variante == "b" else None)
    s = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    assert s is not None
    resultado = {
        "variante": variante,
        "confirmado": confirmado,
        "execucoes": await contar_execucoes(estado["descricao"]),
        "esperado": 1 if confirmado else 0,
        "id_ainda_pendente": conf_id in pendencias(s.events),
        "resposta": resposta,
    }
    resultado["OK"] = (
        resultado["execucoes"] == resultado["esperado"] and not resultado["id_ainda_pendente"]
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return resultado


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("comando", choices=["pedir", "responder", "completo"])
    p.add_argument("--variante", choices=["a", "b"], default="a")
    p.add_argument("--confirmado", choices=["sim", "nao"], default="sim")
    p.add_argument("--travar-parent", action="store_true")
    args = p.parse_args()

    cfg = carregar_config()
    cfg.validar_gemini()
    engine = iniciar_engine(cfg.database_url)
    async with transacao(engine) as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS spike_acoes ("
                "id BIGSERIAL PRIMARY KEY, descricao TEXT NOT NULL, "
                "criado_em TIMESTAMPTZ DEFAULT now())"
            )
        )
    runner = criar_runner(cfg.modelo_especialistas, cfg.database_url, args.travar_parent)
    confirmado = args.confirmado == "sim"
    try:
        if args.comando == "pedir":
            estado = await pedir(runner)
            ARQUIVO_ESTADO.write_text(json.dumps(estado), encoding="utf-8")
        elif args.comando == "responder":
            estado = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
            await responder(runner, estado, args.variante, confirmado)
        else:
            estado = await pedir(runner)
            if estado["pendencias"]:
                await responder(runner, estado, args.variante, confirmado)
        print(f"chamadas ao LLM neste processo: {chamadas_llm}")
    finally:
        await encerrar_engine()


if __name__ == "__main__":
    asyncio.run(main())
