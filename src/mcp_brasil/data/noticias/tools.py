"""Tool functions for the Notícias feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

import unicodedata

from fastmcp import Context

from . import client
from .constants import CATEGORIAS, DEFAULT_LIMITE, FONTES, MAX_LIMITE
from .schemas import Noticia


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def _formatar(noticias: list[Noticia], falhas: list[str]) -> str:
    linhas: list[str] = []
    for n in noticias:
        data = n.publicado_em.strftime("%d/%m/%Y %H:%M") if n.publicado_em else "s/ data"
        linhas.append(f"- **{n.titulo}** — {FONTES[n.fonte].nome}, {data}\n  {n.link}")
        if n.resumo:
            linhas.append(f"  _{n.resumo[:200]}_")
    if falhas:
        linhas.append(f"\n⚠️ Fontes indisponíveis agora: {', '.join(falhas)}")
    return "\n".join(linhas)


async def listar_fontes() -> str:
    """Lista as fontes de notícias oficiais disponíveis e suas categorias."""
    linhas = ["| ID | Fonte | Categoria |", "| --- | --- | --- |"]
    linhas += [f"| `{fid}` | {f.nome} | {f.categoria} |" for fid, f in FONTES.items()]
    linhas.append(f"\nCategorias: {', '.join(CATEGORIAS)}")
    return "\n".join(linhas)


async def ultimas_noticias(
    ctx: Context, fonte: str = "agencia_brasil", limite: int = DEFAULT_LIMITE
) -> str:
    """Retorna as últimas notícias de uma fonte oficial.

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
    limite: int = 20,
) -> str:
    """Busca notícias oficiais por palavra-chave em várias fontes ao mesmo tempo.

    Lê os feeds em paralelo, filtra pelo termo (no título ou resumo, sem
    diferenciar acentos/maiúsculas) e ordena da mais recente para a mais antiga.

    Args:
        termo: Palavra ou expressão (ex: 'imposto de renda', 'dengue', 'reforma tributária').
               Se vazio, retorna as mais recentes.
        categoria: Filtra fontes por categoria (geral, politica, economia, saude,
                   justica, legislativo, governo).
        fontes: Lista de IDs de fontes específicas (sobrepõe `categoria`).
        limite: Máximo de resultados (máx. 50).
    """
    if fontes:
        invalidas = [f for f in fontes if f not in FONTES]
        if invalidas:
            return f"Fontes desconhecidas: {', '.join(invalidas)}"
        ids = fontes
    elif categoria:
        ids = [fid for fid, f in FONTES.items() if f.categoria == categoria]
        if not ids:
            return f"Categoria '{categoria}' inválida. Opções: {', '.join(CATEGORIAS)}"
    else:
        ids = list(FONTES)

    await ctx.info(f"Lendo {len(ids)} feeds oficiais...")
    noticias, falhas = await client.buscar_varios(ids)

    if termo:
        alvo = _normalizar(termo)
        noticias = [n for n in noticias if alvo in _normalizar(f"{n.titulo} {n.resumo}")]

    # Same story is often syndicated by more than one feed
    vistos: set[str] = set()
    unicas = []
    for n in noticias:
        if n.link not in vistos:
            vistos.add(n.link)
            unicas.append(n)

    if not unicas:
        filtro = f" para '{termo}'" if termo else ""
        return f"Nenhuma notícia encontrada{filtro}." + (
            f" Fontes indisponíveis: {', '.join(falhas)}" if falhas else ""
        )
    cabecalho = f"## {len(unicas)} notícia(s)" + (f" sobre '{termo}'" if termo else "")
    return cabecalho + "\n\n" + _formatar(unicas[: min(limite, MAX_LIMITE)], falhas)
