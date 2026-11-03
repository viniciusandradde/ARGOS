"""Clients for the Vigilância feature — reuses the InfoDengue and news clients."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from mcp_brasil.data.noticias import client as noticias_client
from mcp_brasil.data.noticias.filtros import Filtro, aplicar
from mcp_brasil.data.noticias.schemas import Noticia
from mcp_brasil.data.saude import client as saude_client

from .constants import TERMOS_SURTO


class ResumoArbovirose(BaseModel):
    doenca: str
    semana: int | None = None
    nivel: int | None = None
    casos_semana: int = 0
    casos_ano: int = 0
    incidencia_100k: float = 0.0
    rt: float | None = None


def localizar_municipio(cidade: str, uf: str | None = None) -> tuple[str, str] | None:
    """Return (geocode, 'Nome/UF') using the bundled IBGE table (no HTTP)."""
    achados = saude_client.buscar_municipio_geocodigo(cidade, uf)
    if not achados:
        return None
    m = achados[0]
    return str(m.geocodigo), f"{m.nome}/{m.uf}"


async def resumo_arbovirose(
    geocodigo: str, doenca: str, ano: int | None = None
) -> ResumoArbovirose:
    """Summarize the current year for one disease in one municipality."""
    ano = ano or date.today().year
    alertas = await saude_client.buscar_alertas_dengue(
        geocodigo=geocodigo, doenca=doenca, ew_start=1, ew_end=53, ey_start=ano, ey_end=ano
    )
    if not alertas:
        return ResumoArbovirose(doenca=doenca)
    alertas.sort(key=lambda a: a.semana_epidemiologica or 0)
    ultimo = alertas[-1]
    return ResumoArbovirose(
        doenca=doenca,
        semana=ultimo.semana_epidemiologica,
        nivel=ultimo.nivel,
        casos_semana=int(ultimo.casos_notificados or 0),
        casos_ano=sum(int(a.casos_notificados or 0) for a in alertas),
        incidencia_100k=round(float(ultimo.incidencia_100k or 0), 1),
        rt=round(float(ultimo.rt), 2) if ultimo.rt is not None else None,
    )


async def noticias_surtos(escopo: str = "todos") -> tuple[list[Noticia], list[str]]:
    """Health/epidemic news mentioning outbreak terms, newest first."""
    filtro = Filtro(
        termos=TERMOS_SURTO, categorias=["saude", "epidemias"], escopo=escopo, nivel_minimo="alto"
    )
    noticias, falhas = await noticias_client.buscar_varios(filtro.fontes_alvo())
    return aplicar(noticias, filtro), falhas
