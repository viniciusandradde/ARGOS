"""RSS/Atom feeds verified to return real news items.

``escopo`` separates Brazilian sources from international ones and ``idioma``
lets clients filter by language.
"""

from __future__ import annotations

from typing import NamedTuple


class Fonte(NamedTuple):
    nome: str
    url: str
    categoria: str
    escopo: str = "brasil"
    idioma: str = "pt"


_AB = "https://agenciabrasil.ebc.com.br/rss"
_CAMARA = "https://www.camara.leg.br/noticias/rss"
_BBC = "https://feeds.bbci.co.uk/news"
_GUARDIAN = "https://www.theguardian.com"
_NYT = "https://rss.nytimes.com/services/xml/rss/nyt"
_ONU = "https://news.un.org/feed/subscribe"

FONTES: dict[str, Fonte] = {
    # --- Brasil: fontes oficiais -------------------------------------------
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
    "inmet_avisos": Fonte(
        "INMET — avisos meteorológicos", "https://apiprevmet3.inmet.gov.br/avisos/rss", "clima"
    ),
    # --- Brasil: imprensa ---------------------------------------------------
    "g1": Fonte("g1", "https://g1.globo.com/rss/g1/", "geral"),
    "cnn_brasil": Fonte("CNN Brasil", "https://www.cnnbrasil.com.br/feed/", "geral"),
    # --- Mundo: saúde e epidemias -------------------------------------------
    "oms": Fonte(
        "OMS — WHO News", "https://www.who.int/rss-feeds/news-english.xml", "saude", "mundo", "en"
    ),
    "ecdc": Fonte(
        "ECDC — Centro Europeu de Controle de Doenças",
        "https://www.ecdc.europa.eu/en/taxonomy/term/1307/feed",
        "epidemias",
        "mundo",
        "en",
    ),
    "onu_saude": Fonte(
        "ONU News — saúde",
        f"{_ONU}/en/news/topic/health/feed/rss.xml",
        "saude",
        "mundo",
        "en",
    ),
    "stat_news": Fonte("STAT News", "https://www.statnews.com/feed/", "saude", "mundo", "en"),
    "lancet": Fonte(
        "The Lancet",
        "https://www.thelancet.com/rssfeed/lancet_current.xml",
        "saude",
        "mundo",
        "en",
    ),
    "bbc_saude": Fonte("BBC — Health", f"{_BBC}/health/rss.xml", "saude", "mundo", "en"),
    "guardian_saude": Fonte(
        "The Guardian — Health", f"{_GUARDIAN}/society/health/rss", "saude", "mundo", "en"
    ),
    "nyt_saude": Fonte("New York Times — Health", f"{_NYT}/Health.xml", "saude", "mundo", "en"),
    # --- Mundo: economia e finanças -----------------------------------------
    "onu_economia": Fonte(
        "ONU News — economia",
        f"{_ONU}/en/news/topic/economic-development/feed/rss.xml",
        "economia",
        "mundo",
        "en",
    ),
    "federal_reserve": Fonte(
        "Federal Reserve (EUA)",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "economia",
        "mundo",
        "en",
    ),
    "bce": Fonte(
        "Banco Central Europeu",
        "https://www.ecb.europa.eu/rss/press.html",
        "economia",
        "mundo",
        "en",
    ),
    "marketwatch": Fonte(
        "MarketWatch",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "economia",
        "mundo",
        "en",
    ),
    "bbc_negocios": Fonte("BBC — Business", f"{_BBC}/business/rss.xml", "economia", "mundo", "en"),
    "guardian_negocios": Fonte(
        "The Guardian — Business", f"{_GUARDIAN}/business/rss", "economia", "mundo", "en"
    ),
    # --- Mundo: clima e desastres -------------------------------------------
    "bbc_ambiente": Fonte(
        "BBC — Science & Environment",
        f"{_BBC}/science_and_environment/rss.xml",
        "clima",
        "mundo",
        "en",
    ),
    "guardian_clima": Fonte(
        "The Guardian — Climate crisis",
        f"{_GUARDIAN}/environment/climate-crisis/rss",
        "clima",
        "mundo",
        "en",
    ),
    "nyt_clima": Fonte("New York Times — Climate", f"{_NYT}/Climate.xml", "clima", "mundo", "en"),
    "reliefweb": Fonte(
        "ReliefWeb (ONU) — crises humanitárias",
        "https://reliefweb.int/updates/rss.xml",
        "desastres",
        "mundo",
        "en",
    ),
    "usgs_terremotos": Fonte(
        "USGS — terremotos M4.5+ (24h)",
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.atom",
        "desastres",
        "mundo",
        "en",
    ),
    # --- Mundo: geral -------------------------------------------------------
    "onu": Fonte("ONU News", f"{_ONU}/en/news/all/rss.xml", "geral", "mundo", "en"),
    "onu_pt": Fonte("ONU News — português", f"{_ONU}/pt/news/all/rss.xml", "geral", "mundo"),
    "bbc_mundo": Fonte("BBC — World", f"{_BBC}/world/rss.xml", "geral", "mundo", "en"),
    "bbc_brasil": Fonte(
        "BBC News Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml", "geral", "mundo"
    ),
    "guardian_mundo": Fonte(
        "The Guardian — World", f"{_GUARDIAN}/world/rss", "geral", "mundo", "en"
    ),
    "nyt_mundo": Fonte("New York Times — World", f"{_NYT}/World.xml", "geral", "mundo", "en"),
    "aljazeera": Fonte(
        "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "geral", "mundo", "en"
    ),
    "dw": Fonte("Deutsche Welle", "https://rss.dw.com/xml/rss-en-all", "geral", "mundo", "en"),
    "dw_brasil": Fonte("DW Brasil", "https://rss.dw.com/xml/rss-br-all", "geral", "mundo"),
    "rfi_brasil": Fonte("RFI Brasil", "https://www.rfi.fr/br/rss", "geral", "mundo"),
    "france24": Fonte("France 24", "https://www.france24.com/en/rss", "geral", "mundo", "en"),
}

CATEGORIAS = sorted({f.categoria for f in FONTES.values()})
ESCOPOS = ("brasil", "mundo")
NIVEIS = ("normal", "alto", "critico")

DEFAULT_LIMITE = 10
MAX_LIMITE = 50
# Feeds are cached in memory to avoid hammering the publishers
CACHE_TTL_SEGUNDOS = 300
