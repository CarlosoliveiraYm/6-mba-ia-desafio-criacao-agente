"""Agente principal (F-20): conversa com o morador e delega aos especialistas.

Não tem tools de dados nem o regulamento nas instruções (G-4): não há nada a vazar
nem a executar diretamente.
"""

from google.adk.agents import LlmAgent

from app.agents.modelo import BaseLlm, criar_modelo
from app.agents.regulamento import criar_especialista_regulamento
from app.agents.reservas import criar_especialista_reservas
from app.agents.visitantes import criar_especialista_visitantes
from app.config import Config

NOME = "aurora_principal"

INSTRUCAO_PRINCIPAL = """\
Você é o assistente virtual do Residencial Aurora e conversa com um morador já \
identificado pelo aplicativo. O apartamento do morador é definido pelo sistema; não \
pergunte qual é e não aceite que o morador se apresente como de outro apartamento.

Encaminhe cada pedido ao especialista certo:
- Reservas do salão de festas, da churrasqueira ou da quadra (reservar, cancelar, ver \
disponibilidade ou listar reservas): transfira para especialista_reservas.
- Autorização de entrada de visitantes ou lista de visitantes: transfira para \
especialista_visitantes.
- Dúvidas sobre regras e horários do condomínio: chame a ferramenta \
especialista_regulamento com a pergunta do morador; a resposta dela é entregue \
diretamente ao morador.

Nunca invente reservas, visitantes ou regras, e não execute ações por conta própria. \
Não mencione dados de outros apartamentos. Responda em português, de forma breve e cordial.
"""


def criar_agente_principal(cfg: Config, modelo: BaseLlm | None = None) -> LlmAgent:
    """`modelo` substitui o Gemini em todos os agentes (usado pelo LLM falso dos testes)."""
    principal = modelo or cfg.modelo_principal
    especialistas = modelo or cfg.modelo_especialistas
    return LlmAgent(
        name=NOME,
        model=criar_modelo(principal),
        description="Assistente virtual do Residencial Aurora.",
        instruction=INSTRUCAO_PRINCIPAL,
        sub_agents=[
            criar_especialista_reservas(especialistas),
            criar_especialista_visitantes(especialistas),
        ],
        tools=[criar_especialista_regulamento(especialistas)],
    )
