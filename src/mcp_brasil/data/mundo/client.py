"""HTTP clients for Frankfurter (ECB reference rates) and the World Bank API."""

from __future__ import annotations

from typing import Any

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get

from .constants import FRANKFURTER_URL, WORLD_BANK_URL


@ttl_cache(ttl=1800)
async def cotacoes(base: str = "USD", moedas: str = "BRL,EUR,CNY,ARS,GBP,JPY") -> dict[str, Any]:
    data: dict[str, Any] = await http_get(
        f"{FRANKFURTER_URL}/latest", params={"base": base.upper(), "symbols": moedas.upper()}
    )
    return data


async def historico(base: str, moeda: str, inicio: str, fim: str = "") -> dict[str, Any]:
    data: dict[str, Any] = await http_get(
        f"{FRANKFURTER_URL}/{inicio}..{fim}",
        params={"base": base.upper(), "symbols": moeda.upper()},
    )
    return data


@ttl_cache(ttl=86400)
async def indicador(codigo: str, pais: str = "BR", anos: int = 10) -> list[dict[str, Any]]:
    url = WORLD_BANK_URL.format(pais=pais, indicador=codigo)
    data = await http_get(url, params={"format": "json", "per_page": anos, "mrv": anos})
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return [d for d in data[1] if d.get("value") is not None]
    return []
