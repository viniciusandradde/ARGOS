"""Tests for the SICONFI HTTP client."""

import httpx
import pytest
import respx

from mcp_brasil.data.siconfi import client
from mcp_brasil.data.siconfi.constants import ENTES_URL, EXTRATO_URL, RGF_URL, RREO_URL


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    client.listar_entes.cache.clear()  # type: ignore[attr-defined]


class TestEsfera:
    def test_infers_sphere(self) -> None:
        assert client.esfera_do_ente(1) == "U"
        assert client.esfera_do_ente(35) == "E"
        assert client.esfera_do_ente(3509502) == "M"


class TestBuscarEntes:
    @respx.mock
    async def test_filters_by_name_and_uf(self) -> None:
        respx.get(ENTES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"cod_ibge": 3509502, "ente": "Campinas", "uf": "SP", "esfera": "M"},
                        {"cod_ibge": 2202109, "ente": "Campinas do Piauí", "uf": "PI"},
                        {"cod_ibge": 35, "ente": "São Paulo", "uf": "SP", "esfera": "E"},
                    ]
                },
            )
        )
        result = await client.buscar_entes("campinas", "sp")
        assert [e.cod_ibge for e in result] == [3509502]


class TestDemonstrativos:
    @respx.mock
    async def test_rreo_sends_expected_params(self) -> None:
        route = respx.get(RREO_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"conta": "RECEITAS", "coluna": "X", "valor": 10.5}]}
            )
        )
        linhas = await client.consultar_rreo(35, 2024, 6, "RREO-Anexo 01")
        assert linhas[0].valor == 10.5
        params = route.calls[0].request.url.params
        assert params["co_esfera"] == "E"
        assert params["co_tipo_demonstrativo"] == "RREO"
        assert params["no_anexo"] == "RREO-Anexo 01"

    @respx.mock
    async def test_rgf_uses_poder(self) -> None:
        route = respx.get(RGF_URL).mock(return_value=httpx.Response(200, json={"items": []}))
        assert await client.consultar_rgf(3509502, 2024, 3, "RGF-Anexo 01", poder="L") == []
        params = route.calls[0].request.url.params
        assert params["co_poder"] == "L"
        assert params["co_esfera"] == "M"

    @respx.mock
    async def test_extrato(self) -> None:
        respx.get(EXTRATO_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"entregavel": "RGF", "data_status": "2025-01-30T00:00:00Z"}]}
            )
        )
        entregas = await client.extrato_entregas(35, 2025)
        assert entregas[0].entregavel == "RGF"
