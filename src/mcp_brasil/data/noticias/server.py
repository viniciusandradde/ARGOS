"""Notícias feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import alertas_criticos, buscar_noticias, listar_fontes, ultimas_noticias

mcp = FastMCP("mcp-brasil-noticias")

mcp.tool(listar_fontes, tags={"noticias", "fontes"})
mcp.tool(ultimas_noticias, tags={"noticias", "rss", "ultimas"})
mcp.tool(buscar_noticias, tags={"noticias", "rss", "busca", "monitoramento", "internacional"})
mcp.tool(alertas_criticos, tags={"noticias", "alertas", "criticos", "monitoramento"})
