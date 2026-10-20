-- Schema do condomínio (F-04). Idempotente: pode ser aplicado várias vezes.
-- Não usar os nomes de tabela do ADK: sessions, events, app_states, user_states,
-- adk_internal_metadata (FDD V-10).

CREATE TABLE IF NOT EXISTS apartamentos (
    numero  TEXT PRIMARY KEY,
    morador TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS areas (
    id   TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    taxa NUMERIC(10,2) NOT NULL
);

-- RN-5: começa em 10000 para nunca colidir com os códigos de 4 dígitos de dados/.
-- Nunca é reiniciada, nem pela restauração.
CREATE SEQUENCE IF NOT EXISTS seq_codigo_reserva START 10000;

CREATE TABLE IF NOT EXISTS reservas (
    codigo       TEXT PRIMARY KEY,
    apartamento  TEXT NOT NULL REFERENCES apartamentos(numero),
    area         TEXT NOT NULL REFERENCES areas(id),
    data         DATE NOT NULL,
    status       TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'cancelada')),
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelado_em TIMESTAMPTZ
);

-- G-5 / RN-1: no máximo uma reserva ativa por área e data, garantido no instante da gravação.
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_ativa_area_data
    ON reservas (area, data) WHERE status = 'ativa';

-- A-2: chave primária composta torna a autorização idempotente (retomada at-least-once).
CREATE TABLE IF NOT EXISTS visitantes (
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    nome        TEXT NOT NULL,
    data        DATE NOT NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (apartamento, nome, data)
);

-- A-1: vínculo imutável sessão → apartamento (G-2) e localização da sessão para o 404.
CREATE TABLE IF NOT EXISTS sessoes_apartamento (
    session_id  TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
