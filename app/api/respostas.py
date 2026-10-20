"""Texto da resposta ao morador a partir dos eventos de um turno (F-22)."""

from google.adk.events import Event


def _texto_do_evento(evento: Event) -> str:
    if evento.author == "user" or not evento.content or not evento.content.parts:
        return ""
    if evento.partial:
        return ""
    textos = [p.text for p in evento.content.parts if p.text and not p.thought]
    if textos:
        return "\n".join(textos).strip()
    # AgentTool com skip_summarization (especialista de regulamento): a resposta final do
    # turno é a function response da AgentTool, não um texto do modelo.
    if evento.actions and evento.actions.skip_summarization:
        for resposta in evento.get_function_responses():
            resultado = (resposta.response or {}).get("result")
            if isinstance(resultado, str) and resultado.strip():
                return resultado.strip()
    return ""


def texto_da_resposta(eventos: list[Event]) -> str:
    """Último texto produzido pelos agentes no turno; "" se a execução pausou (confirmação)."""
    texto = ""
    for evento in eventos:
        texto = _texto_do_evento(evento) or texto
    return texto
