"""Feature Alimentos — inflação dos alimentos da cesta (IPCA/IBGE) por cidade."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="alimentos",
    description=(
        "Alimentos: variação de preços dos principais itens da cesta (arroz, feijão, carnes, "
        "tomate, batata, leite, ovos, café, óleo, pão) pelo IPCA/IBGE — Brasil e 16 capitais "
        "(inclui Campo Grande/MS), no mês e em 12 meses."
    ),
    version="0.1.0",
    api_base="https://apisidra.ibge.gov.br",
    requires_auth=False,
    tags=["alimentos", "precos", "inflacao", "ipca", "cesta", "ibge"],
)
