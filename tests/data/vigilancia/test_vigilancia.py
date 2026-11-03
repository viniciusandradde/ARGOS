"""Tests for the Vigilância feature."""

from unittest.mock import AsyncMock

import pytest

from mcp_brasil.data.noticias.schemas import Noticia
from mcp_brasil.data.saude.schemas import AlertaDengue
from mcp_brasil.data.vigilancia import client, tools


async def test_resumo_soma_casos(monkeypatch: pytest.MonkeyPatch) -> None:
    alertas = [
        AlertaDengue(semana_epidemiologica=202641, casos_notificados=10, nivel=2, rt=1.1),
        AlertaDengue(
            semana_epidemiologica=202642,
            casos_notificados=35,
            nivel=4,
            rt=1.48,
            incidencia_100k=28.4,
        ),
    ]
    monkeypatch.setattr(
        "mcp_brasil.data.vigilancia.client.saude_client.buscar_alertas_dengue",
        AsyncMock(return_value=list(reversed(alertas))),
    )
    r = await client.resumo_arbovirose("5003702", "chikungunya", 2026)
    assert (r.semana, r.nivel, r.casos_semana, r.casos_ano, r.rt) == (202642, 4, 35, 45, 1.48)


async def test_painel_destaca_alerta(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(geo: str, doenca: str, ano: int | None = None) -> client.ResumoArbovirose:
        nivel = 4 if doenca == "chikungunya" else 1
        return client.ResumoArbovirose(doenca=doenca, semana=202642, nivel=nivel, casos_ano=9)

    monkeypatch.setattr("mcp_brasil.data.vigilancia.tools.client.resumo_arbovirose", fake)
    out = await tools.painel_arboviroses("Dourados", AsyncMock(), "MS")
    assert "Dourados/MS" in out and "🔴 vermelho" in out and "⚠️ chikungunya" in out


async def test_painel_municipio_inexistente() -> None:
    assert "não encontrado" in await tools.painel_arboviroses("Cidade Inexistente", AsyncMock())


async def test_radar_surtos(monkeypatch: pytest.MonkeyPatch) -> None:
    n = Noticia(fonte="ecdc", titulo="Ebola cases emerge in Kenya", link="x", nivel="critico")
    monkeypatch.setattr(
        "mcp_brasil.data.vigilancia.tools.client.noticias_surtos",
        AsyncMock(return_value=([n], ["oms"])),
    )
    out = await tools.radar_surtos(AsyncMock())
    assert "🔴 **Ebola" in out and "indisponíveis: oms" in out
