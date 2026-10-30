"""Feature Notícias — feeds RSS oficiais do governo e do Legislativo."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="noticias",
    description=(
        "Notícias oficiais via RSS: Agência Brasil (política, economia, saúde, justiça), "
        "Agência Câmara, Agência Senado, Planalto, Agência Gov, Banco Central e ANS."
    ),
    version="0.1.0",
    requires_auth=False,
    tags=["noticias", "rss", "agencia-brasil", "camara", "senado", "planalto", "monitoramento"],
)
