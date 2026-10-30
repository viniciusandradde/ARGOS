"""LexML feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import buscar_normas, buscar_por_urn, listar_tipos_documento

mcp = FastMCP("mcp-brasil-lexml")

mcp.tool(buscar_normas, tags={"lexml", "legislacao", "busca", "monitoramento"})
mcp.tool(buscar_por_urn, tags={"lexml", "legislacao", "urn"})
mcp.tool(listar_tipos_documento, tags={"lexml", "legislacao", "referencia"})
