"""Feature Clima — El Niño (NOAA), previsão, avisos INMET, terremotos e eventos naturais."""

from mcp_brasil._shared.feature import FeatureMeta

FEATURE_META = FeatureMeta(
    name="clima",
    description=(
        "Clima e desastres: El Niño/La Niña (NOAA CPC — alerta oficial, ONI, Niño 3.4 semanal), "
        "previsão do tempo e qualidade do ar (Open-Meteo), avisos meteorológicos do INMET, "
        "terremotos (USGS) e eventos naturais ativos (NASA EONET)."
    ),
    version="0.1.0",
    requires_auth=False,
    tags=["clima", "el-nino", "enso", "noaa", "inmet", "previsao", "terremotos", "desastres"],
)
