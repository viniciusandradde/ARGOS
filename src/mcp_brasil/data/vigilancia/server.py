"""Vigilância feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import painel_arboviroses, radar_surtos

mcp = FastMCP("mcp-brasil-vigilancia")

mcp.tool(painel_arboviroses, tags={"vigilancia", "dengue", "zika", "chikungunya", "municipio"})
mcp.tool(radar_surtos, tags={"vigilancia", "surtos", "epidemias", "pandemia", "monitoramento"})
