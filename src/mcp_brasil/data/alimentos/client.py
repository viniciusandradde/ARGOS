"""HTTP client for IPCA food items (SIDRA/IBGE)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mcp_brasil._shared.cache import ttl_cache
from mcp_brasil._shared.http_client import http_get

from .constants import ITENS, LOCALIDADES, SIDRA_URL, VAR_12_MESES, VAR_MENSAL


class VariacaoAlimento(BaseModel):
    codigo: str
    item: str
    localidade: str
    localidade_codigo: str = ""
    mes: str
    mes_codigo: str
    variacao_mes: float | None = None
    variacao_12m: float | None = None


def _num(valor: str | None) -> float | None:
    if valor is None or valor in ("", "-", "...", "X"):
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def parse_sidra(linhas: list[dict[str, Any]]) -> list[VariacaoAlimento]:
    """Merge SIDRA rows (one per variable) into one record per item/place/month."""
    registros: dict[tuple[str, str, str], VariacaoAlimento] = {}
    for r in linhas[1:]:  # first row is the header
        chave = (r.get("D4C", ""), r.get("D1N", ""), r.get("D3C", ""))
        reg = registros.get(chave)
        if reg is None:
            reg = VariacaoAlimento(
                codigo=chave[0],
                item=ITENS.get(chave[0], r.get("D4N", "").split(".", 1)[-1]),
                localidade=chave[1],
                localidade_codigo=r.get("D1C", ""),
                mes=r.get("D3N", ""),
                mes_codigo=chave[2],
            )
            registros[chave] = reg
        if r.get("D2C") == VAR_MENSAL:
            reg.variacao_mes = _num(r.get("V"))
        elif r.get("D2C") == VAR_12_MESES:
            reg.variacao_12m = _num(r.get("V"))
    return list(registros.values())


@ttl_cache(ttl=6 * 3600)
async def variacoes(
    localidades: tuple[str, ...] = ("brasil",), meses: int = 1, itens: tuple[str, ...] = ()
) -> list[VariacaoAlimento]:
    """Fetch monthly and 12-month IPCA changes for food items (cached 6h; IPCA is monthly)."""
    local = "/".join(LOCALIDADES[loc][0] for loc in localidades)
    url = SIDRA_URL.format(local=local, meses=meses, itens=",".join(itens or tuple(ITENS)))
    data = await http_get(url, timeout=60)
    return parse_sidra(data if isinstance(data, list) else [])
