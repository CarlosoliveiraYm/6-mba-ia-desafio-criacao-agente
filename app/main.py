"""API HTTP do assistente do Residencial Aurora (F-21..F-27, contrato do PRD §9).

Garantias implementadas aqui:
- G-1: a rota de confirmações só aceita um `id` que esteja pendente nos eventos
  persistidos da sessão (relidos dentro da trava); qualquer outro recebe 409.
- G-2: o apartamento vem de `sessoes_apartamento`, gravado uma única vez na criação.
- G-3: sessões no `DatabaseSessionService` (PostgreSQL); nada relevante em memória.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, Session
from google.genai import types

from app.agents.app import criar_runner
from app.api.confirmacoes import extrair_pendencias, resposta_de_confirmacao
from app.api.respostas import texto_da_resposta
from app.api.schemas import (
    ConfirmacaoIn,
    ConfirmacaoPendenteOut,
    CriarSessaoIn,
    CriarSessaoOut,
    MensagemIn,
    ReservaOut,
    RespostaOut,
    VisitanteOut,
)
from app.config import Config, carregar_config
from app.db import encerrar_engine, engine_iniciado, iniciar_engine, obter_engine
from app.db import repositorio as repo
from app.db.conexao import aplicar_schema, transacao

log = logging.getLogger("aurora.api")

MENSAGEM_ERRO = "Desculpe, não consegui processar sua mensagem agora. Tente novamente em instantes."


class Assistente:
    """Runner + sessões. Só guarda objetos de infraestrutura, nenhum dado de negócio."""

    def __init__(self, cfg: Config, runner: Runner):
        self.cfg = cfg
        self.runner = runner
        # Serializa requisições da MESMA sessão neste processo; sessões diferentes
        # continuam concorrentes (passo 14). Não é estado de negócio.
        self._travas: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def trava(self, session_id: str) -> asyncio.Lock:
        return self._travas[session_id]

    async def carregar(self, session_id: str) -> tuple[str, Session]:
        async with transacao(obter_engine()) as conn:
            apartamento = await repo.apartamento_da_sessao(conn, session_id)
        if apartamento is None:
            raise HTTPException(404, "sessão não encontrada")
        sessao = await self.runner.session_service.get_session(
            app_name=self.runner.app_name, user_id=apartamento, session_id=session_id
        )
        if sessao is None:
            raise HTTPException(404, "sessão não encontrada")
        return apartamento, sessao

    async def executar(self, apartamento: str, session_id: str, mensagem: types.Content) -> str:
        eventos = []
        try:
            async for evento in self.runner.run_async(
                user_id=apartamento, session_id=session_id, new_message=mensagem
            ):
                eventos.append(evento)
        except Exception:
            # Erro do modelo (cota, indisponibilidade persistente) ou do runtime: resposta
            # normal ao morador, nunca 5xx. Nada é executado sem confirmação mesmo assim.
            log.exception("falha ao executar o turno da sessão %s", session_id)
            return MENSAGEM_ERRO
        return texto_da_resposta(eventos)

    async def responder(self, session_id: str, texto: str) -> RespostaOut:
        _, sessao = await self.carregar(session_id)
        pendentes = [
            ConfirmacaoPendenteOut(id=p.id, acao=p.acao, detalhes=p.detalhes)
            for p in extrair_pendencias(sessao.events)
        ]
        return RespostaOut(resposta=texto, confirmacoes_pendentes=pendentes)


def obter_assistente(request: Request) -> Assistente:
    return request.app.state.assistente


AssistenteDep = Annotated[Assistente, Depends(obter_assistente)]


def criar_api(cfg: Config | None = None, modelo: BaseLlm | None = None) -> FastAPI:
    """Fábrica da API. `modelo` substitui o Gemini (LLM falso dos testes)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = cfg or carregar_config()
        engine_externo = engine_iniciado()
        engine = iniciar_engine(config.database_url)
        await aplicar_schema(engine)
        runner = criar_runner(config, DatabaseSessionService(config.database_url), modelo)
        app.state.assistente = Assistente(config, runner)
        log.info("API pronta (app=%s)", config.app_name)
        yield
        if not engine_externo:
            await encerrar_engine()

    api = FastAPI(title="Residencial Aurora", lifespan=lifespan)

    @api.post("/sessoes", status_code=201, response_model=CriarSessaoOut)
    async def criar_sessao(corpo: CriarSessaoIn, assistente: AssistenteDep) -> CriarSessaoOut:
        apartamento = corpo.apartamento.strip()
        async with transacao(obter_engine()) as conn:
            if not await repo.apartamento_existe(conn, apartamento):
                raise HTTPException(404, "apartamento não encontrado")
        sessao = await assistente.runner.session_service.create_session(
            app_name=assistente.runner.app_name,
            user_id=apartamento,
            state={"apartamento": apartamento},
        )
        async with transacao(obter_engine()) as conn:
            await repo.vincular_sessao(conn, sessao.id, apartamento)
        return CriarSessaoOut(session_id=sessao.id)

    @api.post("/sessoes/{session_id}/mensagens", response_model=RespostaOut)
    async def enviar_mensagem(
        session_id: str, corpo: MensagemIn, assistente: AssistenteDep
    ) -> RespostaOut:
        apartamento, _ = await assistente.carregar(session_id)
        async with assistente.trava(session_id):
            mensagem = types.Content(role="user", parts=[types.Part(text=corpo.texto)])
            texto = await assistente.executar(apartamento, session_id, mensagem)
            return await assistente.responder(session_id, texto)

    @api.post(
        "/sessoes/{session_id}/confirmacoes",
        response_model=RespostaOut,
        responses={404: {"description": "sessão inexistente"}, 409: {"description": "id"}},
    )
    async def responder_confirmacao(
        session_id: str, corpo: ConfirmacaoIn, assistente: AssistenteDep
    ) -> RespostaOut:
        apartamento, _ = await assistente.carregar(session_id)
        async with assistente.trava(session_id):
            # Relê os eventos DENTRO da trava: um reenvio sequencial do mesmo id já encontra
            # a resposta anterior gravada e recebe 409 (G-1).
            _, sessao = await assistente.carregar(session_id)
            if corpo.id not in {p.id for p in extrair_pendencias(sessao.events)}:
                raise HTTPException(409, "não existe confirmação pendente com esse id nesta sessão")
            mensagem = resposta_de_confirmacao(corpo.id, corpo.confirmado)
            texto = await assistente.executar(apartamento, session_id, mensagem)
            return await assistente.responder(session_id, texto)

    @api.get("/sessoes/{session_id}/eventos")
    async def listar_eventos(session_id: str, assistente: AssistenteDep) -> list[dict[str, Any]]:
        _, sessao = await assistente.carregar(session_id)
        return [
            evento.model_dump(mode="json", exclude_none=True, by_alias=True)
            for evento in sessao.events
        ]

    @api.get("/apartamentos/{numero}/reservas", response_model=list[ReservaOut])
    async def reservas_do_apartamento(numero: str) -> list[dict[str, Any]]:
        async with transacao(obter_engine()) as conn:
            return await repo.listar_reservas(conn, numero)

    @api.get("/apartamentos/{numero}/visitantes", response_model=list[VisitanteOut])
    async def visitantes_do_apartamento(numero: str) -> list[dict[str, Any]]:
        async with transacao(obter_engine()) as conn:
            return await repo.listar_visitantes(conn, numero)

    return api


app = criar_api()
