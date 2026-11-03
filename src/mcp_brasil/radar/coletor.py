"""Coletor periódico de indicadores → banco ``indicadores.db``.

Cada etapa é independente: se uma fonte cair, as outras continuam e a falha
fica registrada na tabela ``coletas``. Uso:

    python -m mcp_brasil.radar coletar           # uma rodada
    python -m mcp_brasil.radar coletar --loop    # a cada RADAR_COLETA_MINUTOS
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .indicadores import Indicadores, agora_iso

logger = logging.getLogger(__name__)

UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}  # fmt: skip


@dataclass
class ConfigColeta:
    cidades: list[str] = field(default_factory=lambda: ["Dourados/MS", "Campo Grande/MS"])
    alimentos_localidades: list[str] = field(default_factory=lambda: ["brasil", "campo_grande"])
    moedas: str = "BRL,EUR,CNY,ARS,GBP"


def _separar_cidade(cidade: str) -> tuple[str, str | None]:
    nome, _, uf = cidade.partition("/")
    return nome.strip(), (uf.strip().upper() or None)


# --- Etapas ------------------------------------------------------------------


async def coletar_noticias(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.noticias import client
    from mcp_brasil.data.noticias.constants import FONTES

    noticias, falhas = await client.buscar_varios(list(FONTES))
    agora = agora_iso()
    ind.executar_varios(
        "INSERT INTO noticias (link, fonte, fonte_nome, categoria, escopo, idioma, titulo, "
        "resumo, nivel, publicado_em, coletado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(link) DO UPDATE SET nivel = excluded.nivel",
        [
            (
                n.link, n.fonte, FONTES[n.fonte].nome, FONTES[n.fonte].categoria,
                FONTES[n.fonte].escopo, FONTES[n.fonte].idioma, n.titulo, n.resumo, n.nivel,
                n.publicado_em.astimezone(timezone.utc).isoformat() if n.publicado_em else agora,
                agora,
            )
            for n in noticias
        ],
    )  # fmt: skip
    limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    ind.executar("DELETE FROM noticias WHERE publicado_em < ?", (limite,))
    return f"{len(noticias)} notícias, {len(falhas)} fontes com falha"


async def coletar_enso(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.clima import client

    s = await client.status_enso()
    ind.executar(
        "INSERT INTO enso_status (id, alerta, fase, sinopse, atualizado_em) VALUES (1,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET alerta=excluded.alerta, fase=excluded.fase, "
        "sinopse=excluded.sinopse, atualizado_em=excluded.atualizado_em",
        (s.alerta, s.fase, s.sinopse, agora_iso()),
    )
    roni = {(r.ano, r.trimestre): r.anomalia for r in s.roni}
    ind.executar_varios(
        "INSERT OR REPLACE INTO enso_oni (ano, trimestre, oni, roni) VALUES (?,?,?,?)",
        [(o.ano, o.trimestre, o.anomalia, roni.get((o.ano, o.trimestre))) for o in s.oni],
    )
    ind.executar_varios(
        "INSERT OR REPLACE INTO enso_semanal (semana, data, nino12, nino3, nino34, nino4) "
        "VALUES (?,?,?,?,?,?)",
        [
            (
                w.semana,
                datetime.strptime(w.semana.title(), "%d%b%Y").date().isoformat(),
                w.nino12, w.nino3, w.nino34, w.nino4,
            )
            for w in s.semanal
        ],
    )  # fmt: skip
    return f"{s.alerta} / {s.fase}"


async def coletar_arboviroses(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.vigilancia import client
    from mcp_brasil.data.vigilancia.constants import DOENCAS

    linhas = []
    for cidade in cfg.cidades:
        nome, uf = _separar_cidade(cidade)
        local = client.localizar_municipio(nome, uf)
        if local is None:
            continue
        geocodigo, municipio = local
        for doenca in DOENCAS:
            r = await client.resumo_arbovirose(geocodigo, doenca)
            if r.semana:
                linhas.append(
                    (geocodigo, municipio, doenca, r.semana, r.nivel, r.casos_semana, r.casos_ano,
                     r.incidencia_100k, r.rt, agora_iso())
                )  # fmt: skip
    ind.executar_varios(
        "INSERT OR REPLACE INTO arboviroses (geocodigo, municipio, doenca, semana, nivel, "
        "casos_semana, casos_ano, incidencia_100k, rt, coletado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
        linhas,
    )
    return f"{len(linhas)} séries"


async def coletar_alimentos(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.alimentos import client

    dados = await client.variacoes(tuple(cfg.alimentos_localidades), 13)
    ind.executar_varios(
        "INSERT OR REPLACE INTO alimentos_ipca (localidade, item_codigo, item, mes_codigo, mes, "
        "variacao_mes, variacao_12m) VALUES (?,?,?,?,?,?,?)",
        [
            (d.localidade, d.codigo, d.item, d.mes_codigo, d.mes, d.variacao_mes, d.variacao_12m)
            for d in dados
        ],
    )
    return f"{len(dados)} registros"


async def coletar_cambio(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.mundo import client

    inicio = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
    linhas = []
    for base, moedas in (("USD", cfg.moedas), ("EUR", "BRL")):
        d = await client.historico(base, moedas, inicio)
        for dia, taxas in d.get("rates", {}).items():
            linhas += [(dia, base, moeda, valor) for moeda, valor in taxas.items()]
    ind.executar_varios(
        "INSERT OR REPLACE INTO cambio (data, base, moeda, valor) VALUES (?,?,?,?)", linhas
    )
    return f"{len(linhas)} cotações"


async def coletar_clima(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.clima import client

    feitas = 0
    for cidade in cfg.cidades:
        nome, uf = _separar_cidade(cidade)
        locais = await client.geocodificar(nome)
        if uf:
            locais = [lc for lc in locais if lc.get("admin1") == UF_NOMES.get(uf)] or locais
        if not locais:
            continue
        lat, lon = locais[0]["latitude"], locais[0]["longitude"]
        d = await client.previsao(lat, lon, 5)
        try:
            aqi = (await client.qualidade_ar(lat, lon)).get("current", {}).get("us_aqi")
        except Exception:  # air quality is optional
            aqi = None
        atual, diario = d.get("current", {}), d.get("daily", {})
        ind.executar(
            "INSERT OR REPLACE INTO clima_atual (cidade, temperatura, umidade, vento, codigo, "
            "aqi, atualizado_em) VALUES (?,?,?,?,?,?,?)",
            (
                cidade, atual.get("temperature_2m"), atual.get("relative_humidity_2m"),
                atual.get("wind_speed_10m"), atual.get("weather_code"), aqi, agora_iso(),
            ),
        )  # fmt: skip
        ind.executar_varios(
            "INSERT OR REPLACE INTO clima_previsao (cidade, data, tmin, tmax, chuva_mm, "
            "prob_chuva, codigo) VALUES (?,?,?,?,?,?,?)",
            [
                (
                    cidade, dia, diario["temperature_2m_min"][i], diario["temperature_2m_max"][i],
                    diario["precipitation_sum"][i], diario["precipitation_probability_max"][i],
                    diario["weather_code"][i],
                )
                for i, dia in enumerate(diario.get("time", []))
            ],
        )  # fmt: skip
        feitas += 1
    return f"{feitas} cidades"


async def coletar_avisos(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.clima import client

    avisos = [a for a in await client.avisos_inmet() if client.aviso_vigente(a)]
    ind.executar("DELETE FROM avisos_inmet")
    ind.executar_varios(
        "INSERT OR REPLACE INTO avisos_inmet (link, evento, severidade, inicio, fim, area, "
        "descricao) VALUES (?,?,?,?,?,?,?)",
        [(a.link, a.evento, a.severidade, a.inicio, a.fim, a.area, a.descricao) for a in avisos],
    )
    return f"{len(avisos)} avisos vigentes"


async def coletar_terremotos(ind: Indicadores, cfg: ConfigColeta) -> str:
    from mcp_brasil.data.clima import client

    eventos = await client.terremotos("4.5", "week")
    ind.executar("DELETE FROM terremotos")
    ind.executar_varios(
        "INSERT OR REPLACE INTO terremotos (link, magnitude, local, quando, tsunami) "
        "VALUES (?,?,?,?,?)",
        [
            (
                t.link or f"{t.local}-{t.quando_ms}",
                t.magnitude,
                t.local,
                datetime.fromtimestamp(t.quando_ms / 1000, tz=timezone.utc).isoformat(),
                int(t.tsunami),
            )
            for t in eventos
        ],
    )
    return f"{len(eventos)} terremotos"


Etapa = Callable[[Indicadores, ConfigColeta], Awaitable[str]]

ETAPAS: dict[str, Etapa] = {
    "noticias": coletar_noticias,
    "enso": coletar_enso,
    "arboviroses": coletar_arboviroses,
    "alimentos": coletar_alimentos,
    "cambio": coletar_cambio,
    "clima": coletar_clima,
    "avisos_inmet": coletar_avisos,
    "terremotos": coletar_terremotos,
}


async def coletar_tudo(
    ind: Indicadores, cfg: ConfigColeta, etapas: list[str] | None = None
) -> dict[str, str]:
    """Run all collection steps concurrently. Returns ``{etapa: resultado}``."""
    nomes = etapas or list(ETAPAS)

    async def rodar(nome: str) -> str:
        try:
            resultado = await ETAPAS[nome](ind, cfg)
            ind.registrar_coleta(nome, True, resultado)
            return resultado
        except Exception as exc:  # one failing source must not stop the others
            logger.warning("Coleta %s falhou: %s", nome, exc)
            ind.registrar_coleta(nome, False, str(exc))
            return f"ERRO: {exc}"

    resultados = await asyncio.gather(*(rodar(n) for n in nomes))
    return dict(zip(nomes, resultados, strict=True))


async def loop_coleta(
    ind: Indicadores,
    cfg: ConfigColeta,
    minutos: int,
    depois: Callable[[], Awaitable[object]] | None = None,
) -> None:
    """Collect forever; ``depois`` runs after each round (e.g. alert dispatch)."""
    while True:
        resultados = await coletar_tudo(ind, cfg)
        logger.info("Coleta concluída: %s", resultados)
        if depois is not None:
            try:
                logger.info("Alertas: %s", await depois())
            except Exception as exc:  # alerts must never stop the collector
                logger.warning("Envio de alertas falhou: %s", exc)
        await asyncio.sleep(max(minutos, 1) * 60)
