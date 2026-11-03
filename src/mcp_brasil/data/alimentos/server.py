"""Alimentos feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import historico_alimento, inflacao_alimentos

mcp = FastMCP("mcp-brasil-alimentos")

mcp.tool(inflacao_alimentos, tags={"alimentos", "precos", "inflacao", "ipca", "cesta"})
mcp.tool(historico_alimento, tags={"alimentos", "precos", "historico"})
