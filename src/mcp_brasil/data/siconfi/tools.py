"""Tool functions for the SICONFI feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from fastmcp import Context

from mcp_brasil._shared.formatting import format_brl, markdown_table

from . import client
from .constants import ANEXOS_RGF, ANEXOS_RREO, DEFAULT_MAX_LINHAS, PODERES
from .schemas import LinhaDemonstrativo


def _formatar_linhas(
    titulo: str, linhas: list[LinhaDemonstrativo], coluna: str | None, max_linhas: int
) -> str:
    if coluna:
        alvo = coluna.casefold()
        linhas = [ln for ln in linhas if alvo in (ln.coluna or "").casefold()]
    if not linhas:
        return f"{titulo}\n\nNenhum dado encontrado (relatório não entregue ou filtro vazio)."

    colunas = sorted({ln.coluna or "" for ln in linhas})
    rows = [
        [ln.conta or ln.cod_conta or "", ln.coluna or "", format_brl(ln.valor or 0.0)]
        for ln in linhas[:max_linhas]
    ]
    partes = [
        titulo,
        f"**Instituição:** {linhas[0].instituicao} | **Linhas:** {len(linhas)}",
        f"**Colunas disponíveis:** {', '.join(colunas[:12])}",
        "",
        markdown_table(["Conta", "Coluna", "Valor"], rows),
    ]
    if len(linhas) > max_linhas:
        partes.append(
            f"\n_Mostrando {max_linhas} de {len(linhas)} linhas. "
            "Use o parâmetro `coluna` para filtrar ou aumente `max_linhas`._"
        )
    return "\n".join(partes)


async def buscar_ente(ctx: Context, nome: str | None = None, uf: str | None = None) -> str:
    """Busca o código IBGE de um ente (União, estado ou município) no SICONFI.

    O código é necessário para consultar RREO, RGF e DCA.
    União = 1, estados = 2 dígitos (ex: SP = 35), municípios = 7 dígitos.

    Args:
        nome: Parte do nome do ente (ex: 'Campinas', 'Minas Gerais').
        uf: Sigla do estado para filtrar (ex: 'SP').
    """
    if not nome and not uf:
        return "Informe `nome` e/ou `uf` para buscar."
    await ctx.info(f"Buscando entes SICONFI (nome={nome}, uf={uf})...")
    entes = await client.buscar_entes(nome, uf)
    if not entes:
        return "Nenhum ente encontrado."
    rows = [
        [e.cod_ibge, e.ente, e.uf or "", e.esfera or "", e.populacao or ""] for e in entes[:30]
    ]
    out = markdown_table(["Código IBGE", "Ente", "UF", "Esfera", "População"], rows)
    if len(entes) > 30:
        out += f"\n\n_Mostrando 30 de {len(entes)}. Refine a busca._"
    return out


async def consultar_rreo(
    id_ente: int,
    ano: int,
    bimestre: int,
    ctx: Context,
    anexo: str = "RREO-Anexo 01",
    coluna: str | None = None,
    simplificado: bool = False,
    max_linhas: int = DEFAULT_MAX_LINHAS,
) -> str:
    """Consulta o RREO (Relatório Resumido da Execução Orçamentária) de um ente.

    Mostra receitas arrecadadas, despesas executadas, RCL, resultado primário,
    gastos com saúde etc. Publicado a cada bimestre.

    Anexos comuns: 'RREO-Anexo 01' (balanço orçamentário), 'RREO-Anexo 02'
    (despesa por função), 'RREO-Anexo 03' (RCL), 'RREO-Anexo 06' (resultado
    primário), 'RREO-Anexo 12' (saúde), 'RREO-Anexo 14' (simplificado).

    Args:
        id_ente: Código IBGE do ente (use siconfi_buscar_ente).
        ano: Exercício (ex: 2024).
        bimestre: Bimestre de 1 a 6.
        anexo: Nome do anexo (padrão 'RREO-Anexo 01').
        coluna: Filtra colunas pelo texto (ex: 'ATÉ O BIMESTRE').
        simplificado: True para municípios com menos de 50 mil hab. que entregam RREO simplificado.
        max_linhas: Máximo de linhas na resposta.
    """
    await ctx.info(f"Consultando {anexo} de {id_ente} ({ano}, {bimestre}º bim)...")
    linhas = await client.consultar_rreo(id_ente, ano, bimestre, anexo, simplificado)
    descricao = ANEXOS_RREO.get(anexo, "")
    titulo = f"## {anexo} — {descricao} ({bimestre}º bimestre/{ano})"
    return _formatar_linhas(titulo, linhas, coluna, max_linhas)


async def consultar_rgf(
    id_ente: int,
    ano: int,
    periodo: int,
    ctx: Context,
    anexo: str = "RGF-Anexo 01",
    poder: str = "E",
    periodicidade: str = "Q",
    coluna: str | None = None,
    max_linhas: int = DEFAULT_MAX_LINHAS,
) -> str:
    """Consulta o RGF (Relatório de Gestão Fiscal) — limites da Lei de Responsabilidade Fiscal.

    Mostra despesa com pessoal vs. limite da LRF, dívida consolidada, garantias,
    operações de crédito. Publicado por quadrimestre (ou semestre p/ pequenos municípios).

    Anexos comuns: 'RGF-Anexo 01' (pessoal), 'RGF-Anexo 02' (dívida),
    'RGF-Anexo 06' (simplificado).

    Args:
        id_ente: Código IBGE do ente.
        ano: Exercício (ex: 2024).
        periodo: Quadrimestre (1-3) ou semestre (1-2).
        anexo: Nome do anexo (padrão 'RGF-Anexo 01').
        poder: E (Executivo), L (Legislativo), J (Judiciário), M (Ministério Público).
        periodicidade: Q (quadrimestral) ou S (semestral).
        coluna: Filtra colunas pelo texto.
        max_linhas: Máximo de linhas na resposta.
    """
    poder = poder.upper()
    await ctx.info(f"Consultando {anexo} de {id_ente} ({ano}, período {periodo})...")
    linhas = await client.consultar_rgf(id_ente, ano, periodo, anexo, poder, periodicidade)
    titulo = (
        f"## {anexo} — {ANEXOS_RGF.get(anexo, '')} "
        f"(Poder {PODERES.get(poder, poder)}, {periodo}º {periodicidade}/{ano})"
    )
    return _formatar_linhas(titulo, linhas, coluna, max_linhas)


async def consultar_dca(
    id_ente: int,
    ano: int,
    ctx: Context,
    anexo: str = "DCA-Anexo I-C",
    coluna: str | None = None,
    max_linhas: int = DEFAULT_MAX_LINHAS,
) -> str:
    """Consulta a DCA (Declaração de Contas Anuais) de um ente.

    Anexos: 'DCA-Anexo I-AB' (balanço patrimonial), 'DCA-Anexo I-C' (receitas
    orçamentárias — inclui arrecadação de impostos como IPTU, ISS, ICMS),
    'DCA-Anexo I-D' (despesas por natureza), 'DCA-Anexo I-E' (despesas por função).

    Args:
        id_ente: Código IBGE do ente.
        ano: Exercício (ex: 2023).
        anexo: Nome do anexo (padrão 'DCA-Anexo I-C', receitas).
        coluna: Filtra colunas pelo texto (ex: 'Receitas Realizadas').
        max_linhas: Máximo de linhas na resposta.
    """
    await ctx.info(f"Consultando {anexo} de {id_ente} ({ano})...")
    linhas = await client.consultar_dca(id_ente, ano, anexo)
    return _formatar_linhas(f"## {anexo} ({ano})", linhas, coluna, max_linhas)


async def extrato_entregas(id_ente: int, ano: int, ctx: Context) -> str:
    """Lista quais relatórios fiscais um ente entregou ao Tesouro no ano.

    Útil para monitorar atrasos: mostra RREO, RGF, DCA e MSC entregues,
    com data e situação. Entes inadimplentes ficam impedidos de receber
    transferências voluntárias.

    Args:
        id_ente: Código IBGE do ente.
        ano: Ano de referência.
    """
    await ctx.info(f"Consultando extrato de entregas de {id_ente} ({ano})...")
    entregas = await client.extrato_entregas(id_ente, ano)
    if not entregas:
        return f"Nenhuma entrega registrada para o ente {id_ente} em {ano}."
    entregas.sort(key=lambda e: e.data_status or "", reverse=True)
    rows = [
        [
            (e.data_status or "")[:10],
            e.entregavel or "",
            f"{e.periodo or ''}{e.periodicidade or ''}",
            e.instituicao or "",
            e.status_relatorio or "",
        ]
        for e in entregas[:50]
    ]
    out = f"## Entregas ao SICONFI — {ano} ({len(entregas)} registros)\n\n"
    out += markdown_table(["Data", "Entregável", "Período", "Instituição", "Status"], rows)
    return out
