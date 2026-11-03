"""Tool functions for the Notícias feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from fastmcp import Context

from . import client
from .constants import CATEGORIAS, DEFAULT_LIMITE, ESCOPOS, FONTES, MAX_LIMITE, NIVEIS
from .filtros import Filtro, aplicar, normalizar
from .schemas import Noticia

_ICONE = {"critico": "🔴", "alto": "🟠", "normal": "⚪"}


def _formatar(noticias: list[Noticia], falhas: list[str]) -> str:
    linhas: list[str] = []
    for n in noticias:
        data = n.publicado_em.strftime("%d/%m/%Y %H:%M") if n.publicado_em else "s/ data"
        icone = _ICONE.get(n.nivel, "")
        linhas.append(f"- {icone} **{n.titulo}** — {FONTES[n.fonte].nome}, {data}\n  {n.link}")
        if n.resumo:
            linhas.append(f"  _{n.resumo[:200]}_")
    if falhas:
        linhas.append(f"\n⚠️ Fontes indisponíveis agora: {', '.join(falhas)}")
    return "\n".join(linhas)


async def listar_fontes(escopo: str | None = None) -> str:
    """Lista as fontes de notícias (Brasil e internacionais), categorias e idiomas.

    Args:
        escopo: 'brasil' ou 'mundo' para filtrar a lista.
    """
    linhas = ["| ID | Fonte | Categoria | Escopo | Idioma |", "| --- | --- | --- | --- | --- |"]
    linhas += [
        f"| `{fid}` | {f.nome} | {f.categoria} | {f.escopo} | {f.idioma} |"
        for fid, f in FONTES.items()
        if not escopo or f.escopo == escopo
    ]
    linhas.append(f"\nCategorias: {', '.join(CATEGORIAS)}")
    return "\n".join(linhas)


async def ultimas_noticias(
    ctx: Context, fonte: str = "agencia_brasil", limite: int = DEFAULT_LIMITE
) -> str:
    """Retorna as últimas notícias de uma fonte.

    Args:
        fonte: ID da fonte (use noticias_listar_fontes). Padrão: 'agencia_brasil'.
        limite: Quantidade de notícias (máx. 50).
    """
    if fonte not in FONTES:
        return f"Fonte '{fonte}' desconhecida. Opções: {', '.join(FONTES)}"
    await ctx.info(f"Lendo feed {FONTES[fonte].nome}...")
    noticias, falhas = await client.buscar_varios([fonte])
    if not noticias:
        return "Nenhuma notícia retornada." + (" (fonte indisponível)" if falhas else "")
    return f"## {FONTES[fonte].nome}\n\n" + _formatar(noticias[: min(limite, MAX_LIMITE)], falhas)


async def buscar_noticias(
    ctx: Context,
    termo: str | None = None,
    categoria: str | None = None,
    fontes: list[str] | None = None,
    escopo: str = "todos",
    idioma: str = "todos",
    nivel_minimo: str = "normal",
    excluir: list[str] | None = None,
    limite: int = 20,
) -> str:
    """Busca notícias no Brasil e no mundo, com filtros, em várias fontes ao mesmo tempo.

    Lê os feeds em paralelo, filtra pelo termo (no título ou resumo, sem
    diferenciar acentos/maiúsculas) e ordena da mais recente para a mais antiga.
    Cada notícia recebe um nível de criticidade (🔴 crítico, 🟠 alto, ⚪ normal).

    Args:
        termo: Palavra ou expressão (ex: 'dengue', 'outbreak', 'reforma tributária').
               Para fontes internacionais, use também o termo em inglês.
        categoria: geral, politica, economia, saude, epidemias, clima, desastres,
                   justica, legislativo, governo.
        fontes: IDs de fontes específicas (sobrepõe categoria/escopo/idioma).
        escopo: 'brasil', 'mundo' ou 'todos'.
        idioma: 'pt', 'en' ou 'todos'.
        nivel_minimo: 'normal', 'alto' ou 'critico'.
        excluir: Termos que descartam a notícia (ex: ['futebol', 'novela']).
        limite: Máximo de resultados (máx. 50).
    """
    if fontes and (invalidas := [f for f in fontes if f not in FONTES]):
        return f"Fontes desconhecidas: {', '.join(invalidas)}"
    if categoria and categoria not in CATEGORIAS:
        return f"Categoria '{categoria}' inválida. Opções: {', '.join(CATEGORIAS)}"
    if escopo not in (*ESCOPOS, "todos"):
        return "Escopo inválido. Use 'brasil', 'mundo' ou 'todos'."
    if nivel_minimo not in NIVEIS:
        return f"Nível inválido. Opções: {', '.join(NIVEIS)}"

    filtro = Filtro(
        termos=[termo] if termo else [],
        excluir=excluir or [],
        categorias=[categoria] if categoria else [],
        fontes=fontes or [],
        escopo=escopo,
        idioma=idioma,
        nivel_minimo=nivel_minimo,
    )
    ids = filtro.fontes_alvo()
    if not ids:
        return "Nenhuma fonte atende a esses filtros."

    await ctx.info(f"Lendo {len(ids)} feeds...")
    noticias, falhas = await client.buscar_varios(ids)
    unicas = aplicar(noticias, filtro)

    if not unicas:
        filtro_txt = f" para '{termo}'" if termo else ""
        return f"Nenhuma notícia encontrada{filtro_txt}." + (
            f" Fontes indisponíveis: {', '.join(falhas)}" if falhas else ""
        )
    cabecalho = f"## {len(unicas)} notícia(s)" + (f" sobre '{termo}'" if termo else "")
    return cabecalho + "\n\n" + _formatar(unicas[: min(limite, MAX_LIMITE)], falhas)


async def alertas_criticos(ctx: Context, escopo: str = "todos", limite: int = 20) -> str:
    """Lista só as notícias classificadas como CRÍTICAS (surtos, pandemias, desastres,
    terremotos, enchentes, guerras, emergências) no Brasil e no mundo.

    Args:
        escopo: 'brasil', 'mundo' ou 'todos'.
        limite: Máximo de resultados (máx. 50).
    """
    return await buscar_noticias(ctx, escopo=escopo, nivel_minimo="critico", limite=limite)


__all__ = [
    "alertas_criticos",
    "buscar_noticias",
    "listar_fontes",
    "normalizar",
    "ultimas_noticias",
]
