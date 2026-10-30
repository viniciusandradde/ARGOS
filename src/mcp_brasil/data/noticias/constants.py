"""Official RSS/Atom feeds verified to return real news items."""

from __future__ import annotations

from typing import NamedTuple


class Fonte(NamedTuple):
    nome: str
    url: str
    categoria: str


_AB = "https://agenciabrasil.ebc.com.br/rss"
_CAMARA = "https://www.camara.leg.br/noticias/rss"

FONTES: dict[str, Fonte] = {
    "agencia_brasil": Fonte(
        "Agência Brasil — últimas", f"{_AB}/ultimasnoticias/feed.xml", "geral"
    ),
    "agencia_brasil_politica": Fonte(
        "Agência Brasil — política", f"{_AB}/politica/feed.xml", "politica"
    ),
    "agencia_brasil_economia": Fonte(
        "Agência Brasil — economia", f"{_AB}/economia/feed.xml", "economia"
    ),
    "agencia_brasil_saude": Fonte("Agência Brasil — saúde", f"{_AB}/saude/feed.xml", "saude"),
    "agencia_brasil_justica": Fonte(
        "Agência Brasil — justiça", f"{_AB}/justica/feed.xml", "justica"
    ),
    "agencia_brasil_geral": Fonte("Agência Brasil — geral", f"{_AB}/geral/feed.xml", "geral"),
    "camara": Fonte("Agência Câmara — últimas", f"{_CAMARA}/ultimas-noticias", "legislativo"),
    "camara_saude": Fonte("Agência Câmara — saúde", f"{_CAMARA}/dinamico/SAUDE", "saude"),
    "camara_economia": Fonte(
        "Agência Câmara — economia", f"{_CAMARA}/dinamico/ECONOMIA", "economia"
    ),
    "senado": Fonte("Agência Senado", "https://www12.senado.leg.br/noticias/rss", "legislativo"),
    "planalto": Fonte(
        "Planalto",
        "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias/RSS",
        "governo",
    ),
    "agencia_gov": Fonte("Agência Gov", "https://agenciagov.ebc.com.br/noticias/RSS", "governo"),
    "banco_central": Fonte(
        "Banco Central",
        "https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/noticias",
        "economia",
    ),
    "ans": Fonte(
        "ANS — Agência Nacional de Saúde Suplementar",
        "https://www.gov.br/ans/pt-br/assuntos/noticias/RSS",
        "saude",
    ),
    "receita_federal": Fonte(
        "Receita Federal",
        "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/RSS",
        "economia",
    ),
}

CATEGORIAS = sorted({f.categoria for f in FONTES.values()})

DEFAULT_LIMITE = 10
MAX_LIMITE = 50
