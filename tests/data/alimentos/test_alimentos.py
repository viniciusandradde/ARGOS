"""Tests for the Alimentos feature (SIDRA parsing and tools)."""

from unittest.mock import AsyncMock

import pytest

from mcp_brasil.data.alimentos import client, tools

HEADER = {"D1C": "", "D1N": "", "D2C": "", "D3C": "", "D3N": "", "D4C": "", "D4N": "", "V": ""}


def _row(local: str, nome: str, var: str, item: str, v: str) -> dict[str, str]:
    return {
        "D1C": local,
        "D1N": nome,
        "D2C": var,
        "D3C": "202609",
        "D3N": "setembro 2026",
        "D4C": item,
        "D4N": f"1103028.{item}",
        "V": v,
    }


LINHAS = [
    HEADER,
    _row("1", "Brasil", "63", "7212", "37.76"),
    _row("1", "Brasil", "2265", "7212", "39.55"),
    _row("5002704", "Campo Grande", "63", "7212", "38.89"),
    _row("5002704", "Campo Grande", "2265", "7212", "-"),
]


def test_parse_sidra_merges_variables() -> None:
    regs = {r.localidade_codigo: r for r in client.parse_sidra(LINHAS)}
    assert regs["1"].item == "Tomate"
    assert (regs["1"].variacao_mes, regs["1"].variacao_12m) == (37.76, 39.55)
    assert regs["5002704"].variacao_12m is None


async def test_inflacao_compara_localidades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mcp_brasil.data.alimentos.tools.client.variacoes",
        AsyncMock(return_value=client.parse_sidra(LINHAS)),
    )
    out = await tools.inflacao_alimentos(AsyncMock(), "campo_grande", "brasil")
    linha = next(ln for ln in out.splitlines() if ln.startswith("| Tomate"))
    assert linha == "| Tomate | +38.89% 🔺 | — | +37.76% 🔺 | +39.55% 🔺 |"


async def test_validacoes() -> None:
    assert "inválida" in await tools.inflacao_alimentos(AsyncMock(), "dourados")
    assert "não monitorado" in await tools.historico_alimento("Caviar", AsyncMock())


def test_codigo_sidra() -> None:
    assert tools.codigo_sidra("brasil") == "1"
    assert tools.codigo_sidra("campo_grande") == "5002704"
