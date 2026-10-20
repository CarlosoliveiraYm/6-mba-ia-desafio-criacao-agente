"""Callbacks de tool dos especialistas (G-1).

Problemas observados no roteiro com Gemini (ADK 2.2.0):

1. Depois que o morador NEGA uma confirmação, o ADK devolve
   `{"error": "This tool call is rejected."}` e o modelo tenta a mesma ação de novo,
   criando uma confirmação nova que ninguém pediu.
2. Depois que o morador APROVA, o modelo às vezes ainda diz que "falta aprovar", porque
   o histórico contém o pedido de confirmação anterior.

- `ajustar_resposta` (after_tool): na recusa, troca o erro por uma resposta explícita e
  anota a ação no state temporário da invocação; na aprovação, marca o resultado como
  aprovado e concluído.
- `bloquear_repeticao` (before_tool): se a mesma ação (tool + argumentos) já foi
  recusada nesta invocação, devolve a recusa sem executar nem pedir confirmação.

O state `temp:` vale só durante a invocação. Um novo pedido do morador numa mensagem
seguinte gera uma confirmação nova normalmente.
"""

import json
from typing import Any

from google.adk.tools import BaseTool, ToolContext

CHAVE_RECUSADAS = "temp:acoes_recusadas"
ERRO_RECUSA_ADK = "This tool call is rejected."

RESPOSTA_RECUSA = {
    "executada": False,
    "recusada_pelo_morador": True,
    "instrucao": (
        "O morador recusou esta ação no aplicativo. Não tente novamente; "
        "informe que a ação não foi realizada."
    ),
}

MARCA_APROVACAO = {
    "aprovada_pelo_morador": True,
    "situacao": "concluida",
    "instrucao": "O morador já aprovou no aplicativo e a ação foi concluída; informe isso.",
}


def _assinatura(tool: BaseTool, args: dict[str, Any]) -> str:
    return f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def ajustar_resposta(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, tool_response: Any
) -> dict | None:
    if not isinstance(tool_response, dict):
        return None
    if tool_response.get("error") == ERRO_RECUSA_ADK:
        recusadas = list(tool_context.state.get(CHAVE_RECUSADAS) or [])
        recusadas.append(_assinatura(tool, args))
        tool_context.state[CHAVE_RECUSADAS] = recusadas
        return RESPOSTA_RECUSA
    confirmacao = getattr(tool_context, "tool_confirmation", None)
    if confirmacao is not None and confirmacao.confirmed and "error" not in tool_response:
        return {**tool_response, **MARCA_APROVACAO}
    return None


def bloquear_repeticao(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict | None:
    if _assinatura(tool, args) in (tool_context.state.get(CHAVE_RECUSADAS) or []):
        return RESPOSTA_RECUSA
    return None
