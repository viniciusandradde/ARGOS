"""Tool functions for the Mundo feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from datetime import date, timedelta

from fastmcp import Context

from mcp_brasil._shared.formatting import format_number_br, markdown_table

from . import client
from .constants import INDICADORES


async def cotacoes_moedas(
    ctx: Context, base: str = "USD", moedas: str = "BRL,EUR,CNY,ARS,GBP,JPY"
) -> str:
    """Cotações de referência de moedas (Banco Central Europeu, via Frankfurter, sem chave).

    Args:
        base: Moeda base (ex: 'USD', 'EUR', 'BRL').
        moedas: Moedas de destino separadas por vírgula.
    """
    await ctx.info(f"Cotações base {base}...")
    d = await client.cotacoes(base, moedas)
    rows = [[m, format_number_br(v, 4)] for m, v in sorted(d.get("rates", {}).items())]
    return f"## 💱 1 {d.get('base')} em {d.get('date')}\n\n" + markdown_table(
        ["Moeda", "Valor"], rows
    )


async def historico_cambio(
    ctx: Context, base: str = "USD", moeda: str = "BRL", dias: int = 30
) -> str:
    """Histórico diário de câmbio com variação no período.

    Args:
        base: Moeda base (ex: 'USD').
        moeda: Moeda de destino (ex: 'BRL').
        dias: Janela em dias (até 365).
    """
    inicio = (date.today() - timedelta(days=min(max(dias, 2), 365))).isoformat()
    await ctx.info(f"Histórico {base}/{moeda} desde {inicio}...")
    d = await client.historico(base, moeda, inicio)
    serie = [(dia, v.get(moeda.upper())) for dia, v in sorted(d.get("rates", {}).items())]
    serie = [(dia, v) for dia, v in serie if v is not None]
    if len(serie) < 2:
        return "Sem dados suficientes no período."
    primeiro, ultimo = serie[0][1], serie[-1][1]
    var = (ultimo / primeiro - 1) * 100
    maximo = max(serie, key=lambda x: x[1])
    minimo = min(serie, key=lambda x: x[1])
    return (
        f"## {base.upper()}/{moeda.upper()} — últimos {dias} dias\n"
        f"Atual: **{ultimo:.4f}** ({var:+.2f}% no período) | "
        f"Máx: {maximo[1]:.4f} em {maximo[0]} | Mín: {minimo[1]:.4f} em {minimo[0]}"
    )


async def indicador_banco_mundial(
    indicador: str, ctx: Context, pais: str = "BR", anos: int = 10
) -> str:
    """Série anual de um indicador do Banco Mundial para um país.

    Args:
        indicador: pib, pib_crescimento, pib_per_capita, inflacao,
                   desemprego, gasto_saude, expectativa_vida, populacao, divida_publica.
        pais: Código ISO do país (ex: 'BR', 'AR', 'US', 'CN', 'WLD' para o mundo).
        anos: Quantidade de anos.
    """
    if indicador not in INDICADORES:
        return f"Indicador inválido. Opções: {', '.join(INDICADORES)}"
    codigo, nome = INDICADORES[indicador]
    await ctx.info(f"Banco Mundial: {nome} ({pais})...")
    serie = await client.indicador(codigo, pais.upper(), anos)
    if not serie:
        return f"Sem dados de {nome} para {pais}."
    pais_nome = serie[0].get("country", {}).get("value", pais)
    rows = [[d["date"], format_number_br(float(d["value"]), 2)] for d in serie]
    return f"## 🌐 {nome} — {pais_nome}\n\n" + markdown_table(["Ano", "Valor"], rows)
