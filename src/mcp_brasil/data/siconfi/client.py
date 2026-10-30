"""HTTP client for the SICONFI API.

Base URL: https://apidatalake.tesouro.gov.br/ords/siconfi/tt
Auth: None required
Response format (Oracle ORDS): {"items": [...], "hasMore": bool, "count": int, ...}
"""

from __future__ import annotations

from typing import Any

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get

from .constants import DCA_URL, ENTES_URL, EXTRATO_URL, ID_UNIAO, RGF_URL, RREO_URL
from .schemas import Ente, Entrega, LinhaDemonstrativo


def esfera_do_ente(id_ente: int) -> str:
    """Infer the SICONFI sphere code from the IBGE code (U, E or M)."""
    if id_ente == ID_UNIAO:
        return "U"
    return "E" if id_ente < 100 else "M"


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        items = data.get("items", [])
        return items if isinstance(items, list) else []
    return []


@ttl_cache(ttl=86400)
async def listar_entes() -> list[Ente]:
    """List all federation entities (cached for 24h — ~5.600 items)."""
    data = await http_get(ENTES_URL, timeout=60)
    return [Ente(**item) for item in _items(data)]


async def buscar_entes(nome: str | None = None, uf: str | None = None) -> list[Ente]:
    """Filter entities by (partial, case-insensitive) name and/or UF."""
    entes = await listar_entes()
    if nome:
        alvo = nome.casefold()
        entes = [e for e in entes if alvo in e.ente.casefold()]
    if uf:
        entes = [e for e in entes if (e.uf or "").upper() == uf.upper()]
    return entes


async def consultar_rreo(
    id_ente: int, ano: int, bimestre: int, anexo: str, simplificado: bool = False
) -> list[LinhaDemonstrativo]:
    """Fetch an RREO annex (bimonthly budget execution report)."""
    params = {
        "an_exercicio": ano,
        "nr_periodo": bimestre,
        "co_tipo_demonstrativo": "RREO Simplificado" if simplificado else "RREO",
        "no_anexo": anexo,
        "co_esfera": esfera_do_ente(id_ente),
        "id_ente": id_ente,
    }
    data = await http_get(RREO_URL, params=params, timeout=60)
    return [LinhaDemonstrativo(**item) for item in _items(data)]


async def consultar_rgf(
    id_ente: int,
    ano: int,
    periodo: int,
    anexo: str,
    poder: str = "E",
    periodicidade: str = "Q",
) -> list[LinhaDemonstrativo]:
    """Fetch an RGF annex (fiscal management report — LRF limits)."""
    params = {
        "an_exercicio": ano,
        "in_periodicidade": periodicidade,
        "nr_periodo": periodo,
        "co_tipo_demonstrativo": "RGF",
        "no_anexo": anexo,
        "co_esfera": esfera_do_ente(id_ente),
        "co_poder": poder,
        "id_ente": id_ente,
    }
    data = await http_get(RGF_URL, params=params, timeout=60)
    return [LinhaDemonstrativo(**item) for item in _items(data)]


async def consultar_dca(id_ente: int, ano: int, anexo: str) -> list[LinhaDemonstrativo]:
    """Fetch a DCA annex (annual accounts declaration)."""
    params = {"an_exercicio": ano, "no_anexo": anexo, "id_ente": id_ente}
    data = await http_get(DCA_URL, params=params, timeout=60)
    return [LinhaDemonstrativo(**item) for item in _items(data)]


async def extrato_entregas(id_ente: int, ano: int) -> list[Entrega]:
    """List which reports an entity delivered to SICONFI in a given year."""
    params = {"id_ente": id_ente, "an_referencia": ano}
    data = await http_get(EXTRATO_URL, params=params, timeout=60)
    return [Entrega(**item) for item in _items(data)]
