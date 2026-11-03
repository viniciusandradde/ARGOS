"""Montagem dos dados da sala de situação a partir do banco de indicadores."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp_brasil.data.noticias.constants import CATEGORIAS, ESCOPOS, NIVEIS
from mcp_brasil.data.noticias.filtros import Filtro
from mcp_brasil.data.noticias.schemas import Noticia
from mcp_brasil.data.vigilancia.constants import TERMOS_SURTO

from .indicadores import Indicadores

CAMPOS_NOTICIA = (
    "link, fonte, fonte_nome, categoria, escopo, idioma, titulo, resumo, nivel, publicado_em"
)


def _lista(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [v.strip() for v in valor.split(",") if v.strip()]
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return []


def validar_tema(dados: dict[str, Any]) -> dict[str, Any]:
    """Normalize a topic definition coming from the portal. Raises ValueError."""
    nome = str(dados.get("nome", "")).strip()[:60]
    if not nome:
        raise ValueError("Dê um nome ao tema.")
    config = {
        "termos": _lista(dados.get("termos"))[:30],
        "excluir": _lista(dados.get("excluir"))[:30],
        "categorias": [c for c in _lista(dados.get("categorias")) if c in CATEGORIAS],
        "escopo": dados.get("escopo") if dados.get("escopo") in ESCOPOS else "todos",
        "nivel_minimo": (
            dados.get("nivel_minimo") if dados.get("nivel_minimo") in NIVEIS else "normal"
        ),
    }
    if not config["termos"] and not config["categorias"]:
        raise ValueError("Informe ao menos um termo ou uma categoria.")
    return {"nome": nome, **config}


def filtro_do_tema(tema: dict[str, Any]) -> Filtro:
    return Filtro(
        termos=tema.get("termos", []),
        excluir=tema.get("excluir", []),
        categorias=tema.get("categorias", []),
        escopo=tema.get("escopo", "todos"),
        nivel_minimo=tema.get("nivel_minimo", "normal"),
    )


def filtrar(linhas: list[dict[str, Any]], filtro: Filtro, limite: int) -> list[dict[str, Any]]:
    fontes = set(filtro.fontes_alvo())
    saida = []
    for r in linhas:
        if r["fonte"] not in fontes:
            continue
        n = Noticia(
            fonte=r["fonte"], titulo=r["titulo"], link=r["link"], resumo=r["resumo"],
            nivel=r["nivel"],
        )  # fmt: skip
        if filtro.aceita(n):
            saida.append(r)
            if len(saida) >= limite:
                break
    return saida


def montar(
    ind: Indicadores,
    *,
    temas: list[dict[str, Any]],
    area_inmet: str,
    cidade_precos: str,
    feed_filtro: Filtro | None = None,
) -> dict[str, Any]:
    desde = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recentes = ind.consultar(
        f"SELECT {CAMPOS_NOTICIA} FROM noticias WHERE publicado_em >= ? "
        "ORDER BY publicado_em DESC LIMIT 3000",
        (desde,),
    )

    coletas = {
        r["etapa"]: r
        for r in ind.consultar(
            "SELECT etapa, ok, mensagem, quando FROM coletas WHERE id IN "
            "(SELECT MAX(id) FROM coletas GROUP BY etapa)"
        )
    }

    enso_status = ind.consultar("SELECT alerta, fase, sinopse, atualizado_em FROM enso_status")
    oni = ind.consultar(
        "SELECT ano, trimestre, oni, roni FROM enso_oni ORDER BY ano, "
        "CASE trimestre WHEN 'DJF' THEN 1 WHEN 'JFM' THEN 2 WHEN 'FMA' THEN 3 WHEN 'MAM' THEN 4 "
        "WHEN 'AMJ' THEN 5 WHEN 'MJJ' THEN 6 WHEN 'JJA' THEN 7 WHEN 'JAS' THEN 8 "
        "WHEN 'ASO' THEN 9 WHEN 'SON' THEN 10 WHEN 'OND' THEN 11 ELSE 12 END"
    )
    semanal = ind.consultar("SELECT * FROM enso_semanal ORDER BY data DESC LIMIT 8")

    arbo = ind.consultar(
        "SELECT a.* FROM arboviroses a JOIN (SELECT geocodigo, doenca, MAX(semana) s "
        "FROM arboviroses GROUP BY geocodigo, doenca) m ON a.geocodigo = m.geocodigo "
        "AND a.doenca = m.doenca AND a.semana = m.s ORDER BY a.municipio, a.doenca"
    )

    clima = []
    for atual in ind.consultar("SELECT * FROM clima_atual ORDER BY cidade"):
        previsao = ind.consultar(
            "SELECT * FROM clima_previsao WHERE cidade = ? AND data >= date('now', '-1 day') "
            "ORDER BY data LIMIT 5",
            (atual["cidade"],),
        )
        clima.append({**atual, "previsao": previsao})

    avisos = ind.consultar("SELECT * FROM avisos_inmet ORDER BY inicio DESC")
    alvo = area_inmet.casefold()
    na_area = [a for a in avisos if alvo and alvo in (a["area"] or "").casefold()]

    mes = ind.consultar("SELECT MAX(mes_codigo) m FROM alimentos_ipca")[0]["m"]
    alimentos = ind.consultar(
        "SELECT * FROM alimentos_ipca WHERE mes_codigo = ? ORDER BY localidade, item_codigo",
        (mes,),
    )

    cambio_atual = ind.consultar(
        "SELECT c.base, c.moeda, c.valor, c.data FROM cambio c JOIN (SELECT base, moeda, "
        "MAX(data) d FROM cambio GROUP BY base, moeda) m ON c.base = m.base "
        "AND c.moeda = m.moeda AND c.data = m.d"
    )
    serie_usd = ind.consultar(
        "SELECT data, valor FROM cambio WHERE base='USD' AND moeda='BRL' ORDER BY data DESC "
        "LIMIT 60"
    )[::-1]

    surtos = filtrar(
        recentes,
        Filtro(termos=TERMOS_SURTO, categorias=["saude", "epidemias"], nivel_minimo="alto"),
        25,
    )

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coletas": coletas,
        "enso": {
            "status": enso_status[0] if enso_status else None,
            "oni": oni[-12:],
            "semanal": semanal[::-1],
        },
        "arboviroses": arbo,
        "clima": clima,
        "avisos": {
            "total": len(avisos),
            "area": area_inmet,
            "na_area": na_area[:10],
            "resumo": Counter(f"{a['evento']} ({a['severidade']})" for a in avisos).most_common(),
        },
        "alimentos": {"mes": alimentos[0]["mes"] if alimentos else None, "itens": alimentos},
        "cambio": {"atual": cambio_atual, "usd_brl": serie_usd},
        "terremotos": ind.consultar(
            "SELECT * FROM terremotos ORDER BY magnitude DESC, quando DESC LIMIT 8"
        ),
        "criticos": [r for r in recentes if r["nivel"] == "critico"][:40],
        "surtos": surtos,
        "contagem": dict(Counter(r["nivel"] for r in recentes)),
        "temas": [
            {
                "id": t["id"],
                "nome": t["nome"],
                "noticias": filtrar(recentes, filtro_do_tema(t), 20),
            }
            for t in temas
        ],
        "feed": filtrar(recentes, feed_filtro or Filtro(), 80),
        "precos": {
            "cidade": cidade_precos,
            "medias": ind.medias_precos(cidade_precos or None),
            "ultimos": ind.listar_precos(cidade_precos or None, 15),
        },
    }
