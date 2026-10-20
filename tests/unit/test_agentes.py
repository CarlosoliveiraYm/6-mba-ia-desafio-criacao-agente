"""F-17..F-20: topologia dos agentes, sem chamar o LLM (CA-05, CA-23, G-1, G-4)."""

import re

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import AgentTool

from app.agents.app import criar_app
from app.agents.modelo import CODIGOS_RETENTAVEIS
from app.agents.principal import INSTRUCAO_PRINCIPAL
from app.tools.regulamento import carregar_regulamento
from app.tools.reservas import reservar_area_tool
from app.tools.visitantes import autorizar_visitante_tool


@pytest.fixture(scope="module")
def app_adk(config):
    return criar_app(config)


def _agentes(raiz: LlmAgent) -> list[LlmAgent]:
    agentes = [raiz]
    for sub in raiz.sub_agents:
        agentes += _agentes(sub)  # type: ignore[arg-type]
    for tool in raiz.tools:
        if isinstance(tool, AgentTool):
            agentes += _agentes(tool.agent)  # type: ignore[arg-type]
    return agentes


def test_app_e_resumivel(app_adk):
    """V-6: sem is_resumable a aprovação não chega ao especialista."""
    assert app_adk.resumability_config is not None
    assert app_adk.resumability_config.is_resumable is True


def test_principal_tem_dois_subagentes_e_o_regulamento_como_agent_tool(app_adk):
    raiz = app_adk.root_agent
    assert raiz.name == "aurora_principal"
    assert [s.name for s in raiz.sub_agents] == ["especialista_reservas", "especialista_visitantes"]
    assert [t.agent.name for t in raiz.tools if isinstance(t, AgentTool)] == [
        "especialista_regulamento"
    ]
    # O principal não tem tools de dados: só a AgentTool do regulamento.
    assert all(isinstance(t, AgentTool) for t in raiz.tools)
    assert all(t.skip_summarization for t in raiz.tools if isinstance(t, AgentTool))


def test_tools_confirmaveis_ficam_nos_subagentes(app_adk):
    reservas, visitantes = app_adk.root_agent.sub_agents
    assert reservar_area_tool in reservas.tools
    assert autorizar_visitante_tool in visitantes.tools
    assert all(not isinstance(t, FunctionTool) or t.func.__name__ != "reservar_area"
               for t in visitantes.tools)  # fmt: skip


def test_instrucao_do_principal_nao_contem_o_regulamento():
    """G-4 / CA-23: nenhum trecho do regulamento na instrução do principal."""
    assert not re.search(r"Art\.\s*\d", INSTRUCAO_PRINCIPAL)
    assert "Capítulo" not in INSTRUCAO_PRINCIPAL
    for capitulo in carregar_regulamento():
        for artigo in capitulo.artigos:
            corpo = artigo.texto.split("**", 2)[-1].strip()
            assert corpo[:60] not in INSTRUCAO_PRINCIPAL


def test_todos_os_agentes_usam_gemini_com_novas_tentativas(app_adk, config):
    agentes = _agentes(app_adk.root_agent)
    assert {a.name for a in agentes} == {
        "aurora_principal",
        "especialista_reservas",
        "especialista_visitantes",
        "especialista_regulamento",
    }
    for agente in agentes:
        assert isinstance(agente.model, Gemini)
        assert agente.model.model in {config.modelo_principal, config.modelo_especialistas}
        opcoes = agente.model.retry_options
        assert opcoes is not None
        assert 503 in (opcoes.http_status_codes or [])
        assert set(CODIGOS_RETENTAVEIS) <= set(opcoes.http_status_codes or [])
