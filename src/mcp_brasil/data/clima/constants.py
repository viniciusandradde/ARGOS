"""Endpoints (all free, no API key) for the Clima feature."""

# NOAA Climate Prediction Center — official ENSO alert system
CPC_ENSO_DISCUSSAO = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
)
CPC_ONI = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
CPC_RONI = "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt"
CPC_SST_SEMANAL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"

OPEN_METEO_PREVISAO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_AR = "https://air-quality-api.open-meteo.com/v1/air-quality"

INMET_AVISOS_RSS = "https://apiprevmet3.inmet.gov.br/avisos/rss"

USGS_FEED = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{magnitude}_{periodo}.geojson"
)
NASA_EONET = "https://eonet.gsfc.nasa.gov/api/v3/events"

# WMO weather interpretation codes (Open-Meteo `weather_code`)
CODIGOS_TEMPO = {
    0: "céu limpo",
    1: "predomínio de sol",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina com geada",
    51: "garoa fraca",
    53: "garoa",
    55: "garoa forte",
    61: "chuva fraca",
    63: "chuva",
    65: "chuva forte",
    66: "chuva congelante",
    67: "chuva congelante forte",
    71: "neve fraca",
    73: "neve",
    75: "neve forte",
    80: "pancadas de chuva",
    81: "pancadas de chuva fortes",
    82: "pancadas de chuva violentas",
    95: "trovoadas",
    96: "trovoadas com granizo",
    99: "trovoadas com granizo forte",
}

# Typical ENSO impacts in Brazil (CPTEC/INPE and INMET climatology)
IMPACTOS_EL_NINO_BR = (
    "Impactos típicos no Brasil: chuvas acima da média e risco de enchentes no Sul; "
    "seca e maior risco de incêndios no Norte e no Nordeste; temperaturas acima da média "
    "no Sudeste e no Centro-Oeste (inclui MS), com perdas agrícolas possíveis."
)
IMPACTOS_LA_NINA_BR = (
    "Impactos típicos no Brasil: estiagem no Sul (incluindo sul de MS) e chuvas acima da média "
    "no Norte e no Nordeste."
)
