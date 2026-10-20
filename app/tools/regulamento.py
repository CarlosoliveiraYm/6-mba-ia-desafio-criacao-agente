"""Consulta ao regulamento interno (F-15, F-16).

G-4: o regulamento nunca é carregado inteiro. `buscar_regulamento` devolve só
artigos de UM capítulo, escolhido por busca determinística (sem LLM): título do
capítulo, mapa de sinônimos e termos presentes no texto.
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import RAIZ_PROJETO

ARQUIVO_REGULAMENTO = RAIZ_PROJETO / "dados" / "regulamento.md"

PESO_TITULO = 5
PESO_SINONIMO = 3
PESO_TEXTO = 1
PONTUACAO_MINIMA = 2  # abaixo disso, consideramos que o regulamento não trata do assunto
MAX_ARTIGOS = 3

_CAPITULO = re.compile(r"^## Capítulo ([IVXLC]+): (.+)$", re.MULTILINE)
_INICIO_ARTIGO = re.compile(r"(?=^\*\*Art\. \d+)", re.MULTILINE)
_NUMERO_ARTIGO = re.compile(r"^\*\*Art\. (\d+)")

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos",
    "e", "ou", "em", "no", "na", "nos", "nas", "ao", "aos", "pelo", "pela", "para", "pra",
    "por", "com", "sem", "que", "qual", "quais", "quando", "onde", "como", "quanto",
    "ate", "se", "eu", "meu", "minha", "meus", "minhas", "voce", "posso", "pode", "podem",
    "ser", "sao", "ha", "tem", "ter", "quero", "sobre", "regra", "regras",
    "regulamento", "condominio", "existe", "algum", "alguma", "isso", "esse", "essa",
    "me", "mim", "lhe", "nao", "sim", "mais", "muito", "ja", "permitido", "proibido",
}  # fmt: skip

# Assunto → capítulo. Os termos passam pela mesma normalização da consulta.
SINONIMOS: dict[str, tuple[str, ...]] = {
    "I": ("convencao", "sindico", "subsindico", "administradora", "locacao", "aluguel",
          "alugar", "temporada", "airbnb", "comercial", "escritorio", "remoto"),
    "II": ("direito", "dever", "cota", "condominial", "boleto", "fachada", "varal",
           "roupa", "fumar", "cigarro", "elevador", "sacada", "janela", "inadimplente"),
    "III": ("silencio", "barulho", "barulhento", "ruido", "som", "musica", "instrumento",
            "volume", "vizinho", "sossego", "grito", "skate", "patinete"),
    "IV": ("piscina", "nadar", "natacao", "deck", "boia", "dermatologico",
           "espreguicadeira", "mergulho"),
    "V": ("academia", "musculacao", "ginastica", "treino", "personal", "esteira",
          "brinquedoteca", "playground", "parquinho", "brinquedo"),
    "VI": ("salao", "festa", "churrasqueira", "churrasco", "quadra", "futebol", "esporte",
           "evento", "aniversario", "decoracao", "balao", "confraternizacao"),
    "VII": ("portaria", "porteiro", "visitante", "visita", "entrega", "encomenda",
            "pacote", "correio", "tag", "cartao", "controle", "camera", "seguranca",
            "emergencia", "incendio", "portao", "extintor"),
    "VIII": ("animal", "animais", "cachorro", "cao", "caes", "gato", "pet", "coleira",
             "focinheira", "latido", "passear", "tutor"),
    "IX": ("mudanca", "mudar", "carreto", "caminhao", "icamento", "movel"),
    "X": ("obra", "reforma", "pedreiro", "entulho", "furadeira", "engenheiro",
          "arquiteto", "argamassa"),
    "XI": ("garagem", "vaga", "carro", "veiculo", "moto", "motocicleta", "bicicleta",
           "bike", "estacionar", "estacionamento", "carregador", "bicicletario"),
    "XII": ("lixo", "reciclagem", "reciclavel", "coleta", "residuo", "oleo", "pilha",
            "bateria", "descarte", "descartar", "seletiva", "lixeira"),
    "XIII": ("multa", "penalidade", "infracao", "advertencia", "punicao", "recurso",
             "reincidencia"),
    "XIV": ("alteracao", "alterar", "vigor", "revogar", "vigencia"),
}  # fmt: skip


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _radical(palavra: str) -> str:
    """Radical simples: remove o plural em -s de palavras longas."""
    return palavra[:-1] if len(palavra) > 4 and palavra.endswith("s") else palavra


def _termos(texto: str) -> set[str]:
    palavras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return {_radical(p) for p in palavras if p not in STOPWORDS and len(p) > 1}


def _casa(termo: str, vocabulario: set[str]) -> bool:
    """Termo presente no vocabulário (exato ou como prefixo de palavra longa)."""
    if termo in vocabulario:
        return True
    return len(termo) >= 5 and any(v.startswith(termo) for v in vocabulario)


@dataclass(frozen=True)
class Artigo:
    numero: int
    texto: str
    termos: frozenset[str]


@dataclass(frozen=True)
class Capitulo:
    numero: str
    titulo: str
    artigos: tuple[Artigo, ...]
    termos_titulo: frozenset[str]
    termos_texto: frozenset[str]
    sinonimos: frozenset[str]


@lru_cache
def carregar_regulamento(caminho: Path = ARQUIVO_REGULAMENTO) -> tuple[Capitulo, ...]:
    """F-15: indexa o regulamento por capítulo (`## Capítulo`) e artigo (`**Art. N`)."""
    conteudo = caminho.read_text(encoding="utf-8")
    cabecalhos = list(_CAPITULO.finditer(conteudo))
    capitulos = []
    for i, cab in enumerate(cabecalhos):
        fim = cabecalhos[i + 1].start() if i + 1 < len(cabecalhos) else len(conteudo)
        corpo = conteudo[cab.end() : fim]
        artigos = []
        for bloco in _INICIO_ARTIGO.split(corpo):
            bloco = bloco.strip()
            numero = _NUMERO_ARTIGO.match(bloco)
            if numero:
                artigos.append(Artigo(int(numero.group(1)), bloco, frozenset(_termos(bloco))))
        numero_cap, titulo = cab.group(1), cab.group(2).strip()
        capitulos.append(
            Capitulo(
                numero=numero_cap,
                titulo=titulo,
                artigos=tuple(artigos),
                termos_titulo=frozenset(_termos(titulo)),
                termos_texto=frozenset().union(*(a.termos for a in artigos)),
                sinonimos=frozenset(_radical(s) for s in SINONIMOS.get(numero_cap, ())),
            )
        )
    return tuple(capitulos)


def _pontuar_capitulo(capitulo: Capitulo, termos: set[str]) -> int:
    pontos = 0
    for termo in termos:
        if _casa(termo, set(capitulo.termos_titulo)):
            pontos += PESO_TITULO
        if termo in capitulo.sinonimos:
            pontos += PESO_SINONIMO
        if _casa(termo, set(capitulo.termos_texto)):
            pontos += PESO_TEXTO
    return pontos


def _selecionar_artigos(capitulo: Capitulo, termos: set[str]) -> list[Artigo]:
    pontuados = [(sum(_casa(t, set(a.termos)) for t in termos), a) for a in capitulo.artigos]
    melhor = max((p for p, _ in pontuados), default=0)
    if melhor == 0:
        return list(capitulo.artigos[:2])
    escolhidos = [a for p, a in pontuados if p > 0 and p >= melhor - 1]
    escolhidos.sort(key=lambda a: -sum(_casa(t, set(a.termos)) for t in termos))
    return sorted(escolhidos[:MAX_ARTIGOS], key=lambda a: a.numero)


def buscar_regulamento(consulta: str) -> dict:
    """Busca no regulamento interno do condomínio o trecho que responde à dúvida do morador.

    Devolve somente artigos do capítulo mais relevante para a dúvida.

    Args:
        consulta: a dúvida do morador, em linguagem natural (ex.: "horário da piscina no domingo")
    """
    termos = _termos(consulta)
    if not termos:
        return {"encontrado": False, "mensagem": "Descreva a dúvida sobre o regulamento."}
    pontuados = [(_pontuar_capitulo(c, termos), c) for c in carregar_regulamento()]
    pontos, capitulo = max(pontuados, key=lambda item: item[0])
    if pontos < PONTUACAO_MINIMA:
        return {"encontrado": False, "mensagem": "O regulamento não trata desse assunto."}
    return {
        "encontrado": True,
        "capitulo": capitulo.numero,
        "titulo": capitulo.titulo,
        "trechos": [a.texto for a in _selecionar_artigos(capitulo, termos)],
    }
