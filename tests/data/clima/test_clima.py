"""Tests for the Clima feature (NOAA ENSO, INMET, USGS parsing and tools)."""

from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from mcp_brasil.data.clima import client, tools
from mcp_brasil.data.clima.constants import USGS_FEED
from mcp_brasil.data.clima.schemas import LeituraOni, StatusEnso

ONI = """ SEAS  YR   TOTAL   ANOM
  JJA 2026  29.09   1.80
  JAS 2026  29.12   2.16
"""
RONI = """SEAS  YR  ANOM
JAS  2026  1.69
"""
SST = """ Weekly SST data starts week centered on 3Jan1990
 21OCT2026     26.3 5.2     29.4 4.3     30.1 3.4     29.8 1.1
 28OCT2026     26.7 5.4     29.5 4.4     30.2 3.4     30.1 1.4
"""
DISCUSSAO = """<html><body><p><b>ENSO Alert System Status:</b> El Ni&ntilde;o Advisory</p>
<p><b>Synopsis:</b> El Niño continues to strengthen, with a strong-to-very strong El Niño
likely through January-March 2027 (remaining greater than an 83% chance).
El Niño strengthened further last month.</p></body></html>"""

INMET = """<?xml version="1.0"?><rss><channel><item>
<title>Aviso de Tempestade. Severidade Grau: Perigo</title>
<link>https://apiprevmet3.inmet.gov.br/avisos/rss/1</link>
<description><![CDATA[<table><tr><th align="left">Evento</th><td>Tempestade</td></tr>
<tr><th align="left">Severidade</th><td>Perigo</td></tr>
<tr><th align="left">Início</th><td>2026-11-04 00:00:00.0</td></tr>
<tr><th align="left">Fim</th><td>2026-11-04 23:59:00.0</td></tr>
<tr><th align="left">Descrição</th><td>Chuva entre 30 e 60 mm/h.</td></tr>
<tr><th align="left">Área</th><td>Aviso para as Áreas: Sudoeste de Mato Grosso do Sul, \
Oeste Paranaense</td></tr>
</table>]]></description></item></channel></rss>"""


class TestEnsoParsers:
    def test_oni_and_roni(self) -> None:
        oni = client.parse_oni(ONI)
        assert [(o.trimestre, o.anomalia) for o in oni] == [("JJA", 1.8), ("JAS", 2.16)]
        assert client.parse_oni(RONI)[0].anomalia == 1.69

    def test_semanal(self) -> None:
        [_, ultima] = client.parse_sst_semanal(SST)
        assert ultima.semana == "28OCT2026"
        assert (ultima.nino12, ultima.nino34, ultima.nino4) == (5.4, 3.4, 1.4)

    def test_discussao(self) -> None:
        alerta, sinopse = client.parse_discussao(DISCUSSAO)
        assert alerta == "El Niño Advisory"
        assert sinopse.startswith("El Niño continues to strengthen")

    @pytest.mark.parametrize(
        ("valor", "fase"),
        [
            (2.16, "El Niño muito forte"),
            (1.6, "El Niño forte"),
            (0.2, "Neutra"),
            (-1.1, "La Niña moderada"),
        ],
    )
    def test_fase(self, valor: float, fase: str) -> None:
        s = StatusEnso(oni=[LeituraOni(trimestre="JAS", ano=2026, anomalia=valor)])
        assert s.fase == fase


class TestInmet:
    def test_parse_and_vigencia(self) -> None:
        [aviso] = client.parse_avisos_inmet(INMET)
        assert aviso.severidade == "Perigo"
        assert aviso.area.startswith("Sudoeste de Mato Grosso do Sul")
        assert client.aviso_vigente(aviso, datetime(2026, 11, 4, 12))
        assert not client.aviso_vigente(aviso, datetime(2026, 11, 5))

    async def test_tool_filters_area(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.clima.tools.client.avisos_inmet",
            AsyncMock(return_value=client.parse_avisos_inmet(INMET)),
        )
        out = await tools.avisos_inmet(AsyncMock(), area="mato grosso do sul", so_vigentes=False)
        assert "Tempestade — Perigo" in out
        none = await tools.avisos_inmet(AsyncMock(), area="Amazonas", so_vigentes=False)
        assert "Nenhum" in none


class TestTools:
    async def test_el_nino(self, monkeypatch: pytest.MonkeyPatch) -> None:
        status = StatusEnso(
            alerta="El Niño Advisory",
            sinopse="El Niño continues.",
            oni=client.parse_oni(ONI),
            roni=client.parse_oni(RONI),
            semanal=client.parse_sst_semanal(SST),
        )
        monkeypatch.setattr(
            "mcp_brasil.data.clima.tools.client.status_enso", AsyncMock(return_value=status)
        )
        out = await tools.el_nino(AsyncMock())
        assert "El Niño Advisory" in out and "muito forte" in out
        assert "+1.69" in out  # RONI aligned with the JAS row
        assert "chuvas acima da média" in out

    @respx.mock
    async def test_terremotos(self) -> None:
        respx.get(USGS_FEED.format(magnitude="4.5", periodo="day")).mock(
            return_value=httpx.Response(
                200,
                json={
                    "features": [
                        {"properties": {"mag": 5.1, "place": "Peru", "time": 0, "tsunami": 0}},
                        {"properties": {"mag": 6.4, "place": "Chile", "time": 0, "tsunami": 1}},
                    ]
                },
            )
        )
        out = await tools.terremotos(AsyncMock())
        assert out.index("Chile") < out.index("Peru") and "⚠️ sim" in out
        assert "periodo deve" in await tools.terremotos(AsyncMock(), periodo="ano")

    async def test_previsao_cidade_inexistente(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.clima.tools.client.geocodificar", AsyncMock(return_value=[])
        )
        assert "não encontrada" in await tools.previsao_tempo("Xyz", AsyncMock())
