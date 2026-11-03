"""Feature Mundo — câmbio (BCE via Frankfurter) e indicadores do Banco Mundial."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="mundo",
    description=(
        "Economia mundial: cotações de moedas e histórico (taxas de referência do Banco Central "
        "Europeu via Frankfurter) e indicadores do Banco Mundial por país (PIB, inflação, "
        "desemprego, gasto em saúde, expectativa de vida)."
    ),
    version="0.1.0",
    requires_auth=False,
    tags=["mundo", "cambio", "moedas", "banco-mundial", "economia", "internacional"],
)
