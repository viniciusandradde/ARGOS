"""Tool functions for the Alimentos feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from fastmcp import Context

from mcp_brasil._shared.formatting import markdown_table

from . import client
from .constants import ITENS, LOCALIDADES


def codigo_sidra(localidade: str) -> str:
    """SIDRA territorial code (D1C) for a locality key: 'brasil' → '1'."""
    nivel = LOCALIDADES[localidade][0].split("/")[1]
    return "1" if nivel == "all" else nivel


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    seta = "🔺" if v >= 3 else "🔻" if v <= -3 else ""
    return f"{v:+.2f}% {seta}".strip()


async def inflacao_alimentos(
    ctx: Context, localidade: str = "brasil", comparar_com: str | None = None
) -> str:
    """Variação de preços dos principais alimentos no último IPCA (mês e 12 meses).

    Args:
        localidade: brasil, campo_grande, sao_paulo, rio_de_janeiro, belo_horizonte, curitiba,
                    porto_alegre, goiania, brasilia, salvador, recife, fortaleza, belem,
                    vitoria, sao_luis, aracaju, rio_branco.
                    (Dourados/MS não é pesquisado pelo IBGE — use campo_grande.)
        comparar_com: Segunda localidade para comparação lado a lado (ex: 'brasil').
    """
    locais = [localidade] + ([comparar_com] if comparar_com else [])
    invalidas = [loc for loc in locais if loc not in LOCALIDADES]
    if invalidas:
        return f"Localidade inválida: {', '.join(invalidas)}. Opções: {', '.join(LOCALIDADES)}"
    await ctx.info(f"Consultando IPCA de alimentos ({', '.join(locais)})...")
    dados = await client.variacoes(tuple(locais))
    if not dados:
        return "IBGE não retornou dados agora."
    por_local: dict[str, dict[str, client.VariacaoAlimento]] = {}
    for d in dados:
        por_local.setdefault(d.localidade_codigo, {})[d.codigo] = d
    headers = ["Item"]
    for loc in locais:
        nome = LOCALIDADES[loc][1].split(" (")[0]
        headers += [f"{nome} mês", f"{nome} 12m"]
    rows = []
    for codigo, item in ITENS.items():
        linha: list[str] = [item]
        for loc in locais:
            reg = por_local.get(codigo_sidra(loc), {}).get(codigo)
            linha += [
                _pct(reg.variacao_mes if reg else None),
                _pct(reg.variacao_12m if reg else None),
            ]
        rows.append(linha)
    mes = dados[0].mes
    destaques = sorted(
        (d for d in dados if d.variacao_mes is not None and d.codigo not in ("7170", "7171")),
        key=lambda d: d.variacao_mes or 0,
        reverse=True,
    )[:3]
    texto = [
        f"## 🛒 Inflação dos alimentos — IPCA {mes}",
        markdown_table(headers, rows),
    ]
    if destaques:
        texto.append(
            "\nMaiores altas no mês: "
            + ", ".join(f"{d.item} ({d.localidade}: {d.variacao_mes:+.2f}%)" for d in destaques)
        )
    texto.append("\nFonte: IBGE/SIDRA, tabela 7060 (IPCA).")
    return "\n".join(texto)


async def historico_alimento(
    item: str, ctx: Context, localidade: str = "brasil", meses: int = 12
) -> str:
    """Histórico mensal da variação de preço de um alimento no IPCA.

    Args:
        item: Nome do item (ex: 'Tomate', 'Arroz', 'Carnes', 'Café moído').
        localidade: Localidade do IPCA (ver inflacao_alimentos).
        meses: Quantidade de meses (até 24).
    """
    codigo = next((c for c, n in ITENS.items() if n.casefold() == item.casefold()), None)
    if codigo is None:
        return f"Item '{item}' não monitorado. Opções: {', '.join(ITENS.values())}"
    if localidade not in LOCALIDADES:
        return f"Localidade inválida. Opções: {', '.join(LOCALIDADES)}"
    await ctx.info(f"Histórico de {item}...")
    dados = await client.variacoes((localidade,), min(max(meses, 1), 24), (codigo,))
    dados.sort(key=lambda d: d.mes_codigo)
    rows = [[d.mes, _pct(d.variacao_mes), _pct(d.variacao_12m)] for d in dados]
    return f"## {item} — {LOCALIDADES[localidade][1]}\n\n" + markdown_table(
        ["Mês", "Variação no mês", "Acumulado 12m"], rows
    )
