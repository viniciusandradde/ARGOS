"""Tool functions for the Clima feature.

Rules (ADR-001):
    - tools.py NEVER makes HTTP directly — delegates to client.py
    - Returns formatted strings for LLM consumption
    - Uses Context for structured logging and progress reporting
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastmcp import Context

from mcp_brasil._shared.formatting import markdown_table

from . import client
from .constants import CODIGOS_TEMPO, IMPACTOS_EL_NINO_BR, IMPACTOS_LA_NINA_BR
from .schemas import StatusEnso


async def el_nino(ctx: Context) -> str:
    """Situação oficial do El Niño / La Niña (ENSO) segundo a NOAA (EUA).

    Fonte: Climate Prediction Center (CPC/NOAA) — o sistema oficial de alerta de
    ENSO. Traz o status do alerta (Watch/Advisory), a sinopse da última discussão,
    o índice ONI (média trimestral da anomalia no Niño 3.4), o RONI e as leituras
    semanais das regiões Niño, além dos impactos típicos no Brasil.
    """
    await ctx.info("Consultando NOAA CPC (ENSO)...")
    s = await client.status_enso()
    linhas = [
        "## 🌊 El Niño / La Niña — NOAA Climate Prediction Center",
        f"**Alerta oficial:** {s.alerta or 'indisponível'}",
        f"**Fase pelo ONI mais recente:** {s.fase}",
        "",
        f"> {s.sinopse}" if s.sinopse else "",
        "",
        "### ONI (anomalia °C, trimestres móveis)",
        markdown_table(
            ["Trimestre", "Ano", "ONI", "RONI"],
            [
                [o.trimestre, o.ano, f"{o.anomalia:+.2f}", _roni(s, o.trimestre, o.ano)]
                for o in s.oni[-6:]
            ],
        ),
        "",
        "### Leituras semanais (anomalia °C)",
        markdown_table(
            ["Semana", "Niño 1+2", "Niño 3", "Niño 3.4", "Niño 4"],
            [
                [
                    w.semana,
                    f"{w.nino12:+.1f}",
                    f"{w.nino3:+.1f}",
                    f"{w.nino34:+.1f}",
                    f"{w.nino4:+.1f}",
                ]
                for w in s.semanal[-4:]
            ],
        ),
        "",
    ]
    if s.fase.startswith("El Niño"):
        linhas.append(IMPACTOS_EL_NINO_BR)
    elif s.fase.startswith("La Niña"):
        linhas.append(IMPACTOS_LA_NINA_BR)
    linhas.append(
        "\nFonte: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/"
    )
    return "\n".join(linhas)


def _roni(s: StatusEnso, trimestre: str, ano: int) -> str:
    for r in s.roni:
        if r.trimestre == trimestre and r.ano == ano:
            return f"{r.anomalia:+.2f}"
    return "—"


async def previsao_tempo(cidade: str, ctx: Context, dias: int = 5) -> str:
    """Previsão do tempo para uma cidade brasileira (Open-Meteo, sem chave).

    Args:
        cidade: Nome da cidade (ex: 'Dourados', 'Campo Grande').
        dias: Dias de previsão (1 a 16).
    """
    locais = await client.geocodificar(cidade)
    if not locais:
        return f"Cidade '{cidade}' não encontrada."
    local = locais[0]
    await ctx.info(f"Previsão para {local['name']}/{local.get('admin1', '')}...")
    d = await client.previsao(local["latitude"], local["longitude"], dias)
    atual = d.get("current", {})
    diario = d.get("daily", {})
    linhas = [
        f"## Tempo em {local['name']} ({local.get('admin1', '')})",
        f"Agora: **{atual.get('temperature_2m')} °C**, "
        f"{CODIGOS_TEMPO.get(atual.get('weather_code', -1), 'condição desconhecida')}, "
        f"umidade {atual.get('relative_humidity_2m')}%, vento {atual.get('wind_speed_10m')} km/h",
        "",
    ]
    rows = []
    for i, dia in enumerate(diario.get("time", [])):
        rows.append(
            [
                datetime.fromisoformat(dia).strftime("%d/%m"),
                f"{diario['temperature_2m_min'][i]}-{diario['temperature_2m_max'][i]} °C",
                f"{diario['precipitation_sum'][i]} mm",
                f"{diario['precipitation_probability_max'][i]}%",
                CODIGOS_TEMPO.get(diario["weather_code"][i], ""),
            ]
        )
    linhas.append(markdown_table(["Dia", "Mín-Máx", "Chuva", "Prob.", "Condição"], rows))
    return "\n".join(linhas)


async def qualidade_ar(cidade: str, ctx: Context) -> str:
    """Qualidade do ar atual (PM2.5, PM10 e índice AQI) para uma cidade (Open-Meteo).

    Args:
        cidade: Nome da cidade.
    """
    locais = await client.geocodificar(cidade)
    if not locais:
        return f"Cidade '{cidade}' não encontrada."
    local = locais[0]
    await ctx.info(f"Qualidade do ar em {local['name']}...")
    atual = (await client.qualidade_ar(local["latitude"], local["longitude"])).get("current", {})
    aqi = atual.get("us_aqi") or 0
    faixa = (
        "boa"
        if aqi <= 50
        else "moderada"
        if aqi <= 100
        else "ruim para grupos sensíveis"
        if aqi <= 150
        else "ruim"
        if aqi <= 200
        else "muito ruim"
    )
    return (
        f"## Qualidade do ar — {local['name']}\n"
        f"AQI (EUA): **{aqi}** ({faixa}) | PM2.5: {atual.get('pm2_5')} µg/m³ | "
        f"PM10: {atual.get('pm10')} µg/m³"
    )


async def avisos_inmet(
    ctx: Context, area: str | None = None, so_vigentes: bool = True, limite: int = 20
) -> str:
    """Avisos meteorológicos oficiais do INMET (tempestade, chuvas intensas, baixa umidade...).

    Args:
        area: Filtra pela região/mesorregião ou estado citado no aviso
              (ex: 'Mato Grosso do Sul', 'Sudoeste de Mato Grosso do Sul', 'Paraná').
        so_vigentes: Só avisos que ainda não terminaram.
        limite: Máximo de avisos listados.
    """
    await ctx.info("Consultando avisos do INMET...")
    avisos = await client.avisos_inmet()
    if so_vigentes:
        avisos = [a for a in avisos if client.aviso_vigente(a)]
    if area:
        alvo = area.casefold()
        avisos = [a for a in avisos if alvo in a.area.casefold()]
    if not avisos:
        return "Nenhum aviso do INMET para esse filtro."
    resumo = Counter(f"{a.evento} ({a.severidade})" for a in avisos)
    linhas = [
        f"## ⚠️ {len(avisos)} aviso(s) do INMET" + (f" — {area}" if area else ""),
        "Resumo: " + "; ".join(f"{k}: {v}" for k, v in resumo.most_common()),
        "",
    ]
    for a in avisos[:limite]:
        linhas.append(f"- **{a.evento} — {a.severidade}** ({a.inicio} → {a.fim})")
        linhas.append(f"  {a.descricao[:220]}")
        linhas.append(f"  Áreas: {a.area[:200]}{'…' if len(a.area) > 200 else ''}")
    return "\n".join(linhas)


async def terremotos(
    ctx: Context, magnitude_minima: str = "4.5", periodo: str = "day", limite: int = 15
) -> str:
    """Terremotos recentes no mundo (USGS, tempo quase real).

    Args:
        magnitude_minima: '2.5', '4.5' ou 'significant'.
        periodo: 'hour', 'day', 'week' ou 'month'.
        limite: Máximo de eventos (ordenados por magnitude).
    """
    if magnitude_minima not in ("2.5", "4.5", "significant", "1.0", "all"):
        return "magnitude_minima deve ser '2.5', '4.5' ou 'significant'."
    if periodo not in ("hour", "day", "week", "month"):
        return "periodo deve ser 'hour', 'day', 'week' ou 'month'."
    await ctx.info("Consultando USGS...")
    eventos = await client.terremotos(magnitude_minima, periodo)
    if not eventos:
        return "Nenhum terremoto no período."
    rows = [
        [
            f"M{t.magnitude:.1f}",
            t.local,
            datetime.fromtimestamp(t.quando_ms / 1000, tz=timezone.utc).strftime(
                "%d/%m %H:%M UTC"
            ),
            "⚠️ sim" if t.tsunami else "",
        ]
        for t in eventos[:limite]
    ]
    return f"## 🌍 {len(eventos)} terremoto(s) — M{magnitude_minima}+ ({periodo})\n\n" + (
        markdown_table(["Mag.", "Local", "Quando", "Tsunami"], rows)
    )


async def eventos_naturais(ctx: Context, dias: int = 15, categoria: str | None = None) -> str:
    """Eventos naturais ativos no mundo detectados por satélite (NASA EONET):
    incêndios florestais, tempestades severas, vulcões, enchentes, secas...

    Args:
        dias: Janela em dias.
        categoria: Filtra pelo nome da categoria em inglês (ex: 'Wildfires', 'Severe Storms',
                   'Volcanoes', 'Floods', 'Drought').
    """
    await ctx.info("Consultando NASA EONET...")
    eventos = await client.eventos_naturais(dias)
    if categoria:
        eventos = [e for e in eventos if categoria.casefold() in e.categoria.casefold()]
    if not eventos:
        return "Nenhum evento natural ativo para esse filtro."
    resumo = Counter(e.categoria for e in eventos)
    linhas = [
        f"## 🛰️ {len(eventos)} evento(s) natural(is) ativo(s) — últimos {dias} dias",
        "Por categoria: " + ", ".join(f"{k}: {v}" for k, v in resumo.most_common()),
        "",
    ]
    linhas += [f"- {e.titulo} ({e.categoria}, {e.data})" for e in eventos[:25]]
    return "\n".join(linhas)


async def risco_local(
    cidade: str,
    ctx: Context,
    uf: str = "",
    bairro: str = "",
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    """Risco climático no nível do bairro (ou de um ponto exato): calor, ventania,
    tempestade, chuva forte e baixa umidade nas próximas 48 horas.

    Cruza: avisos oficiais do INMET (testando se o ponto está DENTRO do polígono do
    aviso), observação real do aeroporto mais próximo (METAR), previsão hora a hora de
    3 modelos (ECMWF, ICON, GFS) com a divergência entre eles e focos de queimada (INPE).

    Args:
        cidade: Município (ex: 'Dourados').
        uf: Sigla do estado (ex: 'MS').
        bairro: Bairro (ex: 'Jardim América'). Vazio = centro do município.
        lat: Latitude exata (opcional; sobrepõe o bairro).
        lon: Longitude exata (opcional).
    """
    from . import local as L

    if lat is not None and lon is not None:
        alvo = L.ponto(lat, lon, cidade, uf)
    else:
        encontrado = await L.localizar(cidade, uf, bairro)
        if encontrado is None:
            return f"Não encontrei '{cidade}/{uf}'."
        alvo = encontrado
    await ctx.info(f"Analisando risco climático em {alvo.nome}...")
    r = await L.relatorio(alvo)
    icone = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}
    linhas = [
        f"## 🌩️ Risco climático — {alvo.nome}",
        f"Coordenadas {alvo.lat:.5f}, {alvo.lon:.5f} (precisão: {alvo.precisao}; {alvo.fonte})",
        "",
        "### Avisos oficiais do INMET",
    ]
    if r["avisos"]:
        for a in r["avisos"]:
            onde = "ponto DENTRO da área" if a["dentro_do_poligono"] else "município citado"
            linhas.append(
                f"- **{a['evento']} — {a['severidade']}** ({a['inicio']} → {a['fim']}; {onde})"
            )
    else:
        linhas.append("- Nenhum aviso vigente para este ponto.")
    linhas += ["", "### Próximas 48 h (critérios INMET / NOAA)"]
    for x in r["riscos"]:
        linhas.append(
            f"- {icone[x['nivel']]} **{x['tipo'].upper()}: {x['rotulo']}** — {x['valor']}"
            + (f" (pico {x['quando'][5:16].replace('T', ' ')})" if x["quando"] else "")
        )
    obs = r["observacao"]
    if obs:
        linhas += [
            "",
            f"### Observação real — {obs['nome']} ({obs['distancia_km']} km)",
            f"{obs['temperatura']}°C, vento {obs['vento_kmh']} km/h"
            + (f", rajada {obs['rajada_kmh']} km/h" if obs["rajada_kmh"] else "")
            + (f", fenômeno {obs['fenomeno']}" if obs["fenomeno"] else "")
            + f" — `{obs['bruto']}`",
        ]
    if r["consenso"]:
        linhas += ["", "### Consenso entre modelos (máx. do dia)"]
        rows = []
        for c in r["consenso"]:
            for modelo, v in c["modelos"].items():
                rows.append([c["dia"], modelo, v["tmax"], v["rajada"], v["chuva"]])
        linhas.append(
            markdown_table(["Dia", "Modelo", "Tmáx °C", "Rajada km/h", "Chuva mm"], rows)
        )
    if r["focos"]:
        linhas.append(f"\n🔥 {len(r['focos'])} foco(s) de queimada em até 50 km "
                      f"(mais próximo a {r['focos'][0]['distancia_km']} km).")  # fmt: skip
    if r["falhas"]:
        linhas.append(f"\n⚠️ Fontes indisponíveis agora: {', '.join(r['falhas'])}")
    return "\n".join(linhas)
