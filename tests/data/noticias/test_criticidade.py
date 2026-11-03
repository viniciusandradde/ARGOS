"""Tests for keyword-based criticality and shared filters."""

import pytest

from mcp_brasil.data.noticias.criticidade import classificar
from mcp_brasil.data.noticias.filtros import Filtro, aplicar
from mcp_brasil.data.noticias.schemas import Noticia


@pytest.mark.parametrize(
    ("texto", "nivel"),
    [
        ("DR Congo: Ebola cases top 10,000", "critico"),
        ("Surto de sarampo no Paraná", "critico"),
        ("Magnitude 6.4 earthquake near Easter Island", "critico"),
        ("Aviso de Tempestade. Severidade Grau: Perigo", "critico"),
        ("Casos de chikungunya crescem em Dourados", "alto"),
        ("Copom mantém a Selic em 15%", "alto"),
        ("El Niño deve se intensificar até março", "alto"),
        ("Museu reabre exposição de arte", "normal"),
        ("Warfarin dosing study", "normal"),  # word boundary: 'war' ≠ 'warfarin'
    ],
)
def test_classificar(texto: str, nivel: str) -> None:
    assert classificar(texto) == nivel


def _n(titulo: str, nivel: str = "normal", link: str | None = None) -> Noticia:
    return Noticia(fonte="oms", titulo=titulo, link=link or titulo, nivel=nivel)


def test_filtro_termos_excluir_nivel() -> None:
    noticias = [
        _n("Dengue em alta", "alto"),
        _n("Dengue e futebol", "alto"),
        _n("Dengue leve"),
        _n("Ebola", "critico"),
    ]
    f = Filtro(termos=["dengue", "ebola"], excluir=["futebol"], nivel_minimo="alto")
    assert [n.titulo for n in aplicar(noticias, f)] == ["Dengue em alta", "Ebola"]


def test_filtro_fontes_alvo() -> None:
    assert Filtro(fontes=["oms", "xyz"]).fontes_alvo() == ["oms"]
    alvo = Filtro(categorias=["epidemias"], escopo="mundo").fontes_alvo()
    assert alvo == ["ecdc"]


def test_filtro_apenas_titulo() -> None:
    n = Noticia(fonte="oms", titulo="Editorial on leadership", link="x", resumo="pandemic risk")
    assert Filtro(termos=["pandemic"]).aceita(n)
    assert not Filtro(termos=["pandemic"], apenas_titulo=True).aceita(n)
