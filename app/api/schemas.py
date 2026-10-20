"""Modelos do contrato da API (PRD §9)."""

from typing import Any

from pydantic import BaseModel, Field


class CriarSessaoIn(BaseModel):
    apartamento: str = Field(min_length=1)


class CriarSessaoOut(BaseModel):
    session_id: str


class MensagemIn(BaseModel):
    texto: str


class ConfirmacaoIn(BaseModel):
    id: str
    confirmado: bool


class ConfirmacaoPendenteOut(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class RespostaOut(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[ConfirmacaoPendenteOut]


class ReservaOut(BaseModel):
    codigo: str
    area: str
    data: str


class VisitanteOut(BaseModel):
    nome: str
    data: str
