"""Mundo feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import cotacoes_moedas, historico_cambio, indicador_banco_mundial

mcp = FastMCP("mcp-brasil-mundo")

mcp.tool(cotacoes_moedas, tags={"mundo", "cambio", "moedas"})
mcp.tool(historico_cambio, tags={"mundo", "cambio", "historico"})
mcp.tool(indicador_banco_mundial, tags={"mundo", "banco-mundial", "indicadores"})
