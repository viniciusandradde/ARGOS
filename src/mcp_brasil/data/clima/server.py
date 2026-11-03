"""Clima feature server — registers tools.

This file only registers components. Zero business logic (ADR-001 rule #4).
"""

from fastmcp import FastMCP

from .tools import (
    avisos_inmet,
    el_nino,
    eventos_naturais,
    previsao_tempo,
    qualidade_ar,
    terremotos,
)

mcp = FastMCP("mcp-brasil-clima")

mcp.tool(el_nino, tags={"clima", "el-nino", "la-nina", "enso", "noaa", "monitoramento"})
mcp.tool(previsao_tempo, tags={"clima", "previsao", "tempo"})
mcp.tool(qualidade_ar, tags={"clima", "ar", "poluicao"})
mcp.tool(avisos_inmet, tags={"clima", "inmet", "alertas", "monitoramento"})
mcp.tool(terremotos, tags={"desastres", "terremotos", "usgs"})
mcp.tool(eventos_naturais, tags={"desastres", "nasa", "incendios", "tempestades"})
