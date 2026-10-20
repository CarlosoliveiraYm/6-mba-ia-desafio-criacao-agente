"""F-15, F-16 / G-4: o regulamento é consultado por trecho, nunca carregado inteiro."""

import json

import pytest

from app.tools.regulamento import buscar_regulamento, carregar_regulamento

# Detalhes exclusivos de capítulos que não tratam da piscina (VIII, IX e X).
# Se aparecerem numa resposta sobre outro assunto, houve vazamento de capítulo.
MARCADORES_DE_OUTROS_CAPITULOS = {
    "VIII": "mostarda",
    "IX": "lilás",
    "X": "xadrez vermelha",
}


def _numeros_dos_artigos(capitulo: str) -> set[str]:
    cap = next(c for c in carregar_regulamento() if c.numero == capitulo)
    return {a.texto for a in cap.artigos}


def test_indexa_14_capitulos_e_96_artigos():
    capitulos = carregar_regulamento()
    assert [c.numero for c in capitulos] == [
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"
    ]  # fmt: skip
    assert capitulos[3].titulo == "Piscina"
    assert sum(len(c.artigos) for c in capitulos) == 96
    assert [a.numero for c in capitulos for a in c.artigos] == list(range(1, 97))


def test_piscina_aos_domingos_traz_so_o_capitulo_iv():
    r = buscar_regulamento("Até que horas a piscina funciona aos domingos?")
    assert r["capitulo"] == "IV"
    texto = "\n".join(r["trechos"])
    assert "20h" in texto
    assert "domingos" in texto
    assert set(r["trechos"]) <= _numeros_dos_artigos("IV")
    serializado = json.dumps(r, ensure_ascii=False)
    for marcador in MARCADORES_DE_OUTROS_CAPITULOS.values():
        assert marcador not in serializado
    assert "Capítulo" not in serializado  # nunca devolve cabeçalhos / outros capítulos


@pytest.mark.parametrize(
    ("consulta", "capitulo"),
    [
        ("Posso ter cachorro no apartamento?", "VIII"),
        ("Qual o horário permitido para mudança?", "IX"),
        ("Em que horário posso fazer obra com barulho?", "X"),
        ("Como funciona a coleta seletiva de lixo?", "XII"),
        ("Que horas a academia abre?", "V"),
        ("Qual o período de silêncio?", "III"),
        ("Posso usar fogos de artifício no salão de festas?", "VI"),
        ("Onde guardo minha bicicleta na garagem?", "XI"),
        ("Qual a multa por reincidência?", "XIII"),
        ("Como recebo encomendas na portaria?", "VII"),
    ],
)
def test_escolhe_o_capitulo_do_assunto(consulta, capitulo):
    r = buscar_regulamento(consulta)
    assert r["encontrado"] is True
    assert r["capitulo"] == capitulo
    assert set(r["trechos"]) <= _numeros_dos_artigos(capitulo)
    assert 1 <= len(r["trechos"]) <= 3


@pytest.mark.parametrize(
    "consulta", ["Qual a capital da França?", "receita de bolo de cenoura", "???"]
)
def test_assunto_fora_do_regulamento(consulta):
    r = buscar_regulamento(consulta)
    assert r["encontrado"] is False
    assert "trechos" not in r
