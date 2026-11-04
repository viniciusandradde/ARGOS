"""Tests for the Clima feature (NOAA ENSO, INMET, USGS parsing and tools)."""

from datetime import datetime, timedelta, timezone
from typing import ClassVar
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


class TestEstacaoInmet:
    AGORA = datetime(2026, 11, 4, 21, 50, tzinfo=timezone.utc)
    PAYLOAD: ClassVar[dict[str, dict[str, str]]] = {
        "estacao": {
            "CODIGO": "A721",
            "NOME": "DOURADOS",
            "DISTANCIA_EM_KM": "9",
            "LATITUDE": "-22.19388888",
            "LONGITUDE": "-54.91138888",
        },
        "dados": {
            "DT_MEDICAO": "2026-11-04",
            "HR_MEDICAO": "2100",
            "TEM_INS": "32.8",
            "TEM_MAX": "34.2",
            "UMD_INS": "46",
            "VEN_VEL": "1.3",
            "VEN_RAJ": "11.8",
        },
    }

    def test_converte_leitura(self) -> None:
        r = client.parse_estacao(self.PAYLOAD, agora=self.AGORA)
        assert r is not None
        assert (r.codigo, r.nome, r.distancia_km) == ("A721", "DOURADOS", 9.0)
        assert r.rotulo == "INMET A721 DOURADOS"
        assert (r.temperatura, r.umidade) == (32.8, 46.0)
        assert r.vento_kmh == 4.7  # m/s -> km/h
        assert r.rajada_kmh == 42.5
        assert r.quando == "2026-11-04T21:00:00+00:00"

    def test_recusa_leitura_antiga(self) -> None:
        depois = self.AGORA + timedelta(hours=4)
        assert client.parse_estacao(self.PAYLOAD, agora=depois) is None

    def test_recusa_estacao_distante(self) -> None:
        longe = {**self.PAYLOAD, "estacao": {**self.PAYLOAD["estacao"], "DISTANCIA_EM_KM": "90"}}
        assert client.parse_estacao(longe, agora=self.AGORA) is None

    @pytest.mark.parametrize("temperatura", [None, "", "abc"])
    def test_recusa_sem_temperatura(self, temperatura: str | None) -> None:
        vazio = {**self.PAYLOAD, "dados": {**self.PAYLOAD["dados"], "TEM_INS": temperatura}}
        assert client.parse_estacao(vazio, agora=self.AGORA) is None

    def test_coordenadas_valem_mais_que_a_distancia_informada(self) -> None:
        # The API reports 71 km for the station that sits inside Campo Grande
        estacao = {
            **self.PAYLOAD["estacao"],
            "DISTANCIA_EM_KM": "71",
            "LATITUDE": "-20.45",
            "LONGITUDE": "-54.61",
        }
        r = client.parse_estacao(
            {**self.PAYLOAD, "estacao": estacao}, -20.4428, -54.6464, self.AGORA
        )
        assert r is not None
        assert r.distancia_km < 5

    def test_recusa_estacao_distante_pelas_coordenadas(self) -> None:
        assert client.parse_estacao(self.PAYLOAD, -20.44, -54.64, self.AGORA) is None

    def test_recusa_payload_vazio(self) -> None:
        assert client.parse_estacao({}, agora=self.AGORA) is None
        assert client.parse_estacao({"estacao": {}, "dados": None}, agora=self.AGORA) is None


class TestFaixaModelos:
    def test_extremos_por_dia(self) -> None:
        dados = {
            "daily": {
                "time": ["2026-11-04", "2026-11-05"],
                "temperature_2m_max_ecmwf_ifs025": [33.2, 30.3],
                "temperature_2m_max_icon_global": [35.0, None],
                "temperature_2m_max_gfs_seamless": [36.7, 33.0],
            }
        }
        assert client.parse_faixa(dados) == {
            "2026-11-04": (33.2, 36.7),
            "2026-11-05": (30.3, 33.0),
        }

    def test_ignora_dia_com_um_modelo(self) -> None:
        dados = {"daily": {"time": ["2026-11-04"], "temperature_2m_max_gfs_seamless": [36.7]}}
        assert client.parse_faixa(dados) == {}


class TestGuiaClima:
    AGORA = datetime(2026, 11, 4, 22, 7, tzinfo=timezone.utc)
    ESTACAO = (1, "Dourados Embrapa", -22.2753, -54.8183)
    REAL: ClassVar[dict[str, str]] = {
        "day": "04/11/2026 18:00",
        "temp_c_avg": "31.9",
        "urc_pctg_avg": "52.0",
        "u2m_ms": "4.3",
    }
    HOJE: ClassVar[dict[str, str]] = {
        "day": "2026-11-04",
        "temp_c_max": "35.4",
        "temp_c_min": "24.5",
    }

    def _ler(self, real: dict[str, str], hoje: dict[str, str], agora: datetime) -> object:
        return client.parse_guia_clima(real, hoje, self.ESTACAO, -22.22, -54.81, agora)

    def test_converte_leitura_e_extremos(self) -> None:
        r = client.parse_guia_clima(self.REAL, self.HOJE, self.ESTACAO, -22.22, -54.81, self.AGORA)
        assert r is not None
        assert (r.temperatura, r.umidade, r.vento_kmh) == (31.9, 52.0, 15.5)
        assert (r.hoje_max, r.hoje_min) == (35.4, 24.5)
        assert r.quando == "2026-11-04T22:00:00+00:00"  # the API sends local time
        assert r.rotulo == "Embrapa Guia Clima · Dourados Embrapa"
        assert r.distancia_km < 10

    def test_recusa_leitura_antiga(self) -> None:
        assert self._ler(self.REAL, self.HOJE, self.AGORA + timedelta(hours=4)) is None

    def test_recusa_sem_temperatura(self) -> None:
        assert self._ler({**self.REAL, "temp_c_avg": ""}, self.HOJE, self.AGORA) is None

    def test_ignora_extremos_de_outro_dia(self) -> None:
        r = client.parse_guia_clima(
            self.REAL, {**self.HOJE, "day": "2026-11-03"}, self.ESTACAO, -22.2, -54.8, self.AGORA
        )
        assert r is not None
        assert r.hoje_max is None

    @pytest.mark.asyncio
    async def test_fora_do_raio_nao_consulta(self) -> None:
        assert await client.guia_clima_proximo(-20.44, -54.64) is None

    @pytest.mark.asyncio
    async def test_usa_inmet_se_embrapa_falhar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reserva = AsyncMock(return_value="leitura-inmet")
        monkeypatch.setattr(client, "guia_clima_proximo", AsyncMock(side_effect=RuntimeError))
        monkeypatch.setattr(client, "estacao_proxima", reserva)
        assert await client.medicao_local("5003702", -22.2, -54.8) == "leitura-inmet"


class TestPrevisaoInmet:
    def test_junta_periodos_e_dias_simples(self) -> None:
        payload = {
            "5003702": {
                "04/11/2026": {
                    "manha": {"temp_min": 23, "temp_max": 36},
                    "tarde": {"temp_min": 24, "temp_max": 35},
                },
                "06/11/2026": {"temp_min": 23, "temp_max": 34, "resumo": "Chuva"},
            }
        }
        assert client.parse_previsao_inmet(payload, "5003702") == {
            "2026-11-04": (23.0, 36.0),
            "2026-11-06": (23.0, 34.0),
        }

    def test_payload_vazio(self) -> None:
        assert client.parse_previsao_inmet({}, "5003702") == {}
