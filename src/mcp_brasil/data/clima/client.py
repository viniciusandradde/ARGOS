"""HTTP clients for NOAA CPC, Open-Meteo, INMET, USGS and NASA EONET (no keys needed)."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get, http_get_text

from .constants import (
    CPC_ENSO_DISCUSSAO,
    CPC_ONI,
    CPC_RONI,
    CPC_SST_SEMANAL,
    INMET_AVISOS_RSS,
    NASA_EONET,
    OPEN_METEO_AR,
    OPEN_METEO_GEOCODING,
    OPEN_METEO_PREVISAO,
    USGS_FEED,
)
from .schemas import (
    AvisoInmet,
    EventoNatural,
    LeituraOni,
    LeituraSemanal,
    StatusEnso,
    Terremoto,
)

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
    data = await http_get(OPEN_METEO_GEOCODING, params=params)
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
    data: dict[str, Any] = await http_get(OPEN_METEO_PREVISAO, params=params)
    return data


async def qualidade_ar(lat: float, lon: float) -> dict[str, Any]:
    params = {"latitude": lat, "longitude": lon, "current": "pm2_5,pm10,us_aqi"}
    data: dict[str, Any] = await http_get(OPEN_METEO_AR, params=params)
    return data


# --- INMET ---------------------------------------------------------------------


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
