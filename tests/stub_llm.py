"""LLM falso e determinístico para os testes de API (F-28).

Substitui o Gemini em todos os agentes. Identifica qual agente está chamando pelas tools
disponíveis no `LlmRequest` e decide, por palavras-chave do pedido do morador, qual
function call emitir. Todo o resto é o ADK real: transferências, confirmação de tools,
retomada pelo Runner, AgentTool e persistência no PostgreSQL.
"""

import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

AREAS = {"salão": "salao-de-festas", "salao": "salao-de-festas", "churrasqueira": "churrasqueira"}
_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
_NOME = re.compile(r"entrada d[aeo] ([A-ZÁ-Ú][\wà-ú]+(?: [A-ZÁ-Ú][\wà-ú]+)+)")


def _chamada(funcao: str, /, **args: Any) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=funcao, args=args))],
        )
    )


def _texto(texto: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)]))


def _e_contexto(conteudo: types.Content) -> bool:
    """Mensagens de outros agentes chegam como ["For context:", "[agente] ..."]."""
    partes = conteudo.parts or []
    return bool(partes and partes[0].text and partes[0].text.startswith("For context"))


def _pedido_e_resultados(contents: list[types.Content]) -> tuple[str, list[dict]]:
    """Último texto do morador e os resultados de tools DESTE agente depois dele."""
    pedido, resultados = "", []
    for conteudo in contents:
        if _e_contexto(conteudo):
            continue
        for parte in conteudo.parts or []:
            if conteudo.role == "user" and parte.text:
                pedido, resultados = parte.text, []
            elif parte.function_response and parte.function_response.name != "transfer_to_agent":
                resultados.append(parte.function_response.response or {})
    return pedido, resultados


def _area(texto: str) -> str:
    minusculo = texto.lower()
    for chave, area in AREAS.items():
        if chave in minusculo:
            return area
    return "quadra"


def _resumo_do_regulamento(pedido: str, resultado: dict) -> str:
    """Como o especialista real: uma frase curta, sem transcrever artigos inteiros."""
    termos = [t[:-1] for t in re.findall(r"\w+", pedido.lower()) if len(t) > 4]
    linhas = [
        linha.strip() for trecho in resultado.get("trechos", []) for linha in trecho.splitlines()
    ]
    pontuadas = [(sum(t in linha.lower() for t in termos), linha) for linha in linhas if linha]
    if not pontuadas or max(p for p, _ in pontuadas) == 0:
        return "O regulamento não trata desse assunto."
    _, melhor = max(pontuadas, key=lambda item: item[0])
    return f"Conforme o capítulo {resultado['capitulo']}: {melhor}"


class LlmRoteirizado(BaseLlm):
    model: str = "llm-roteirizado"
    chamadas: int = 0

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"llm-roteirizado"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.chamadas += 1
        yield self._decidir(llm_request)

    def _decidir(self, req: LlmRequest) -> LlmResponse:
        tools = set(req.tools_dict)
        pedido, resultados = _pedido_e_resultados(list(req.contents))
        texto = pedido.lower()

        if resultados and "buscar_regulamento" in tools:
            return _texto(_resumo_do_regulamento(pedido, resultados[-1]))
        if resultados:  # já executou uma tool para este pedido: responde com o resultado
            return _texto(json.dumps(resultados[-1], ensure_ascii=False))

        if "buscar_regulamento" in tools:
            return _chamada("buscar_regulamento", consulta=pedido)

        if "especialista_regulamento" in tools:  # agente principal
            if any(p in texto for p in ("piscina", "regulamento", "horas")):
                return _chamada("especialista_regulamento", request=pedido)
            if any(p in texto for p in ("visitante", "entrada", "libera")):
                return _chamada("transfer_to_agent", agent_name="especialista_visitantes")
            return _chamada("transfer_to_agent", agent_name="especialista_reservas")

        data = (_DATA.findall(pedido) or [""])[0]
        if "reservar_area" in tools:  # especialista de reservas
            if any(p in texto for p in ("visitante", "entrada", "libera")):
                return _chamada("transfer_to_agent", agent_name="especialista_visitantes")
            if "cancel" in texto:
                return _chamada("cancelar_reserva", area=_area(pedido), data=data)
            if "reserv" in texto and data:
                return _chamada("reservar_area", area=_area(pedido), data=data)
            return _chamada("listar_minhas_reservas")

        if "autorizar_visitante" in tools:  # especialista de visitantes
            if "reserv" in texto or "cancel" in texto:
                return _chamada("transfer_to_agent", agent_name="especialista_reservas")
            nome = _NOME.search(pedido)
            if nome and data:
                return _chamada("autorizar_visitante", nome=nome.group(1), data=data)
            return _chamada("listar_meus_visitantes")

        return _texto("Olá! Como posso ajudar?")
