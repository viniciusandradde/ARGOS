"""Tool functions for the LexML feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from fastmcp import Context

from . import client
from .constants import DEFAULT_MAX_REGISTROS, MAX_REGISTROS, TIPOS_DOCUMENTO


async def buscar_normas(
    termo: str,
    ctx: Context,
    tipo: str | None = None,
    localidade: str | None = None,
    ano: int | None = None,
    max_registros: int = DEFAULT_MAX_REGISTROS,
) -> str:
    """Busca leis, decretos e outras normas no LexML (todas as esferas de governo).

    Procura o termo no título e na ementa. Ideal para monitorar legislação
    sobre um tema (ex: 'reforma tributária', 'telemedicina', 'ICMS').

    Args:
        termo: Palavras-chave (ex: 'proteção de dados pessoais').
        tipo: Tipo de documento: Lei, Lei Complementar, Decreto, Medida Provisória,
              Emenda Constitucional, Resolução, Portaria, Projeto de Lei, Acórdão...
        localidade: 'Brasil' para normas federais, ou nome do estado/município
                    (ex: 'São Paulo', 'Minas Gerais').
        ano: Mantém só normas desse ano.
        max_registros: Máximo de resultados (até 100).
    """
    cql = client.montar_cql(termo, tipo, localidade)
    await ctx.info(f"Consultando LexML: {cql}")
    try:
        resultado = await client.buscar(cql, min(max_registros, MAX_REGISTROS))
    except client.LexmlBloqueadoError as exc:
        return f"⚠️ {exc}"

    normas = resultado.normas
    if ano:
        normas = [n for n in normas if n.data.startswith(str(ano))]
    if not normas:
        return f"Nenhuma norma encontrada para '{termo}'."

    linhas = [f"## {resultado.total} norma(s) no LexML para '{termo}'\n"]
    for n in normas:
        linhas.append(f"### {n.titulo or n.urn}")
        meta = " | ".join(p for p in (n.tipo, n.data, n.localidade, n.autoridade) if p)
        if meta:
            linhas.append(meta)
        if n.ementa:
            linhas.append(f"> {n.ementa[:500]}")
        if n.link:
            linhas.append(n.link)
        linhas.append("")
    if resultado.total > len(resultado.normas):
        linhas.append(
            f"_Mostrando {len(normas)} de {resultado.total}. Refine com `tipo` ou `ano`._"
        )
    return "\n".join(linhas)


async def buscar_por_urn(urn: str, ctx: Context) -> str:
    """Busca uma norma específica pelo identificador URN LexML.

    Args:
        urn: URN da norma (ex: 'urn:lex:br:federal:lei:2018-08-14;13709').
    """
    await ctx.info(f"Buscando URN {urn}...")
    try:
        resultado = await client.buscar(f'urn any "{urn}"', 1)
    except client.LexmlBloqueadoError as exc:
        return f"⚠️ {exc}"
    if not resultado.normas:
        return f"URN '{urn}' não encontrada."
    n = resultado.normas[0]
    return "\n".join(
        p
        for p in (
            f"## {n.titulo}",
            f"**Tipo:** {n.tipo} | **Data:** {n.data} | **Localidade:** {n.localidade}",
            f"**Ementa:** {n.ementa}" if n.ementa else "",
            n.link,
        )
        if p
    )


async def listar_tipos_documento() -> str:
    """Lista os tipos de documento aceitos no filtro `tipo` de lexml_buscar_normas."""
    return "\n".join(f"- {t}" for t in TIPOS_DOCUMENTO)
