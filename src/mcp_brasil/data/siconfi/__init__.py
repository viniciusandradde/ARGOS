"""Feature SICONFI — dados fiscais de estados e municípios (Tesouro Nacional)."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="siconfi",
    description=(
        "Tesouro Nacional (SICONFI): relatórios fiscais de União, estados e municípios — "
        "RREO (execução orçamentária), RGF (gestão fiscal/LRF), DCA (contas anuais) "
        "e extrato de entregas."
    ),
    version="0.1.0",
    api_base="https://apidatalake.tesouro.gov.br/ords/siconfi/tt",
    requires_auth=False,
    tags=["siconfi", "tesouro", "fiscal", "lrf", "rreo", "rgf", "dca", "impostos"],
)
