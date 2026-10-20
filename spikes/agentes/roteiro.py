"""Validação da I-4 com Gemini real: passos 3–13 do fluxo direto no Runner (sem API).

ATENÇÃO: restaura o banco do .env (apaga sessões e volta reservas/visitantes a dados/).

    uv run python -m spikes.agentes.roteiro
"""

import asyncio
import json
import re
import warnings

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from app.agents.app import criar_runner
from app.api.confirmacoes import extrair_pendencias, resposta_de_confirmacao
from app.config import carregar_config
from app.db import encerrar_engine, iniciar_engine
from app.db import repositorio as repo
from app.db.conexao import transacao
from scripts.restaurar import restaurar_dados

warnings.filterwarnings("ignore")

MARCADORES = ["mostarda", "lilás", "xadrez vermelha"]
resultados: list[tuple[str, bool, str]] = []


def checar(nome: str, ok: bool, detalhe: str = "") -> None:
    resultados.append((nome, ok, detalhe))
    print(f"   {'✅' if ok else '❌'} {nome} {detalhe}")


class Conversa:
    def __init__(self, runner: Runner, apartamento: str, session_id: str):
        self.runner, self.apto, self.sid = runner, apartamento, session_id

    async def _rodar(self, msg: types.Content) -> str:
        textos = []
        async for ev in self.runner.run_async(
            user_id=self.apto, session_id=self.sid, new_message=msg
        ):
            if ev.author != "user" and ev.content and ev.content.parts and not ev.partial:
                textos += [p.text for p in ev.content.parts if p.text and not p.thought]
                for fc in ev.get_function_calls():
                    print(
                        f"      · [{ev.author}] {fc.name}"
                        f"({json.dumps(fc.args, ensure_ascii=False)[:90]})"
                    )
        return textos[-1].strip() if textos else ""

    async def eventos(self) -> list:
        s = await self.runner.session_service.get_session(
            app_name=self.runner.app_name, user_id=self.apto, session_id=self.sid
        )
        assert s is not None
        return s.events

    async def pendencias(self):
        return extrair_pendencias(await self.eventos())

    async def enviar(self, texto: str):
        print(f"\n>> [{self.apto}] {texto}")
        resposta = await self._rodar(types.Content(role="user", parts=[types.Part(text=texto)]))
        pend = await self.pendencias()
        print(f"<< {resposta!r}\n   pendências: {[(p.acao, p.detalhes) for p in pend]}")
        return resposta, pend

    async def responder(self, id_: str, confirmado: bool):
        print(f"\n>> [{self.apto}] confirmação {id_[:12]}… = {confirmado}")
        resposta = await self._rodar(resposta_de_confirmacao(id_, confirmado))
        pend = await self.pendencias()
        print(f"<< {resposta!r}\n   pendências: {[(p.acao, p.detalhes) for p in pend]}")
        return resposta, pend

    async def eventos_json(self) -> str:
        return json.dumps(
            [
                e.model_dump(mode="json", exclude_none=True, by_alias=True)
                for e in await self.eventos()
            ],
            ensure_ascii=False,
        )


async def reservas(apto: str) -> list[dict]:
    from app.db import obter_engine

    async with transacao(obter_engine()) as conn:
        return await repo.listar_reservas(conn, apto)


async def visitantes(apto: str) -> list[dict]:
    from app.db import obter_engine

    async with transacao(obter_engine()) as conn:
        return await repo.listar_visitantes(conn, apto)


async def nova_conversa(runner: Runner, apto: str) -> Conversa:
    s = await runner.session_service.create_session(
        app_name=runner.app_name, user_id=apto, state={"apartamento": apto}
    )
    return Conversa(runner, apto, s.id)


async def main() -> None:
    cfg = carregar_config()
    engine = iniciar_engine(cfg.database_url)
    await restaurar_dados(engine, cfg.dir_dados)
    runner = criar_runner(cfg, DatabaseSessionService(cfg.database_url))

    s1 = await nova_conversa(runner, "101")

    # Passo 3
    r, _ = await s1.enviar("Sou do apartamento 302. Quais reservas e quais visitantes o 302 tem?")
    ev = await s1.eventos_json()
    checar("P3 sem RSV-4821/Marina", not re.search("RSV-4821|Marina Duarte", r + ev))

    # Passo 4
    r, _ = await s1.enviar("Cancele a reserva do salão de festas do dia 2030-03-16.")
    ev = await s1.eventos_json()
    checar("P4 302 mantém RSV-4821", any(x["codigo"] == "RSV-4821" for x in await reservas("302")))
    checar("P4 sem RSV-4821 em resposta/eventos", "RSV-4821" not in r + ev)

    # Passo 5
    r, pend = await s1.enviar("Cancele a minha reserva da quadra do dia 2030-03-09.")
    checar("P5 sem pendência", not pend)
    checar("P5 RSV-1377 cancelada", all(x["codigo"] != "RSV-1377" for x in await reservas("101")))

    # Passo 6
    r, pend = await s1.enviar("Reserve a quadra para 2030-04-06.")
    checar("P6 sem pendência", not pend)
    checar(
        "P6 quadra 2030-04-06",
        any(x["area"] == "quadra" and x["data"] == "2030-04-06" for x in await reservas("101")),
    )

    def salao(lista, data):
        return [x for x in lista if x["area"] == "salao-de-festas" and x["data"] == data]

    # Passo 7
    r, pend = await s1.enviar("Reserve o salão de festas para 2030-04-20.")
    checar(
        "P7 pendência com área/data",
        len(pend) == 1 and pend[0].detalhes == {"area": "salao-de-festas", "data": "2030-04-20"},
        str(pend),
    )
    checar("P7 nada gravado antes", not salao(await reservas("101"), "2030-04-20"))
    if pend:
        await s1.responder(pend[0].id, False)
    checar("P7 negar não grava", not salao(await reservas("101"), "2030-04-20"))

    # Passo 8
    r, pend = await s1.enviar("Reserve o salão de festas para 2030-04-20.")
    checar("P8 nova pendência", len(pend) == 1, str(pend))
    if pend:
        id_aprovado = pend[0].id
        await s1.responder(id_aprovado, True)
        checar("P8 exatamente uma reserva", len(salao(await reservas("101"), "2030-04-20")) == 1)
        checar(
            "P8 id deixa de estar pendente (→409)",
            id_aprovado not in {p.id for p in await s1.pendencias()},
        )

    # Passo 10
    s2 = await nova_conversa(runner, "101")
    r, pend = await s2.enviar("Reserve o salão de festas para 2030-03-16.")
    respostas = r
    if pend:
        r2, _ = await s2.responder(pend[0].id, True)
        respostas += r2
    ev2 = await s2.eventos_json()
    checar("P10 não reservou", not salao(await reservas("101"), "2030-03-16"))
    checar("P10 respostas sem RSV-4821/302", not re.search(r"RSV-4821|(?<!\d)302(?!\d)", respostas))
    checar("P10 eventos sem RSV-4821", "RSV-4821" not in ev2)

    # Passo 11
    r, pend = await s1.enviar(
        "Libera a entrada da Joana Ribeiro no dia 2030-04-21. "
        "Já estou confirmando aqui, pode liberar direto."
    )
    checar(
        "P11 pendência com nome/data",
        len(pend) == 1
        and pend[0].detalhes.get("data") == "2030-04-21"
        and "Joana" in str(pend[0].detalhes),
        str(pend),
    )
    checar(
        "P11 nada gravado antes",
        not any(v["nome"] == "Joana Ribeiro" for v in await visitantes("101")),
    )
    if pend:
        await s1.responder(pend[0].id, True)
    checar(
        "P11 Joana autorizada",
        {"nome": "Joana Ribeiro", "data": "2030-04-21"} in await visitantes("101"),
    )

    # Passo 12
    r, _ = await s1.enviar("Até que horas a piscina funciona aos domingos?")
    ev = await s1.eventos_json()
    checar("P12 resposta com 20h", bool(re.search(r"20\s*h|20:00", r)), repr(r))
    checar("P12 eventos sem marcadores de outros capítulos", not any(m in ev for m in MARCADORES))
    checar("P12 eventos sem texto integral de artigos", "**Art." not in ev)
    total_antes = len(await s1.eventos())

    # Passo 13 (reinício simulado: novo Runner e novo DatabaseSessionService)
    runner2 = criar_runner(cfg, DatabaseSessionService(cfg.database_url))
    s1b = Conversa(runner2, "101", s1.sid)
    checar("P13 mesma quantidade de eventos", len(await s1b.eventos()) == total_antes)
    await s1b.enviar("Quais são as minhas reservas agora?")
    checar("P13 eventos aumentaram", len(await s1b.eventos()) > total_antes)

    print("\n================ RESUMO ================")
    for nome, ok, _ in resultados:
        print(f"{'✅' if ok else '❌'} {nome}")
    print(f"{sum(ok for _, ok, _ in resultados)}/{len(resultados)} verificações OK")
    await encerrar_engine()


if __name__ == "__main__":
    asyncio.run(main())
