"""Tests for the SICONFI tool functions."""

from unittest.mock import AsyncMock

import pytest

from mcp_brasil.data.siconfi import tools
from mcp_brasil.data.siconfi.schemas import Ente, Entrega, LinhaDemonstrativo


def _ctx() -> AsyncMock:
    return AsyncMock()


def _linha(coluna: str, valor: float) -> LinhaDemonstrativo:
    return LinhaDemonstrativo(
        instituicao="Governo do Estado de São Paulo",
        coluna=coluna,
        conta="RECEITAS CORRENTES",
        valor=valor,
    )


class TestBuscarEnte:
    async def test_requires_filter(self) -> None:
        assert "Informe" in await tools.buscar_ente(_ctx())

    async def test_formats_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.siconfi.tools.client.buscar_entes",
            AsyncMock(return_value=[Ente(cod_ibge=3509502, ente="Campinas", uf="SP")]),
        )
        result = await tools.buscar_ente(_ctx(), nome="Campinas")
        assert "3509502" in result


class TestConsultarRreo:
    async def test_filters_column_and_formats_brl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.siconfi.tools.client.consultar_rreo",
            AsyncMock(return_value=[_linha("ATÉ O BIMESTRE", 1500.0), _linha("PREVISÃO", 9.0)]),
        )
        result = await tools.consultar_rreo(35, 2024, 6, _ctx(), coluna="até o bimestre")
        assert "R$ 1.500,00" in result
        assert "PREVISÃO |" not in result

    async def test_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.siconfi.tools.client.consultar_rreo", AsyncMock(return_value=[])
        )
        assert "Nenhum dado" in await tools.consultar_rreo(35, 2024, 6, _ctx())

    async def test_truncates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.siconfi.tools.client.consultar_rreo",
            AsyncMock(return_value=[_linha(f"C{i}", float(i)) for i in range(10)]),
        )
        result = await tools.consultar_rreo(35, 2024, 6, _ctx(), max_linhas=3)
        assert "Mostrando 3 de 10" in result


class TestExtrato:
    async def test_sorted_by_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "mcp_brasil.data.siconfi.tools.client.extrato_entregas",
            AsyncMock(
                return_value=[
                    Entrega(entregavel="RREO", data_status="2025-01-01T00:00:00Z"),
                    Entrega(entregavel="RGF", data_status="2025-06-01T00:00:00Z"),
                ]
            ),
        )
        result = await tools.extrato_entregas(35, 2025, _ctx())
        assert result.index("RGF") < result.index("RREO")
