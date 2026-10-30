"""SICONFI feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import buscar_ente, consultar_dca, consultar_rgf, consultar_rreo, extrato_entregas

mcp = FastMCP("mcp-brasil-siconfi")

mcp.tool(buscar_ente, tags={"siconfi", "entes", "busca"})
mcp.tool(consultar_rreo, tags={"siconfi", "rreo", "orcamento", "receitas", "despesas"})
mcp.tool(consultar_rgf, tags={"siconfi", "rgf", "lrf", "pessoal", "divida"})
mcp.tool(consultar_dca, tags={"siconfi", "dca", "contas-anuais", "impostos"})
mcp.tool(extrato_entregas, tags={"siconfi", "entregas", "monitoramento"})
