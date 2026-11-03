"""Tests for the Mundo feature."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from mcp_brasil.data.mundo import client, tools
from mcp_brasil.data.mundo.constants import FRANKFURTER_URL


@respx.mock
async def test_cotacoes() -> None:
    client.cotacoes.cache.clear()  # type: ignore[attr-defined]
    respx.get(f"{FRANKFURTER_URL}/latest").mock(
        return_value=httpx.Response(
            200, json={"base": "USD", "date": "2026-11-02", "rates": {"BRL": 5.4378}}
        )
    )
    out = await tools.cotacoes_moedas(AsyncMock())
    assert "5,4378" in out and "2026-11-02" in out


async def test_historico(monkeypatch: pytest.MonkeyPatch) -> None:
    rates = {"2026-10-01": {"BRL": 5.0}, "2026-11-02": {"BRL": 5.5}}
    monkeypatch.setattr(
        "mcp_brasil.data.mundo.tools.client.historico", AsyncMock(return_value={"rates": rates})
    )
    out = await tools.historico_cambio(AsyncMock(), dias=30)
    assert "+10.00%" in out and "5.5000" in out


async def test_indicador_invalido() -> None:
    assert "inválido" in await tools.indicador_banco_mundial("xyz", AsyncMock())


@respx.mock
async def test_indicador_banco_mundial() -> None:
    client.indicador.cache.clear()  # type: ignore[attr-defined]
    respx.get(url__regex=r"https://api\.worldbank\.org/.*").mock(
        return_value=httpx.Response(
            200,
            json=[{"page": 1}, [{"date": "2025", "value": 5.01, "country": {"value": "Brazil"}}]],
        )
    )
    out = await tools.indicador_banco_mundial("inflacao", AsyncMock(), anos=1)
    assert "Brazil" in out and "5,01" in out
