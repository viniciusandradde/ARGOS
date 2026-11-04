"""Tests for the local (neighbourhood-level) climate risk engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from mcp_brasil.data.clima import local as L
from mcp_brasil.data.clima import tools

QUADRADO = {"type": "Polygon", "coordinates": [[[-55, -23], [-54, -23], [-54, -22], [-55, -22],
                                                [-55, -23]]]}  # fmt: skip
COM_BURACO = {
    "type": "Polygon",
    "coordinates": [
        [[-56, -24], [-53, -24], [-53, -21], [-56, -21], [-56, -24]],
        [[-55, -23], [-54, -23], [-54, -22], [-55, -22], [-55, -23]],
    ],
}


@pytest.fixture(autouse=True)
def _limpar() -> None:
    L._CACHE_LOCAL.clear()
    for f in (L.observacao_proxima, L.previsao, L.avisos_ativos):
        f.cache.clear()  # type: ignore[attr-defined]


class TestGeometria:
    def test_poligono(self) -> None:
        assert L.ponto_no_poligono(-22.5, -54.5, QUADRADO)
        assert not L.ponto_no_poligono(-21.5, -54.5, QUADRADO)

    def test_buraco_e_multipoligono(self) -> None:
        assert not L.ponto_no_poligono(-22.5, -54.5, COM_BURACO)
        assert L.ponto_no_poligono(-21.5, -55.5, COM_BURACO)
        multi = {"type": "MultiPolygon", "coordinates": [QUADRADO["coordinates"]]}
        assert L.ponto_no_poligono(-22.5, -54.5, multi)

    def test_distancia(self) -> None:
        assert 95 < L.distancia_km(-22.2286, -54.8203, -22.55, -55.703) < 100


class TestAvisos:
    def test_poligono_ou_municipio(self) -> None:
        local = L.Local(lat=-22.5, lon=-54.5, nome="x", geocodigo="5003702")
        avisos = [
            {"descricao": "Tempestade", "severidade": "Perigo Potencial",
             "poligono": json.dumps(QUADRADO), "geocodes": ""},
            {"descricao": "Chuvas", "severidade": "Grande Perigo", "poligono": "",
             "geocodes": "5003702,5002704", "riscos": "['Chuva forte', 'Ventos']"},
            {"descricao": "Calor", "severidade": "Perigo", "poligono": "", "geocodes": "123"},
        ]  # fmt: skip
        r = L.avisos_para(avisos, local)
        assert [a.evento for a in r] == ["Chuvas", "Tempestade"]  # sorted by severity
        assert r[0].dentro_do_poligono is False and r[1].dentro_do_poligono is True
        assert r[0].riscos == "Chuva forte · Ventos"


def _horas(**over: list[object]) -> dict[str, list[object]]:
    base: dict[str, list[object]] = {
        "time": ["2026-11-04T10:00", "2026-11-04T11:00"],
        "temperature_2m": [30, 31],
        "apparent_temperature": [33, 35],
        "relative_humidity_2m": [60, 55],
        "wind_gusts_10m": [20, 30],
        "precipitation": [0, 0],
        "cape": [100, 200],
        "weather_code": [1, 2],
    }
    base.update(over)
    return base


class TestRiscos:
    def niveis(
        self, h: dict[str, list[object]], cons: list[dict[str, object]] | None = None
    ) -> dict[str, int]:
        return {r.tipo: r.nivel for r in L.avaliar_riscos(h, cons or [])}

    def test_calmo(self) -> None:
        n = self.niveis(_horas(apparent_temperature=[25, 28], temperature_2m=[25, 27]))
        assert set(n.values()) == {0}

    def test_limiares_inmet(self) -> None:
        h = _horas(
            wind_gusts_10m=[65, 10],
            precipitation=[35, 0],
            relative_humidity_2m=[15, 40],
            cape=[2600, 0],
            weather_code=[95, 1],
            apparent_temperature=[42, 30],
        )
        n = self.niveis(h)
        assert n == {"calor": 2, "ventania": 2, "tempestade": 2, "chuva": 2, "umidade": 2}

    def test_pior_modelo_e_granizo(self) -> None:
        cons = [{"rajada_max": 105, "chuva_max": 120}]
        h = _horas(cape=[3000, 0], weather_code=[96, 1])
        n = self.niveis(h, cons)
        assert n["ventania"] == 3 and n["chuva"] == 3 and n["tempestade"] == 3


class TestPrevisao:
    def test_consenso_e_horas(self) -> None:
        dados = {
            "utc_offset_seconds": 0,
            "hourly": {"time": ["2000-01-01T00:00", "2999-01-01T00:00"],
                       "temperature_2m": [1, 2]},
            "daily": {
                "time": ["2026-11-04"],
                "temperature_2m_max_ecmwf_ifs025": [33.0],
                "temperature_2m_max_icon_global": [35.7],
                "temperature_2m_max_gfs_seamless": [38.2],
                "wind_gusts_10m_max_gfs_seamless": [64.0],
            },
        }  # fmt: skip
        [c] = L.consenso(dados)
        assert c["tmax_spread"] == 5.2 and c["rajada_max"] == 64.0
        assert c["modelos"]["NOAA GFS"]["tmax"] == 38.2
        horas = L.proximas_horas(dados)
        assert horas["time"] == ["2999-01-01T00:00"] and horas["temperature_2m"] == [2]


class TestFontes:
    @respx.mock
    async def test_metar_mais_proximo(self) -> None:
        respx.get(L.AWC_METAR).mock(
            return_value=httpx.Response(200, json=[
                {"icaoId": "SBCG", "lat": -20.47, "lon": -54.67, "obsTime": 1, "temp": 31},
                {"icaoId": "SBPP", "lat": -22.55, "lon": -55.70, "obsTime": 1, "temp": 30,
                 "wspd": 10, "wgst": 25, "wxString": "TSRA", "rawOb": "METAR SBPP"},
                {"icaoId": "SBPP", "lat": -22.55, "lon": -55.70, "obsTime": 2, "temp": 32,
                 "wspd": 11, "rawOb": "METAR SBPP novo"},
            ])
        )  # fmt: skip
        o = await L.observacao_proxima(-22.228, -54.811)
        assert o is not None and o.estacao == "SBPP" and o.temperatura == 32
        assert o.vento_kmh == pytest.approx(20.4, 0.01) and o.bruto == "METAR SBPP novo"
        bbox = respx.calls[0].request.url.params["bbox"]
        assert bbox == "-24.43,-57.01,-20.03,-52.61"

    @respx.mock
    async def test_localizar_nominatim(self) -> None:
        respx.get(L.NOMINATIM).mock(
            return_value=httpx.Response(200, json=[
                {"lat": "-15.5", "lon": "-56.0", "addresstype": "residential",
                 "address": {"city": "Cuiabá"}},
                {"lat": "-22.2278", "lon": "-54.8112", "addresstype": "suburb",
                 "address": {"city": "Dourados"}},
            ])
        )  # fmt: skip
        loc = await L.localizar("Dourados", "MS", "Centro")
        assert loc is not None and loc.precisao == "bairro" and loc.lat == -22.2278
        assert loc.geocodigo == "5003702"

    @respx.mock
    async def test_localizar_photon_e_fallback(self) -> None:
        respx.get(L.NOMINATIM).mock(return_value=httpx.Response(200, json=[]))
        respx.get(L.PHOTON).mock(
            return_value=httpx.Response(200, json={"features": [
                {"properties": {"city": "Dourados", "district": "Jardim América"},
                 "geometry": {"coordinates": [-54.82, -22.22]}},
                {"properties": {"city": "Dourados", "district": "Jardim América"},
                 "geometry": {"coordinates": [-54.80, -22.24]}},
                {"properties": {"city": "Outra", "district": "Jardim América"},
                 "geometry": {"coordinates": [0, 0]}},
            ]})
        )  # fmt: skip
        loc = await L.localizar("Dourados", "MS", "Jardim América")
        assert (
            loc is not None and loc.lat == pytest.approx(-22.23) and "2 referências" in loc.fonte
        )
        respx.get(L.OPEN_METEO_GEO).mock(
            return_value=httpx.Response(200, json={"results": [
                {"latitude": -22.22, "longitude": -54.8, "admin1": "Mato Grosso do Sul"}]})
        )  # fmt: skip
        loc2 = await L.localizar("Dourados", "MS", "Bairro Inexistente")
        assert loc2 is not None and loc2.precisao == "municipio"
        # the fallback is not cached; the real bairro is
        assert ("dourados", "MS", "bairro inexistente") not in L._CACHE_LOCAL
        assert ("dourados", "MS", "jardim america") in L._CACHE_LOCAL

    async def test_focos_raio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(L, "_focos_brasil", AsyncMock(return_value=[
            {"lat": "-22.30", "lon": "-54.80", "satelite": "GOES-19", "data_hora_gmt": "x"},
            {"lat": "-23.50", "lon": "-54.80"},
            {"lat": "bad", "lon": "0"},
        ]))  # fmt: skip
        focos = await L.focos_proximos(-22.2286, -54.8203)
        assert len(focos) == 1 and focos[0]["distancia_km"] < 10


async def test_tool_risco_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        L, "relatorio",
        AsyncMock(return_value={
            "avisos": [{"evento": "Tempestade", "severidade": "Perigo", "inicio": "a",
                        "fim": "b", "dentro_do_poligono": True}],
            "riscos": [{"tipo": "ventania", "nivel": 2, "rotulo": "Perigo",
                        "valor": "rajada 64 km/h", "quando": "2026-11-05T10:00"}],
            "observacao": None, "consenso": [], "focos": [], "falhas": ["metar"],
        }),
    )  # fmt: skip
    out = await tools.risco_local("Dourados", AsyncMock(), uf="MS", lat=-22.2, lon=-54.8)
    assert "ponto DENTRO da área" in out and "🟠 **VENTANIA: Perigo**" in out
    assert "indisponíveis agora: metar" in out


class TestReservaEChave:
    def test_open_meteo_comercial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_brasil.data.clima.constants import open_meteo

        assert open_meteo("https://api.open-meteo.com/v1/forecast", {"a": 1}) == (
            "https://api.open-meteo.com/v1/forecast",
            {"a": 1},
        )
        monkeypatch.setattr("mcp_brasil.settings.OPEN_METEO_API_KEY", "k")
        url, params = open_meteo("https://geocoding-api.open-meteo.com/v1/search", {})
        assert url == "https://customer-geocoding-api.open-meteo.com/v1/search"
        assert params == {"apikey": "k"}

    @respx.mock
    async def test_met_norway(self) -> None:
        L.previsao_met_norway.cache.clear()  # type: ignore[attr-defined]
        respx.get(L.MET_NORWAY).mock(
            return_value=httpx.Response(200, json={"properties": {"timeseries": [
                {"time": "2999-01-01T12:00:00Z", "data": {
                    "instant": {"details": {"air_temperature": 33.0, "relative_humidity": 40,
                                            "apparent_air_temperature": 36.0, "wind_speed": 10}},
                    "next_1_hours": {"summary": {"symbol_code": "heavyrainandthunder"},
                                     "details": {"precipitation_amount": 25.0}}}},
            ]}})
        )  # fmt: skip
        d = await L.previsao_met_norway(-22.2, -54.8)
        assert d["utc_offset_seconds"] == -4 * 3600
        h = d["hourly"]
        assert h["time"] == ["2999-01-01T08:00"] and h["wind_speed_10m"] == [36.0]
        assert h["weather_code"] == [95] and h["wind_gusts_10m"] == [None]
        riscos = {r.tipo: r for r in L.avaliar_riscos(L.proximas_horas(d), [])}
        assert "rajadas indisponíveis" in riscos["ventania"].valor
        assert riscos["chuva"].nivel == 1 and riscos["tempestade"].nivel == 1

    async def test_relatorio_usa_reserva(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(L, "avisos_ativos", AsyncMock(return_value=[]))
        monkeypatch.setattr(L, "observacao_proxima", AsyncMock(return_value=None))
        monkeypatch.setattr(L, "medicao_local", AsyncMock(return_value=None))
        monkeypatch.setattr(L, "focos_proximos", AsyncMock(return_value=[]))
        monkeypatch.setattr(L, "previsao", AsyncMock(side_effect=RuntimeError("429")))
        reserva = {"utc_offset_seconds": 0, "hourly": {"time": ["2999-01-01T00:00"],
                   "temperature_2m": [30]}, "daily": {}, "fonte": "MET Norway"}  # fmt: skip
        monkeypatch.setattr(L, "previsao_met_norway", AsyncMock(return_value=reserva))
        r = await L.relatorio(L.ponto(-22.2, -54.8))
        assert r["falhas"] == ["open-meteo (usando MET Norway)"]
        assert r["fonte_previsao"] == "MET Norway" and r["horas"]["temperature_2m"] == [30]
