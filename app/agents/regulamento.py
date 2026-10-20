"""Especialista de regulamento (F-19), acionado como AgentTool pelo principal.

G-4: o AgentTool roda o especialista num Runner próprio com sessão em memória. A saída
de `buscar_regulamento` fica nessa execução isolada; na sessão principal entram só a
chamada da AgentTool e a resposta curta do especialista.
"""

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from app.agents.modelo import BaseLlm, criar_modelo
from app.tools.regulamento import buscar_regulamento

NOME = "especialista_regulamento"

INSTRUCAO_REGULAMENTO = """\
Você responde dúvidas sobre o regulamento interno do Residencial Aurora.

- Sempre chame buscar_regulamento com a dúvida do morador antes de responder.
- Responda em no máximo 3 frases, somente sobre o que foi perguntado, citando o artigo \
(por exemplo: "conforme o Art. 22").
- Não transcreva artigos inteiros e não mencione regras de outros assuntos, mesmo que \
apareçam no trecho retornado.
- Se a busca não encontrar o assunto, diga que o regulamento não trata disso e que a \
dúvida pode ser enviada à administração pelo aplicativo.

Responda em português.
"""


def criar_especialista_regulamento(modelo: str | BaseLlm) -> AgentTool:
    agente = LlmAgent(
        name=NOME,
        model=criar_modelo(modelo),
        description=(
            "Responde dúvidas sobre as regras do regulamento interno do condomínio "
            "(horários, piscina, academia, animais, mudanças, obras, barulho, garagem, "
            "lixo, multas). Envie a pergunta do morador."
        ),
        instruction=INSTRUCAO_REGULAMENTO,
        tools=[buscar_regulamento],
    )
    # skip_summarization: a resposta curta do especialista vira a resposta final, sem uma
    # chamada extra do principal para reescrevê-la.
    return AgentTool(agent=agente, skip_summarization=True)
