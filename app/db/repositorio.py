"""SQL de áreas, reservas e visitantes.

Toda função recebe a conexão (transação aberta por quem chama) e o apartamento
explicitamente. O apartamento sempre vem da sessão, nunca do modelo (G-2).
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

log = logging.getLogger("aurora.db")

VIOLACAO_UNICIDADE = "23505"


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: Decimal

    @property
    def gera_cobranca(self) -> bool:
        """RN-2: área com taxa maior que zero gera cobrança."""
        return self.taxa > 0


# --- Áreas -------------------------------------------------------------------


async def obter_area(conn: AsyncConnection, area_id: str) -> Area | None:
    linha = (
        await conn.execute(text("SELECT id, nome, taxa FROM areas WHERE id = :id"), {"id": area_id})
    ).first()
    return Area(linha.id, linha.nome, linha.taxa) if linha else None


async def listar_areas(conn: AsyncConnection) -> list[Area]:
    linhas = await conn.execute(text("SELECT id, nome, taxa FROM areas ORDER BY id"))
    return [Area(linha.id, linha.nome, linha.taxa) for linha in linhas]


# --- Reservas ----------------------------------------------------------------


async def data_ocupada(conn: AsyncConnection, area_id: str, data: date) -> bool:
    """F-07: há reserva ativa da área na data? Não revela de quem é (G-2)."""
    resultado = await conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM reservas "
            "WHERE area = :area AND data = :data AND status = 'ativa')"
        ),
        {"area": area_id, "data": data},
    )
    return bool(resultado.scalar_one())


async def inserir_reserva(
    conn: AsyncConnection, apartamento: str, area_id: str, data: date
) -> str | None:
    """F-08/F-09: grava a reserva e devolve o código, ou None se a data já está ocupada.

    A exclusividade (RN-1, G-5) é garantida pelo índice único parcial
    `ux_reserva_ativa_area_data` no instante do INSERT, não por uma consulta anterior.
    O código vem da sequence dentro do próprio INSERT (RN-5).
    """
    try:
        resultado = await conn.execute(
            text(
                "INSERT INTO reservas (codigo, apartamento, area, data, status) "
                "VALUES ('RSV-' || nextval('seq_codigo_reserva'), :apto, :area, :data, 'ativa') "
                "ON CONFLICT DO NOTHING "
                "RETURNING codigo"
            ),
            {"apto": apartamento, "area": area_id, "data": data},
        )
    except IntegrityError as erro:
        # Defesa adicional: o ON CONFLICT já deveria ter absorvido a disputa.
        if getattr(erro.orig, "sqlstate", None) == VIOLACAO_UNICIDADE:
            log.warning("violação de unicidade absorvida ao reservar %s em %s", area_id, data)
            return None
        raise
    return resultado.scalar_one_or_none()


async def cancelar_reserva(
    conn: AsyncConnection, apartamento: str, area_id: str, data: date
) -> str | None:
    """F-11: cancela a reserva ativa do próprio apartamento (RN-4) e devolve o código."""
    resultado = await conn.execute(
        text(
            "UPDATE reservas SET status = 'cancelada', cancelado_em = now() "
            "WHERE apartamento = :apto AND area = :area AND data = :data AND status = 'ativa' "
            "RETURNING codigo"
        ),
        {"apto": apartamento, "area": area_id, "data": data},
    )
    return resultado.scalar_one_or_none()


async def listar_reservas(conn: AsyncConnection, apartamento: str) -> list[dict]:
    """F-12: reservas ativas do apartamento, por data."""
    linhas = await conn.execute(
        text(
            "SELECT codigo, area, data FROM reservas "
            "WHERE apartamento = :apto AND status = 'ativa' ORDER BY data, area"
        ),
        {"apto": apartamento},
    )
    return [
        {"codigo": linha.codigo, "area": linha.area, "data": linha.data.isoformat()}
        for linha in linhas
    ]


# --- Apartamentos e sessões ---------------------------------------------------


async def apartamento_existe(conn: AsyncConnection, numero: str) -> bool:
    resultado = await conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM apartamentos WHERE numero = :n)"), {"n": numero}
    )
    return bool(resultado.scalar_one())


async def vincular_sessao(conn: AsyncConnection, session_id: str, apartamento: str) -> None:
    """A-1 / G-2: vínculo imutável sessão → apartamento, gravado só na criação."""
    await conn.execute(
        text("INSERT INTO sessoes_apartamento (session_id, apartamento) VALUES (:sid, :apto)"),
        {"sid": session_id, "apto": apartamento},
    )


async def apartamento_da_sessao(conn: AsyncConnection, session_id: str) -> str | None:
    resultado = await conn.execute(
        text("SELECT apartamento FROM sessoes_apartamento WHERE session_id = :sid"),
        {"sid": session_id},
    )
    return resultado.scalar_one_or_none()


# --- Visitantes --------------------------------------------------------------


async def inserir_visitante(conn: AsyncConnection, apartamento: str, nome: str, data: date) -> bool:
    """F-13: autoriza o visitante. Idempotente pela PK (apartamento, nome, data).

    Devolve True se gravou agora e False se a autorização já existia.
    """
    resultado = await conn.execute(
        text(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (:apto, :nome, :data) "
            "ON CONFLICT (apartamento, nome, data) DO NOTHING "
            "RETURNING nome"
        ),
        {"apto": apartamento, "nome": nome, "data": data},
    )
    return resultado.scalar_one_or_none() is not None


async def listar_visitantes(conn: AsyncConnection, apartamento: str) -> list[dict]:
    """F-14: visitantes autorizados do apartamento, por data."""
    linhas = await conn.execute(
        text("SELECT nome, data FROM visitantes WHERE apartamento = :apto ORDER BY data, nome"),
        {"apto": apartamento},
    )
    return [{"nome": linha.nome, "data": linha.data.isoformat()} for linha in linhas]
