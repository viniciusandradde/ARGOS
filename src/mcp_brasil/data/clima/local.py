"""Risco climático local (município + bairro ou ponto exato).

Combina as fontes mais confiáveis e precisas disponíveis sem custo:

- **Avisos oficiais do INMET** (``/avisos/ativos``): cada aviso traz o polígono exato
  da área afetada (GeoJSON) e os códigos IBGE dos municípios. O ponto do bairro é
  testado contra o polígono, o que torna esta a camada mais precisa do painel.
- **Observação real** mais próxima: METAR de aeroportos (NOAA Aviation Weather Center).
- **Previsão hora a hora** de três modelos globais via Open-Meteo: ECMWF IFS (~9 km),
  DWD ICON (~13 km) e NOAA GFS (~13-25 km). O consenso e a divergência entre eles
  mostram a incerteza.
- **Focos de queimada** por satélite (INPE), num raio em torno do ponto.
- **Localização do bairro**: OpenStreetMap (Nominatim, Photon e Overpass).

Os limiares de risco seguem os critérios dos avisos do INMET (chuva, vento, baixa
umidade) e as faixas do índice de calor da NOAA.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get, http_get_text
from mcp_brasil.data.noticias.filtros import normalizar

from .client import distancia_km, medicao_local
from .constants import open_meteo

UA_OSM = {
    "User-Agent": "ARGOS-monitoramento/1.0 (+https://github.com/viniciusandradde/mcp-brasil)"
}

INMET_ATIVOS = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
AWC_METAR = "https://aviationweather.gov/api/data/metar"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
MET_NORWAY = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
PHOTON = "https://photon.komoot.io/api/"
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
INPE_FOCOS_DIA = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/"
    "focos_diario_br_{data}.csv"
)

MODELOS = {
    "ecmwf_ifs025": "ECMWF IFS",
    "icon_global": "DWD ICON",
    "gfs_seamless": "NOAA GFS",
}

UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}  # fmt: skip

NIVEIS = ("Normal", "Perigo Potencial", "Perigo", "Grande Perigo")


class Local(BaseModel):
    lat: float
    lon: float
    nome: str
    municipio: str = ""
    uf: str = ""
    geocodigo: str = ""
    fonte: str = ""
    precisao: str = ""  # ponto | bairro | rua | municipio


class AvisoLocal(BaseModel):
    evento: str
    severidade: str
    cor: str = ""
    inicio: str = ""
    fim: str = ""
    riscos: str = ""
    instrucoes: str = ""
    dentro_do_poligono: bool = False
    poligono: dict[str, Any] | None = None


class Observacao(BaseModel):
    estacao: str
    nome: str
    distancia_km: float
    quando: str
    temperatura: float | None = None
    ponto_orvalho: float | None = None
    vento_kmh: float | None = None
    rajada_kmh: float | None = None
    fenomeno: str = ""
    bruto: str = ""
    lat: float = 0.0
    lon: float = 0.0


class Risco(BaseModel):
    tipo: str
    nivel: int  # 0..3
    rotulo: str
    valor: str
    quando: str = ""
    criterio: str = ""


# --- Geometria -------------------------------------------------------------------


def _no_anel(lon: float, lat: float, anel: list[list[float]]) -> bool:
    dentro = False
    j = len(anel) - 1
    for i in range(len(anel)):
        xi, yi = anel[i][0], anel[i][1]
        xj, yj = anel[j][0], anel[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


def ponto_no_poligono(lat: float, lon: float, geo: dict[str, Any]) -> bool:
    """Ray casting for GeoJSON Polygon/MultiPolygon (holes respected)."""
    tipo = geo.get("type")
    poligonos = (
        [geo.get("coordinates", [])] if tipo == "Polygon" else geo.get("coordinates", [])
        if tipo == "MultiPolygon" else []
    )  # fmt: skip
    for poli in poligonos:
        if (
            poli
            and _no_anel(lon, lat, poli[0])
            and not any(_no_anel(lon, lat, buraco) for buraco in poli[1:])
        ):
            return True
    return False


# --- Localização (município + bairro) ---------------------------------------------

_nominatim_lock = asyncio.Lock()
_nominatim_ultimo = 0.0


async def _nominatim(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Nominatim usage policy: max 1 request/second and an identifying User-Agent."""
    global _nominatim_ultimo
    async with _nominatim_lock:
        espera = 1.1 - (time.monotonic() - _nominatim_ultimo)
        if espera > 0:
            await asyncio.sleep(espera)
        try:
            data = await http_get(
                NOMINATIM,
                params={"format": "jsonv2", "addressdetails": 1, "countrycodes": "br", **params},
                headers=UA_OSM,
                max_retries=1,
            )
        finally:
            _nominatim_ultimo = time.monotonic()
    return data if isinstance(data, list) else []


def _mesma_cidade(endereco: dict[str, Any], cidade: str) -> bool:
    alvo = normalizar(cidade)
    return any(
        normalizar(str(endereco.get(k, ""))) == alvo
        for k in ("city", "town", "municipality", "village", "city_district")
    )


def geocodigo_ibge(cidade: str, uf: str) -> str:
    from mcp_brasil.data.saude.client import buscar_municipio_geocodigo

    achados = buscar_municipio_geocodigo(cidade, uf or None)
    return str(achados[0].geocodigo) if achados else ""


def ponto(lat: float, lon: float, cidade: str = "", uf: str = "") -> Local:
    """An exact point chosen on the map or by the device GPS."""
    return Local(
        lat=lat,
        lon=lon,
        nome=f"Ponto {lat:.5f}, {lon:.5f}" + (f" — {cidade}/{uf.upper()}" if cidade else ""),
        municipio=cidade,
        uf=uf.upper(),
        geocodigo=geocodigo_ibge(cidade, uf) if cidade else "",
        fonte="coordenada informada",
        precisao="ponto",
    )


_CACHE_LOCAL: dict[tuple[str, str, str], tuple[float, Local]] = {}
_TTL_LOCAL = 7 * 86400


async def localizar(cidade: str, uf: str, bairro: str = "") -> Local | None:
    """Coordinates for a neighbourhood (or the municipality when no bairro is given).

    Successful lookups are cached for 7 days. A municipality fallback for a requested
    bairro is *not* cached, so a transient geocoder failure doesn't stick for a week.
    """
    chave = (normalizar(cidade), uf.upper(), normalizar(bairro))
    guardado = _CACHE_LOCAL.get(chave)
    if guardado and time.monotonic() - guardado[0] < _TTL_LOCAL:
        return guardado[1].model_copy()
    local = await _localizar(cidade, uf, bairro)
    if local is None:
        return None
    local.geocodigo = geocodigo_ibge(cidade, uf)
    if not (bairro and local.precisao == "municipio"):
        _CACHE_LOCAL[chave] = (time.monotonic(), local)
    return local.model_copy()


async def _localizar(cidade: str, uf: str, bairro: str) -> Local | None:
    uf = uf.upper()
    estado = UF_NOMES.get(uf, uf)
    if bairro:
        for r in await _nominatim({"q": f"{bairro}, {cidade}, {estado}", "limit": 5}):
            if _mesma_cidade(r.get("address", {}), cidade):
                tipo = r.get("addresstype", "")
                return Local(
                    lat=float(r["lat"]),
                    lon=float(r["lon"]),
                    nome=f"{bairro}, {cidade}/{uf}",
                    municipio=cidade,
                    uf=uf,
                    fonte="OpenStreetMap (Nominatim)",
                    precisao="bairro"
                    if tipo in ("suburb", "neighbourhood", "quarter", "city_block")
                    else "rua",
                )
        # Photon indexes the "district" of every POI/street: average those inside the bairro
        try:
            data = await http_get(
                PHOTON,
                params={"q": f"{bairro} {cidade}", "limit": 30},
                headers=UA_OSM,
                max_retries=1,
            )
        except Exception:
            data = {}
        pontos = []
        for f in data.get("features", []) if isinstance(data, dict) else []:
            p = f.get("properties", {})
            if normalizar(p.get("city", "")) == normalizar(cidade) and normalizar(bairro) in (
                normalizar(p.get("district", "")) + " " + normalizar(p.get("name", ""))
            ):
                lon, lat = f["geometry"]["coordinates"][:2]
                pontos.append((lat, lon))
        if pontos:
            return Local(
                lat=sum(p[0] for p in pontos) / len(pontos),
                lon=sum(p[1] for p in pontos) / len(pontos),
                nome=f"{bairro}, {cidade}/{uf}",
                municipio=cidade,
                uf=uf,
                fonte=f"OpenStreetMap (Photon, {len(pontos)} referências)",
                precisao="bairro",
            )
    url, params = open_meteo(
        OPEN_METEO_GEO, {"name": cidade, "count": 10, "language": "pt", "countryCode": "BR"}
    )
    data = await http_get(url, params=params)
    for r in data.get("results", []) if isinstance(data, dict) else []:
        if r.get("admin1") == estado or not uf:
            return Local(
                lat=r["latitude"],
                lon=r["longitude"],
                nome=f"{cidade}/{uf}" + (f" (bairro '{bairro}' não encontrado)" if bairro else ""),
                municipio=cidade,
                uf=uf,
                fonte="Open-Meteo Geocoding (GeoNames)",
                precisao="municipio",
            )
    return None


@ttl_cache(ttl=7 * 86400, maxsize=512)
async def listar_bairros(cidade: str, uf: str) -> list[dict[str, Any]]:
    """Neighbourhoods mapped in OpenStreetMap for a municipality (Overpass API)."""
    consulta = (
        '[out:json][timeout:25];area["boundary"="administrative"]["admin_level"="8"]'
        f'["name"="{cidade.replace(chr(34), "")}"]->.a;'
        'nwr["place"~"^(suburb|neighbourhood|quarter)$"](area.a);out center tags;'
    )
    for url in OVERPASS:
        try:
            data = await http_get(url, params={"data": consulta}, headers=UA_OSM, timeout=30,
                                  max_retries=0)  # fmt: skip
        except Exception:
            continue
        bairros = {}
        for e in data.get("elements", []) if isinstance(data, dict) else []:
            nome = (e.get("tags") or {}).get("name")
            centro = e.get("center") or e
            if nome and "lat" in centro:
                bairros[nome] = {"nome": nome, "lat": centro["lat"], "lon": centro["lon"]}
        return sorted(bairros.values(), key=lambda b: normalizar(b["nome"]))
    return []


# --- Avisos INMET no ponto --------------------------------------------------------


@ttl_cache(ttl=600)
async def avisos_ativos() -> list[dict[str, Any]]:
    data = await http_get(INMET_ATIVOS, timeout=40)
    if not isinstance(data, dict):
        return []
    return [a for lista in data.values() if isinstance(lista, list) for a in lista]


def _texto_lista(valor: Any) -> str:
    """INMET sends risks/instructions as a Python-like list string: "['a', 'b']"."""
    texto = str(valor or "").strip()
    if texto.startswith("[") and texto.endswith("]"):
        partes = [p.strip(" '\"") for p in texto[1:-1].split("', '")]
        return " · ".join(p for p in partes if p)
    return texto


def avisos_para(avisos: list[dict[str, Any]], local: Local) -> list[AvisoLocal]:
    saida = []
    for a in avisos:
        try:
            geo = json.loads(a.get("poligono") or "{}")
        except ValueError:
            geo = {}
        dentro = bool(geo) and ponto_no_poligono(local.lat, local.lon, geo)
        no_municipio = bool(local.geocodigo) and local.geocodigo in str(a.get("geocodes", ""))
        if not (dentro or no_municipio):
            continue
        inicio = f"{str(a.get('data_inicio', ''))[:10]} {a.get('hora_inicio', '')}".strip()
        fim = f"{str(a.get('data_fim', ''))[:10]} {a.get('hora_fim', '')}".strip()
        saida.append(
            AvisoLocal(
                evento=a.get("descricao", ""),
                severidade=a.get("severidade", ""),
                cor=a.get("aviso_cor", ""),
                inicio=inicio,
                fim=fim,
                riscos=_texto_lista(a.get("riscos")),
                instrucoes=_texto_lista(a.get("instrucoes")),
                dentro_do_poligono=dentro,
                poligono=geo or None,
            )
        )
    ordem = {"Grande Perigo": 0, "Perigo": 1, "Perigo Potencial": 2}
    return sorted(saida, key=lambda a: ordem.get(a.severidade, 3))


# --- Observação (METAR) -----------------------------------------------------------

KT_PARA_KMH = 1.852


@ttl_cache(ttl=600, maxsize=512)
async def observacao_proxima(lat: float, lon: float) -> Observacao | None:
    """Latest METAR from the nearest airport within ~250 km."""
    bbox = f"{lat - 2.2:.2f},{lon - 2.2:.2f},{lat + 2.2:.2f},{lon + 2.2:.2f}"
    data = await http_get(AWC_METAR, params={"bbox": bbox, "format": "json", "hours": 3})
    if not isinstance(data, list) or not data:
        return None
    ultimos: dict[str, dict[str, Any]] = {}
    for m in data:
        atual = ultimos.get(m["icaoId"])
        if atual is None or m.get("obsTime", 0) > atual.get("obsTime", 0):
            ultimos[m["icaoId"]] = m
    m = min(ultimos.values(), key=lambda x: distancia_km(lat, lon, x["lat"], x["lon"]))
    wspd, wgst = m.get("wspd"), m.get("wgst")
    return Observacao(
        estacao=m["icaoId"],
        nome=m.get("name", ""),
        distancia_km=round(distancia_km(lat, lon, m["lat"], m["lon"]), 1),
        quando=datetime.fromtimestamp(m.get("obsTime", 0), tz=timezone.utc).isoformat(),
        temperatura=m.get("temp"),
        ponto_orvalho=m.get("dewp"),
        vento_kmh=round(wspd * KT_PARA_KMH, 1) if isinstance(wspd, (int, float)) else None,
        rajada_kmh=round(wgst * KT_PARA_KMH, 1) if isinstance(wgst, (int, float)) else None,
        fenomeno=m.get("wxString") or "",
        bruto=m.get("rawOb", ""),
        lat=m["lat"],
        lon=m["lon"],
    )


# --- Previsão multimodelo ---------------------------------------------------------

VARIAVEIS_HORA = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,"
    "precipitation,precipitation_probability,cape,weather_code,uv_index"
)


@ttl_cache(ttl=1800, maxsize=512)
async def previsao(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": VARIAVEIS_HORA,
        "daily": "temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,precipitation_sum",
        "models": "best_match," + ",".join(MODELOS),
        "timezone": "auto",
        "forecast_days": 3,
    }
    url, params = open_meteo(OPEN_METEO, params)
    data: dict[str, Any] = await http_get(url, params=params, timeout=40)
    data["fonte"] = "Open-Meteo (ECMWF, ICON, GFS)"
    return data


_SIMBOLOS_TROVOADA = ("thunder",)


@ttl_cache(ttl=1800, maxsize=512)
async def previsao_met_norway(lat: float, lon: float) -> dict[str, Any]:
    """Fallback forecast from MET Norway (free, CC BY 4.0 — commercial use allowed).

    Returned in the Open-Meteo shape (single model, no CAPE/gusts/probability). Times are
    converted to local time with an offset estimated from the longitude (Brazil: -2 to -5 h).
    """
    data = await http_get(
        MET_NORWAY,
        params={"lat": round(lat, 4), "lon": round(lon, 4)},
        headers={"User-Agent": UA_OSM["User-Agent"]},
        timeout=40,
    )
    offset_h = max(-5, min(-2, round(lon / 15)))
    horas: dict[str, list[Any]] = {k: [] for k in ("time", *VARIAVEIS_HORA.split(","))}
    for item in (data.get("properties") or {}).get("timeseries", [])[:72]:
        dt = datetime.fromisoformat(item["time"].replace("Z", "+00:00")) + timedelta(
            hours=offset_h
        )
        inst = item["data"]["instant"]["details"]
        prox = item["data"].get("next_1_hours") or {}
        simbolo = (prox.get("summary") or {}).get("symbol_code", "")
        vento = inst.get("wind_speed")
        horas["time"].append(dt.strftime("%Y-%m-%dT%H:00"))
        horas["temperature_2m"].append(inst.get("air_temperature"))
        horas["apparent_temperature"].append(inst.get("apparent_air_temperature"))
        horas["relative_humidity_2m"].append(inst.get("relative_humidity"))
        horas["wind_speed_10m"].append(round(vento * 3.6, 1) if vento is not None else None)
        horas["wind_gusts_10m"].append(None)
        horas["precipitation"].append((prox.get("details") or {}).get("precipitation_amount"))
        horas["precipitation_probability"].append(None)
        horas["cape"].append(None)
        horas["weather_code"].append(95 if any(s in simbolo for s in _SIMBOLOS_TROVOADA) else 0)
        horas["uv_index"].append(inst.get("ultraviolet_index_clear_sky"))
    return {
        "utc_offset_seconds": offset_h * 3600,
        "hourly": horas,
        "daily": {},
        "elevation": None,
        "fonte": "MET Norway (reserva — sem rajadas, CAPE ou consenso de modelos)",
    }


def serie(
    dados: dict[str, Any], bloco: str, variavel: str, modelo: str = "best_match"
) -> list[Any]:
    b = dados.get(bloco, {})
    return list(b.get(f"{variavel}_{modelo}") or b.get(variavel) or [])


def proximas_horas(dados: dict[str, Any], horas: int = 48) -> dict[str, list[Any]]:
    """Best-match hourly series from the current hour onwards."""
    tempos = serie(dados, "hourly", "time")
    offset = int(dados.get("utc_offset_seconds", 0))
    agora = (datetime.now(timezone.utc) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:00")
    inicio = next((i for i, t in enumerate(tempos) if t >= agora), 0)
    fim = inicio + horas
    saida = {"time": tempos[inicio:fim]}
    for v in VARIAVEIS_HORA.split(","):
        saida[v] = serie(dados, "hourly", v)[inicio:fim]
    return saida


def consenso(dados: dict[str, Any]) -> list[dict[str, Any]]:
    """Per day and model: max temperature, max gust and rain — plus the spread."""
    dias = serie(dados, "daily", "time")
    saida = []
    for i, dia in enumerate(dias):
        linha: dict[str, Any] = {"dia": dia, "modelos": {}}
        for chave, nome in MODELOS.items():

            def v(var: str, c: str = chave, idx: int = i) -> Any:
                s = serie(dados, "daily", var, c)
                return s[idx] if idx < len(s) else None

            linha["modelos"][nome] = {
                "tmax": v("temperature_2m_max"),
                "tmin": v("temperature_2m_min"),
                "rajada": v("wind_gusts_10m_max"),
                "chuva": v("precipitation_sum"),
            }
        for campo in ("tmax", "rajada", "chuva"):
            valores = [m[campo] for m in linha["modelos"].values() if m[campo] is not None]
            linha[f"{campo}_spread"] = round(max(valores) - min(valores), 1) if valores else None
            linha[f"{campo}_max"] = max(valores) if valores else None
        saida.append(linha)
    return saida


# --- Riscos (critérios INMET + índice de calor NOAA) -------------------------------


def _pico(tempos: list[str], valores: list[Any]) -> tuple[float, str]:
    pares = [(v, t) for v, t in zip(valores, tempos, strict=False) if v is not None]
    if not pares:
        return 0.0, ""
    v, t = max(pares, key=lambda p: p[0])
    return float(v), t


def avaliar_riscos(h: dict[str, list[Any]], cons: list[dict[str, Any]]) -> list[Risco]:
    t = h.get("time", [])
    riscos: list[Risco] = []

    sens, quando = _pico(t, h.get("apparent_temperature", []))
    tmax, _ = _pico(t, h.get("temperature_2m", []))
    nivel = 3 if sens >= 54 else 2 if sens >= 41 else 1 if sens >= 32 or tmax >= 35 else 0
    riscos.append(Risco(
        tipo="calor", nivel=nivel, rotulo=NIVEIS[nivel],
        valor=f"sensação {sens:.0f}°C · máx {tmax:.0f}°C", quando=quando,
        criterio="Índice de calor (NOAA): 32-41 atenção · 41-54 perigo · >54 perigo extremo",
    ))  # fmt: skip

    rajadas = h.get("wind_gusts_10m", [])
    tem_rajada = any(v is not None for v in rajadas)
    rajada, quando = _pico(t, rajadas if tem_rajada else h.get("wind_speed_10m", []))
    rajada_modelos = max((d.get("rajada_max") or 0) for d in cons) if cons else 0
    pior = max(rajada, rajada_modelos)
    nivel = 3 if pior >= 100 else 2 if pior >= 60 else 1 if pior >= 40 else 0
    valor = (
        f"rajada {rajada:.0f} km/h (pior modelo {rajada_modelos:.0f})"
        if tem_rajada
        else f"vento {rajada:.0f} km/h (rajadas indisponíveis)"
    )
    riscos.append(Risco(
        tipo="ventania", nivel=nivel, rotulo=NIVEIS[nivel], valor=valor, quando=quando,
        criterio="INMET: 40-60 km/h perigo potencial · 60-100 perigo · >100 grande perigo",
    ))  # fmt: skip

    cape, quando_cape = _pico(t, h.get("cape", []))
    trovoada = [
        tt for tt, c in zip(t, h.get("weather_code", []), strict=False) if c in (95, 96, 99)
    ]
    granizo = any(c in (96, 99) for c in h.get("weather_code", []))
    nivel = (
        3 if (granizo and cape >= 2500) else 2 if (trovoada and cape >= 1500) or cape >= 2500
        else 1 if trovoada or cape >= 1000 else 0
    )  # fmt: skip
    riscos.append(Risco(
        tipo="tempestade", nivel=nivel, rotulo=NIVEIS[nivel],
        valor=f"CAPE {cape:.0f} J/kg · {len(trovoada)}h com trovoada" + (" · granizo" if granizo
                                                                        else ""),
        quando=trovoada[0] if trovoada else quando_cape,
        criterio="Energia convectiva (CAPE) >1000 favorece tempestades; >2500 severas",
    ))  # fmt: skip

    chuva_h, quando = _pico(t, h.get("precipitation", []))
    chuva_dia = max((d.get("chuva_max") or 0) for d in cons) if cons else 0
    nivel = (
        3 if chuva_h > 60 or chuva_dia > 100 else 2 if chuva_h >= 30 or chuva_dia >= 50
        else 1 if chuva_h >= 20 or chuva_dia >= 30 else 0
    )  # fmt: skip
    riscos.append(Risco(
        tipo="chuva", nivel=nivel, rotulo=NIVEIS[nivel],
        valor=f"{chuva_h:.1f} mm/h · até {chuva_dia:.0f} mm/dia", quando=quando,
        criterio="INMET: 20-30 mm/h perigo potencial · 30-60 perigo · >60 grande perigo",
    ))  # fmt: skip

    umidades = [(u, tt) for u, tt in zip(h.get("relative_humidity_2m", []), t, strict=False)
                if u is not None]  # fmt: skip
    umin, quando = min(umidades, key=lambda p: p[0]) if umidades else (100, "")
    nivel = 3 if umin < 12 else 2 if umin < 20 else 1 if umin <= 30 else 0
    riscos.append(Risco(
        tipo="umidade", nivel=nivel, rotulo=NIVEIS[nivel], valor=f"mínima {umin:.0f}%",
        quando=quando,
        criterio="INMET: 30-20% perigo potencial · 20-12% perigo · <12% grande perigo",
    ))  # fmt: skip
    return riscos


# --- Focos de queimada (INPE) -----------------------------------------------------


@ttl_cache(ttl=3600)
async def _focos_brasil() -> list[dict[str, Any]]:
    hoje = datetime.now(timezone.utc).date()
    for dia in (hoje, hoje - timedelta(days=1)):
        try:
            texto = await http_get_text(
                INPE_FOCOS_DIA.format(data=dia.strftime("%Y%m%d")), timeout=60, max_retries=1
            )
        except Exception:
            continue
        linhas = list(csv.DictReader(io.StringIO(texto)))
        if linhas:
            return linhas
    return []


async def focos_proximos(lat: float, lon: float, raio_km: float = 50) -> list[dict[str, Any]]:
    saida = []
    for f in await _focos_brasil():
        try:
            flat, flon = float(f["lat"]), float(f["lon"])
        except (KeyError, ValueError):
            continue
        if abs(flat - lat) > 1 or abs(flon - lon) > 1:
            continue
        d = distancia_km(lat, lon, flat, flon)
        if d <= raio_km:
            saida.append({
                "lat": flat, "lon": flon, "distancia_km": round(d, 1),
                "quando": f.get("data_hora_gmt", ""), "satelite": f.get("satelite", ""),
                "risco_fogo": f.get("risco_fogo") or None,
                "dias_sem_chuva": f.get("numero_dias_sem_chuva") or None,
            })  # fmt: skip
    return sorted(saida, key=lambda x: x["distancia_km"])


# --- Agregado -----------------------------------------------------------------------


async def _estacao_local(local: Local) -> dict[str, Any] | None:
    """Best measured reading for the exact point (Embrapa, then INMET)."""
    leitura = await medicao_local(local.geocodigo, local.lat, local.lon)
    return leitura.model_dump() if leitura else None


async def relatorio(local: Local) -> dict[str, Any]:
    """Everything the local climate dashboard needs, fetched concurrently."""
    resultados = await asyncio.gather(
        avisos_ativos(),
        observacao_proxima(round(local.lat, 3), round(local.lon, 3)),
        previsao(round(local.lat, 4), round(local.lon, 4)),
        focos_proximos(local.lat, local.lon),
        _estacao_local(local),
        return_exceptions=True,
    )
    avisos, obs, prev, focos, estacao = (
        None if isinstance(r, BaseException) else r for r in resultados
    )
    falhas = [
        nome
        for nome, r in zip(
            ("inmet", "metar", "previsao", "focos", "estacao"), resultados, strict=True
        )
        if isinstance(r, BaseException)
    ]
    if not isinstance(prev, dict):
        try:
            prev = await previsao_met_norway(round(local.lat, 4), round(local.lon, 4))
            falhas = [f if f != "previsao" else "open-meteo (usando MET Norway)" for f in falhas]
        except Exception:
            prev = None
    horas = proximas_horas(prev) if isinstance(prev, dict) else {}
    cons = consenso(prev) if isinstance(prev, dict) else []
    return {
        "local": local.model_dump(),
        "avisos": [a.model_dump() for a in avisos_para(avisos, local)] if avisos else [],
        "observacao": obs.model_dump() if isinstance(obs, Observacao) else None,
        "estacao": estacao if isinstance(estacao, dict) else None,
        "horas": horas,
        "consenso": cons,
        "riscos": [r.model_dump() for r in avaliar_riscos(horas, cons)] if horas else [],
        "focos": focos or [],
        "elevacao_m": prev.get("elevation") if isinstance(prev, dict) else None,
        "fonte_previsao": prev.get("fonte", "") if isinstance(prev, dict) else "",
        "falhas": falhas,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
