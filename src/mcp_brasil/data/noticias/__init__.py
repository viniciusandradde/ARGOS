"""Feature Notícias — feeds RSS do Brasil e do mundo, com criticidade."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="noticias",
    description=(
        "Notícias do Brasil e do mundo via RSS (48 fontes): Agência Brasil, Câmara, Senado, "
        "Planalto, Banco Central, INMET, OMS, ECDC, ONU, BBC, Guardian, NYT, DW, RFI, "
        "Fed, BCE, ReliefWeb, USGS — com filtros e classificação de criticidade."
    ),
    version="0.2.0",
    requires_auth=False,
    tags=["noticias", "rss", "internacional", "saude", "clima", "economia", "monitoramento"],
)
