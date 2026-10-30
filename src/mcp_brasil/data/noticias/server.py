"""Notícias feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import buscar_noticias, listar_fontes, ultimas_noticias

mcp = FastMCP("mcp-brasil-noticias")

mcp.tool(listar_fontes, tags={"noticias", "fontes"})
mcp.tool(ultimas_noticias, tags={"noticias", "rss", "ultimas"})
mcp.tool(buscar_noticias, tags={"noticias", "rss", "busca", "monitoramento"})
