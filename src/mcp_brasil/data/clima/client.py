"""HTTP clients for NOAA CPC, Open-Meteo, INMET, USGS and NASA EONET (no keys needed)."""

from __future__ import annotations

import asyncio
import html
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get, http_get_text

from .constants import (
    CPC_ENSO_DISCUSSAO,
    CPC_ONI,
    CPC_RONI,
    CPC_SST_SEMANAL,
    ESTACAO_DISTANCIA_MAX_KM,
    ESTACAO_IDADE_MAX_H,
    GUIA_CLIMA,
    GUIA_CLIMA_ESTACOES,
    GUIA_CLIMA_RAIO_KM,
    INMET_AVISOS_RSS,
    INMET_ESTACAO_PROXIMA,
    INMET_PREVISAO,
    MODELOS_FAIXA,
    NASA_EONET,
    OPEN_METEO_AR,
    OPEN_METEO_GEOCODING,
    OPEN_METEO_PREVISAO,
    USGS_FEED,
    open_meteo,
)
from .schemas import (
    AvisoInmet,
    EventoNatural,
    LeituraEstacao,
    LeituraOni,
    LeituraSemanal,
    StatusEnso,
    Terremoto,
)

FUSO_MS = timezone(timedelta(hours=-4))  # Embrapa timestamps are local, without an offset
_TAG_RE = re.compile(r"<[^>]+>")


def _texto(html_text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", html_text)).split())


# --- ENSO (NOAA CPC) -------------------------------------------------------


def parse_oni(texto: str, ultimos: int = 12) -> list[LeituraOni]:
    """Parse CPC ONI/RONI ascii tables (``SEAS YR TOTAL ANOM`` or ``SEAS YR ANOM``)."""
    leituras: list[LeituraOni] = []
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) < 3 or not partes[1].isdigit():
            continue
        try:
            leituras.append(
                LeituraOni(trimestre=partes[0], ano=int(partes[1]), anomalia=float(partes[-1]))
            )
        except ValueError:
            continue
    return leituras[-ultimos:]


def parse_sst_semanal(texto: str, ultimos: int = 8) -> list[LeituraSemanal]:
    """Parse ``wksst9120.for`` (week, then SST/anomaly pairs for Niño 1+2, 3, 3.4, 4)."""
    leituras: list[LeituraSemanal] = []
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) != 9 or not re.fullmatch(r"\d{2}[A-Z]{3}\d{4}", partes[0]):
            continue
        valores = [float(v) for v in partes[1:]]
        leituras.append(
            LeituraSemanal(
                semana=partes[0],
                nino12=valores[1],
                nino3=valores[3],
                nino34=valores[5],
                nino4=valores[7],
            )
        )
    return leituras[-ultimos:]


def parse_discussao(html_text: str) -> tuple[str, str]:
    """Extract the alert status and synopsis from the CPC ENSO discussion page."""
    texto = _texto(html_text)
    alerta = re.search(r"ENSO Alert System Status:\s*(.+?)\s+Synopsis:", texto)
    sinopse = re.search(r"Synopsis:\s*(.+?)(?:\s+[A-Z][a-z]+ Niño strengthened|\.\s)", texto)
    return (
        alerta.group(1).strip() if alerta else "",
        (sinopse.group(1).strip() + ".") if sinopse else "",
    )


@ttl_cache(ttl=3600)
async def status_enso() -> StatusEnso:
    """Official ENSO status (cached 1h — CPC updates weekly/monthly)."""
    discussao = await http_get_text(CPC_ENSO_DISCUSSAO, timeout=30)
    oni = await http_get_text(CPC_ONI, timeout=30)
    roni = await http_get_text(CPC_RONI, timeout=30)
    semanal = await http_get_text(CPC_SST_SEMANAL, timeout=30)
    alerta, sinopse = parse_discussao(discussao)
    return StatusEnso(
        alerta=alerta,
        sinopse=sinopse,
        oni=parse_oni(oni),
        roni=parse_oni(roni),
        semanal=parse_sst_semanal(semanal),
    )


# --- Open-Meteo --------------------------------------------------------------


@ttl_cache(ttl=86400)
async def geocodificar(cidade: str, pais: str = "BR") -> list[dict[str, Any]]:
    params = {"name": cidade, "count": 5, "language": "pt", "countryCode": pais}
    url, params = open_meteo(OPEN_METEO_GEOCODING, params)
    data = await http_get(url, params=params)
    resultados = data.get("results", []) if isinstance(data, dict) else []
    return resultados if isinstance(resultados, list) else []


async def previsao(lat: float, lon: float, dias: int = 5) -> dict[str, Any]:
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,weather_code"
        ),
        "timezone": "auto",
        "forecast_days": max(1, min(dias, 16)),
    }
    url, params = open_meteo(OPEN_METEO_PREVISAO, params)
    data: dict[str, Any] = await http_get(url, params=params)
    return data


def parse_faixa(dados: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Lowest and highest daily maximum among the models, for days with two or more."""
    diario = dados.get("daily", {})
    faixa: dict[str, tuple[float, float]] = {}
    for i, dia in enumerate(diario.get("time", [])):
        valores = []
        for modelo in MODELOS_FAIXA:
            serie = diario.get(f"temperature_2m_max_{modelo}") or []
            if i < len(serie) and serie[i] is not None:
                valores.append(float(serie[i]))
        if len(valores) >= 2:
            faixa[dia] = (min(valores), max(valores))
    return faixa


async def faixa_modelos(lat: float, lon: float, dias: int = 5) -> dict[str, tuple[float, float]]:
    """Spread of the daily maximum across global models, to show forecast uncertainty."""
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max",
        "models": ",".join(MODELOS_FAIXA),
        "timezone": "auto",
        "forecast_days": max(1, min(dias, 16)),
    }
    url, params = open_meteo(OPEN_METEO_PREVISAO, params)
    data: dict[str, Any] = await http_get(url, params=params)
    return parse_faixa(data)


async def qualidade_ar(lat: float, lon: float) -> dict[str, Any]:
    url, params = open_meteo(
        OPEN_METEO_AR, {"latitude": lat, "longitude": lon, "current": "pm2_5,pm10,us_aqi"}
    )
    data: dict[str, Any] = await http_get(url, params=params)
    return data


# --- INMET ---------------------------------------------------------------------


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _numero(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def parse_estacao(
    payload: dict[str, Any],
    lat: float | None = None,
    lon: float | None = None,
    agora: datetime | None = None,
) -> LeituraEstacao | None:
    """Latest reading of an INMET automatic station, or None if it is unusable.

    The endpoint is undocumented, so anything stale, too far away or incomplete is
    rejected and the caller falls back to the forecast model. The reported distance is
    unreliable (71 km for the station inside Campo Grande), so coordinates take precedence.
    """
    estacao, dados = payload.get("estacao") or {}, payload.get("dados") or {}
    temperatura = _numero(dados.get("TEM_INS"))
    distancia = _numero(estacao.get("DISTANCIA_EM_KM"))
    lat_estacao, lon_estacao = _numero(estacao.get("LATITUDE")), _numero(estacao.get("LONGITUDE"))
    if None not in (lat, lon, lat_estacao, lon_estacao):
        distancia = round(distancia_km(lat, lon, lat_estacao, lon_estacao), 1)  # type: ignore[arg-type]
    if temperatura is None or distancia is None or distancia > ESTACAO_DISTANCIA_MAX_KM:
        return None
    try:
        quando = datetime.strptime(
            f"{dados.get('DT_MEDICAO')} {dados.get('HR_MEDICAO')}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if (agora or datetime.now(timezone.utc)) - quando > timedelta(hours=ESTACAO_IDADE_MAX_H):
        return None
    vento, rajada = _numero(dados.get("VEN_VEL")), _numero(dados.get("VEN_RAJ"))
    codigo = str(estacao.get("CODIGO") or dados.get("CD_ESTACAO") or "")
    nome = str(estacao.get("NOME") or dados.get("DC_NOME") or "")
    return LeituraEstacao(
        rotulo=f"INMET {codigo} {nome}",
        codigo=codigo,
        nome=nome,
        distancia_km=distancia,
        quando=quando.isoformat(),
        temperatura=temperatura,
        umidade=_numero(dados.get("UMD_INS")),
        vento_kmh=round(vento * 3.6, 1) if vento is not None else None,
        rajada_kmh=round(rajada * 3.6, 1) if rajada is not None else None,
        lat=lat_estacao,
        lon=lon_estacao,
    )


async def estacao_proxima(geocodigo: str, lat: float, lon: float) -> LeituraEstacao | None:
    """Reading of the INMET station nearest to an IBGE municipality."""
    data = await http_get(f"{INMET_ESTACAO_PROXIMA}/{geocodigo}")
    return parse_estacao(data, lat, lon) if isinstance(data, dict) else None


def parse_guia_clima(
    tempo_real: dict[str, Any],
    hoje: dict[str, Any],
    estacao: tuple[int, str, float, float],
    lat: float,
    lon: float,
    agora: datetime | None = None,
) -> LeituraEstacao | None:
    """Current reading of an Embrapa station, plus the measured extremes of the day."""
    codigo, nome, lat_estacao, lon_estacao = estacao
    temperatura = _numero(tempo_real.get("temp_c_avg"))
    if temperatura is None:
        return None
    try:
        quando = datetime.strptime(str(tempo_real.get("day")), "%d/%m/%Y %H:%M").replace(
            tzinfo=FUSO_MS
        )
    except ValueError:
        return None
    if (agora or datetime.now(timezone.utc)) - quando > timedelta(hours=ESTACAO_IDADE_MAX_H):
        return None
    vento = _numero(tempo_real.get("u2m_ms"))
    mesmo_dia = hoje.get("day") == quando.date().isoformat()
    return LeituraEstacao(
        rotulo=f"Embrapa Guia Clima · {nome}",
        codigo=str(codigo),
        nome=nome,
        distancia_km=round(distancia_km(lat, lon, lat_estacao, lon_estacao), 1),
        quando=quando.astimezone(timezone.utc).isoformat(),
        temperatura=temperatura,
        umidade=_numero(tempo_real.get("urc_pctg_avg")),
        vento_kmh=round(vento * 3.6, 1) if vento is not None else None,
        hoje_max=_numero(hoje.get("temp_c_max")) if mesmo_dia else None,
        hoje_min=_numero(hoje.get("temp_c_min")) if mesmo_dia else None,
        lat=lat_estacao,
        lon=lon_estacao,
    )


async def guia_clima_proximo(lat: float, lon: float) -> LeituraEstacao | None:
    """Reading of the nearest Embrapa station, when one covers the point."""
    estacao = min(GUIA_CLIMA_ESTACOES, key=lambda e: distancia_km(lat, lon, e[2], e[3]))
    if distancia_km(lat, lon, estacao[2], estacao[3]) > GUIA_CLIMA_RAIO_KM:
        return None
    params = {"cod_estacao": estacao[0]}
    resultados: tuple[Any, Any] = await asyncio.gather(
        http_get(f"{GUIA_CLIMA}/tempoReal", params=params),
        http_get(f"{GUIA_CLIMA}/leituraAtual", params=params),
        return_exceptions=True,
    )
    tempo_real, hoje = resultados
    if not isinstance(tempo_real, dict):
        return None
    return parse_guia_clima(tempo_real, hoje if isinstance(hoje, dict) else {}, estacao, lat, lon)


async def medicao_local(geocodigo: str, lat: float, lon: float) -> LeituraEstacao | None:
    """Best measured reading for a point: Embrapa (15 min), then the INMET station (hourly)."""
    try:
        leitura = await guia_clima_proximo(lat, lon)
    except Exception:
        leitura = None
    if leitura is None and geocodigo:
        leitura = await estacao_proxima(geocodigo, lat, lon)
    return leitura


def parse_previsao_inmet(
    payload: dict[str, Any], geocodigo: str
) -> dict[str, tuple[float, float]]:
    """Official daily forecast as {ISO date: (min, max)}; near days are split by period."""
    previsao_dias: dict[str, tuple[float, float]] = {}
    for dia, conteudo in (payload.get(geocodigo) or {}).items():
        if not isinstance(conteudo, dict):
            continue
        periodos = [p for p in conteudo.values() if isinstance(p, dict)] or [conteudo]
        minimas = [v for p in periodos if (v := _numero(p.get("temp_min"))) is not None]
        maximas = [v for p in periodos if (v := _numero(p.get("temp_max"))) is not None]
        try:
            data = datetime.strptime(dia, "%d/%m/%Y").date().isoformat()
        except ValueError:
            continue
        if minimas and maximas:
            previsao_dias[data] = (min(minimas), max(maximas))
    return previsao_dias


@ttl_cache(ttl=10800)
async def previsao_inmet(geocodigo: str) -> dict[str, tuple[float, float]]:
    """Official INMET forecast for a municipality (updated a few times a day)."""
    data = await http_get(f"{INMET_PREVISAO}/{geocodigo}")
    return parse_previsao_inmet(data, geocodigo) if isinstance(data, dict) else {}


def parse_avisos_inmet(xml_text: str) -> list[AvisoInmet]:
    root = ET.fromstring(xml_text.strip())
    avisos: list[AvisoInmet] = []
    for item in root.iter("item"):
        descricao_html = item.findtext("description") or ""
        campos = {
            _texto(k): _texto(v)
            for k, v in re.findall(r"<th[^>]*>(.*?)</th>\s*<td>(.*?)</td>", descricao_html, re.S)
        }
        avisos.append(
            AvisoInmet(
                evento=campos.get("Evento", ""),
                severidade=campos.get("Severidade", ""),
                inicio=campos.get("Início", "")[:16],
                fim=campos.get("Fim", "")[:16],
                descricao=campos.get("Descrição", ""),
                area=campos.get("Área", "").removeprefix("Aviso para as Áreas:").strip(),
                link=item.findtext("link") or "",
            )
        )
    return avisos


@ttl_cache(ttl=600)
async def avisos_inmet() -> list[AvisoInmet]:
    texto = await http_get_text(INMET_AVISOS_RSS, timeout=30)
    return parse_avisos_inmet(texto)


def aviso_vigente(aviso: AvisoInmet, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now()
    try:
        return datetime.fromisoformat(aviso.fim) >= agora
    except ValueError:
        return True


# --- USGS / NASA ---------------------------------------------------------------


async def terremotos(magnitude: str = "4.5", periodo: str = "day") -> list[Terremoto]:
    url = USGS_FEED.format(magnitude=magnitude, periodo=periodo)
    data = await http_get(url)
    saida: list[Terremoto] = []
    for f in data.get("features", []) if isinstance(data, dict) else []:
        p = f.get("properties", {})
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        saida.append(
            Terremoto(
                magnitude=float(p.get("mag") or 0),
                local=p.get("place") or "",
                quando_ms=int(p.get("time") or 0),
                link=p.get("url") or "",
                tsunami=bool(p.get("tsunami")),
                profundidade_km=coords[2] if len(coords) > 2 else None,
            )
        )
    saida.sort(key=lambda t: t.magnitude, reverse=True)
    return saida


async def eventos_naturais(dias: int = 15, limite: int = 100) -> list[EventoNatural]:
    params = {"status": "open", "days": dias, "limit": limite}
    data = await http_get(NASA_EONET, params=params)
    saida: list[EventoNatural] = []
    for e in data.get("events", []) if isinstance(data, dict) else []:
        geometria = e.get("geometry") or [{}]
        saida.append(
            EventoNatural(
                titulo=e.get("title", ""),
                categoria=", ".join(c.get("title", "") for c in e.get("categories", [])),
                data=(geometria[-1].get("date") or "")[:10],
                link=e.get("link", ""),
            )
        )
    return saida
