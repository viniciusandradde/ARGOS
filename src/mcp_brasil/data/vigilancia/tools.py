"""Tool functions for the Vigilância feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

import asyncio

from fastmcp import Context

from mcp_brasil._shared.formatting import markdown_table
from mcp_brasil.data.noticias.constants import FONTES

from . import client
from .constants import DOENCAS, NIVEIS


async def painel_arboviroses(cidade: str, ctx: Context, uf: str | None = None) -> str:
    """Painel de dengue, chikungunya e zika de um município no ano corrente (InfoDengue).

    Mostra nível de alerta da última semana, casos na semana, total no ano,
    incidência por 100 mil habitantes e Rt (Rt > 1 = transmissão em expansão).

    Args:
        cidade: Nome do município (ex: 'Dourados').
        uf: Sigla do estado para desambiguar (ex: 'MS').
    """
    local = client.localizar_municipio(cidade, uf)
    if local is None:
        return f"Município '{cidade}' não encontrado."
    geocodigo, nome = local
    await ctx.info(f"Consultando InfoDengue para {nome}...")
    resultados = await asyncio.gather(
        *(client.resumo_arbovirose(geocodigo, d) for d in DOENCAS), return_exceptions=True
    )
    rows: list[list[str | int | float]] = []
    alertas = []
    for doenca, r in zip(DOENCAS, resultados, strict=True):
        if isinstance(r, BaseException):
            rows.append([doenca, "indisponível", "", "", "", ""])
            continue
        rows.append(
            [
                doenca,
                NIVEIS.get(r.nivel or 0, "—"),
                r.casos_semana,
                f"{r.casos_ano:,}".replace(",", "."),
                r.incidencia_100k,
                f"{r.rt:.2f}" if r.rt is not None else "—",
            ]
        )
        if (r.nivel or 0) >= 3 or (r.rt or 0) > 1.2:
            alertas.append(f"⚠️ {doenca}: nível {r.nivel}, Rt {r.rt}")
    semana = next(
        (r.semana for r in resultados if not isinstance(r, BaseException) and r.semana), None
    )
    saida = [
        f"## 🦟 Arboviroses — {nome} (semana epidemiológica {semana or '—'})",
        markdown_table(
            ["Doença", "Nível", "Casos na semana", "Casos no ano", "Inc./100 mil", "Rt"], rows
        ),
    ]
    if alertas:
        saida += ["", *alertas]
    saida.append("\nFonte: InfoDengue (Fiocruz/FGV) — https://info.dengue.mat.br")
    return "\n".join(saida)


async def radar_surtos(ctx: Context, escopo: str = "todos", limite: int = 15) -> str:
    """Radar de surtos, epidemias e pandemias: notícias recentes de OMS, ECDC, ONU,
    Agência Brasil e imprensa internacional que citam doenças/surtos.

    Args:
        escopo: 'brasil', 'mundo' ou 'todos'.
        limite: Máximo de notícias.
    """
    await ctx.info("Varrendo fontes de saúde e epidemias...")
    noticias, falhas = await client.noticias_surtos(escopo)
    if not noticias:
        return "Nenhuma notícia de surto encontrada agora."
    linhas = [f"## 🧬 Radar de surtos — {len(noticias)} notícia(s)"]
    for n in noticias[:limite]:
        icone = "🔴" if n.nivel == "critico" else "🟠"
        data = n.publicado_em.strftime("%d/%m %H:%M") if n.publicado_em else ""
        linhas.append(f"- {icone} **{n.titulo}** — {FONTES[n.fonte].nome} {data}\n  {n.link}")
    if falhas:
        linhas.append(f"\nFontes indisponíveis: {', '.join(falhas)}")
    return "\n".join(linhas)
