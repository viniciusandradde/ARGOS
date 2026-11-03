"""Feature Vigilância — biovigilância: arboviroses por município e surtos no mundo."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="vigilancia",
    description=(
        "Biovigilância: painel de dengue, chikungunya e zika por município (InfoDengue/Fiocruz) "
        "e radar de surtos, epidemias e pandemias no mundo (OMS, ECDC, ONU e imprensa)."
    ),
    version="0.1.0",
    requires_auth=False,
    tags=["vigilancia", "epidemias", "dengue", "zika", "chikungunya", "surtos", "pandemia"],
)
