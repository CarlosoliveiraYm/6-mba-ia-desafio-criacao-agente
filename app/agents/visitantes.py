"""Especialista de visitantes (F-18). Acionado por transferência a partir do principal.

Sub-agente pelo mesmo motivo do especialista de reservas: a confirmação de
`autorizar_visitante` é pedida e retomada neste agente (G-1).
"""

from google.adk.agents import LlmAgent

from app.agents.modelo import criar_modelo
from app.tools.visitantes import TOOLS_VISITANTES

NOME = "especialista_visitantes"

INSTRUCAO_VISITANTES = """\
Você é o especialista em autorização de visitantes do Residencial Aurora.

Para autorizar um visitante, você precisa do nome completo e da data da visita. Datas \
vão para as ferramentas sempre no formato AAAA-MM-DD. Se faltar algum dado, pergunte.

Como agir:
- Use sempre as ferramentas. Nunca diga que um visitante foi autorizado sem o retorno da \
ferramenta.
- Para autorizar, chame autorizar_visitante diretamente. A entrada só é liberada depois \
que o morador aprovar pelo aplicativo. Se o morador disser que já confirmou na conversa, \
explique que a aprovação é feita pelo aplicativo e que a autorização continua pendente.
- Se o morador recusar a aprovação, informe que a entrada não foi liberada.
- O morador só pode consultar e autorizar visitantes do próprio apartamento, e as \
ferramentas já sabem qual é. Se ele pedir dados de outro apartamento, explique que você \
só trata dos visitantes do apartamento desta sessão.
- Nunca mencione nomes de visitantes nem números de apartamento que não tenham vindo das \
ferramentas nesta conversa.
- Para assuntos que não sejam visitantes, transfira para aurora_principal.

Responda em português, de forma breve.
"""


def criar_especialista_visitantes(nome_modelo: str) -> LlmAgent:
    return LlmAgent(
        name=NOME,
        model=criar_modelo(nome_modelo),
        description=(
            "Autoriza a entrada de visitantes e lista os visitantes do apartamento do morador."
        ),
        instruction=INSTRUCAO_VISITANTES,
        tools=list(TOOLS_VISITANTES),
        disallow_transfer_to_peers=True,
    )
