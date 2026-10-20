"""Helpers dos testes E2E (F-29): API real em execução + Gemini real.

Fluxo completo:
    uv run restaurar && uv run api                                   # terminal 1
    uv run pytest -m e2e tests/e2e/test_antes_do_reinicio.py         # terminal 2
    (Ctrl+C no terminal 1 e `uv run api` de novo, sem restaurar)
    uv run pytest -m e2e tests/e2e/test_depois_do_reinicio.py        # terminal 2
"""

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.getenv("AURORA_BASE_URL", "http://localhost:8000")
ARQUIVO_ESTADO = Path(__file__).with_name("estado.json")
TIMEOUT = httpx.Timeout(300.0)  # chamadas ao Gemini com novas tentativas podem demorar

CODIGOS_INICIAIS = {"RSV-1377", "RSV-4821", "RSV-2950"}
MARCADORES_OUTROS_CAPITULOS = ("mostarda", "lilás", "xadrez vermelha")
APARTAMENTO_302_ISOLADO = re.compile(r"(?<!\d)302(?!\d)")
RESPOSTA_PADRAO = "Sim, pode seguir com o pedido."


def cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)


async def criar_sessao(c: httpx.AsyncClient, apartamento: str) -> str:
    r = await c.post("/sessoes", json={"apartamento": apartamento})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


async def enviar(c: httpx.AsyncClient, sid: str, texto: str) -> dict[str, Any]:
    r = await c.post(f"/sessoes/{sid}/mensagens", json={"texto": texto})
    assert r.status_code == 200, r.text
    return r.json()


async def enviar_ate_pendencia(
    c: httpx.AsyncClient, sid: str, texto: str, tentativas: int = 2
) -> tuple[list[dict], list[dict]]:
    """Envia o pedido; se o assistente perguntar algo em vez de agir, responde como o
    avaliador faria. Devolve (respostas, pendências)."""
    respostas = [await enviar(c, sid, texto)]
    while not respostas[-1]["confirmacoes_pendentes"] and tentativas > 0:
        if not respostas[-1]["resposta"].rstrip().endswith("?"):
            break
        respostas.append(await enviar(c, sid, RESPOSTA_PADRAO))
        tentativas -= 1
    return respostas, respostas[-1]["confirmacoes_pendentes"]


async def confirmar(c: httpx.AsyncClient, sid: str, id_: str, ok: bool) -> httpx.Response:
    return await c.post(f"/sessoes/{sid}/confirmacoes", json={"id": id_, "confirmado": ok})


async def reservas(c: httpx.AsyncClient, apartamento: str) -> list[dict]:
    r = await c.get(f"/apartamentos/{apartamento}/reservas")
    assert r.status_code == 200
    return r.json()


async def visitantes(c: httpx.AsyncClient, apartamento: str) -> list[dict]:
    r = await c.get(f"/apartamentos/{apartamento}/visitantes")
    assert r.status_code == 200
    return r.json()


async def eventos(c: httpx.AsyncClient, sid: str) -> list[dict]:
    r = await c.get(f"/sessoes/{sid}/eventos")
    assert r.status_code == 200
    return r.json()


def texto(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)


def da_area(lista: list[dict], area: str, data: str) -> list[dict]:
    return [x for x in lista if x["area"] == area and x["data"] == data]


def salvar_estado(estado: dict[str, Any]) -> None:
    ARQUIVO_ESTADO.write_text(json.dumps(estado, indent=2), encoding="utf-8")


def ler_estado() -> dict[str, Any]:
    return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
