"""Tests for the Notícias tool functions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from mcp_brasil.data.noticias import tools
from mcp_brasil.data.noticias.schemas import Noticia


def _n(titulo: str, link: str, fonte: str = "agencia_brasil") -> Noticia:
    return Noticia(
        fonte=fonte,
        titulo=titulo,
        link=link,
        publicado_em=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_varios(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(
        return_value=(
            [
                _n("Reforma tributária avança", "https://a/1"),
                _n("Reforma tributária avança", "https://a/1", "agencia_brasil_economia"),
                _n("Dengue: alerta em SP", "https://a/2"),
            ],
            ["ans"],
        )
    )
    monkeypatch.setattr("mcp_brasil.data.noticias.tools.client.buscar_varios", mock)
    return mock


class TestBuscarNoticias:
    async def test_accent_insensitive_and_dedup(self, mock_varios: AsyncMock) -> None:
        result = await tools.buscar_noticias(AsyncMock(), termo="TRIBUTARIA")
        assert result.startswith("## 1 notícia(s)")
        assert "Dengue" not in result
        assert "indisponíveis agora: ans" in result

    async def test_category_selects_feeds(self, mock_varios: AsyncMock) -> None:
        await tools.buscar_noticias(AsyncMock(), categoria="saude")
        ids = mock_varios.call_args.args[0]
        assert ids and all("saude" in i or i == "ans" for i in ids)

    async def test_invalid_category(self, mock_varios: AsyncMock) -> None:
        assert "inválida" in await tools.buscar_noticias(AsyncMock(), categoria="esportes")

    async def test_invalid_source(self, mock_varios: AsyncMock) -> None:
        assert "desconhecidas" in await tools.buscar_noticias(AsyncMock(), fontes=["xyz"])


class TestUltimasNoticias:
    async def test_unknown_source(self) -> None:
        assert "desconhecida" in await tools.ultimas_noticias(AsyncMock(), fonte="xyz")

    async def test_lists(self, mock_varios: AsyncMock) -> None:
        result = await tools.ultimas_noticias(AsyncMock(), limite=1)
        assert "Reforma" in result and "Dengue" not in result


async def test_listar_fontes() -> None:
    assert "`senado`" in await tools.listar_fontes()
