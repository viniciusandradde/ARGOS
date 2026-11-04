"""Endpoints (all free, no API key) for the Clima feature."""

# NOAA Climate Prediction Center — official ENSO alert system
CPC_ENSO_DISCUSSAO = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
)
CPC_ONI = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
CPC_RONI = "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt"
CPC_SST_SEMANAL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"

OPEN_METEO_PREVISAO = "https://api.open-meteo.com/v1/forecast"
INMET_ESTACAO_PROXIMA = "https://apiprevmet3.inmet.gov.br/estacao/proxima"
INMET_PREVISAO = "https://apiprevmet3.inmet.gov.br/previsao"
GUIA_CLIMA = "https://www.cpao.embrapa.br/gc/api/v1/guiaclima"
GUIA_CLIMA_RAIO_KM = 25
# Embrapa Agropecuária Oeste stations: code, name, latitude, longitude
GUIA_CLIMA_ESTACOES = (
    (1, "Dourados Embrapa", -22.2753, -54.8183),
    (5, "Dourados UFGD", -22.2333, -54.9861),
    (3, "Rio Brilhante", -21.8461, -54.5383),
    (4, "Ivinhema", -22.3889, -53.8869),
    (6, "Naviraí", -23.0258, -54.1894),
)
ESTACAO_DISTANCIA_MAX_KM = 60  # beyond this a reading no longer represents the city
ESTACAO_IDADE_MAX_H = 3
MODELOS_FAIXA = ("ecmwf_ifs025", "icon_global", "gfs_seamless")
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


def open_meteo(url: str, params: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Route Open-Meteo calls to the commercial endpoint when OPEN_METEO_API_KEY is set."""
    from mcp_brasil import settings

    if not settings.OPEN_METEO_API_KEY:
        return url, params
    url = (
        url.replace("https://api.", "https://customer-api.")
        .replace("https://geocoding-api.", "https://customer-geocoding-api.")
        .replace("https://air-quality-api.", "https://customer-air-quality-api.")
    )
    return url, {**params, "apikey": settings.OPEN_METEO_API_KEY}
