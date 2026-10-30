"""Feature LexML — legislação federal, estadual e municipal (Rede LexML Brasil)."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="lexml",
    description=(
        "LexML Brasil: busca unificada de leis, decretos, medidas provisórias, "
        "projetos de lei e jurisprudência de todas as esferas (federal, estadual, municipal)."
    ),
    version="0.1.0",
    api_base="https://www.lexml.gov.br/busca/SRU",
    requires_auth=False,
    tags=["lexml", "legislacao", "leis", "decretos", "normas", "monitoramento"],
)
