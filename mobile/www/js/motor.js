// ARGOS mobile — local collection engine.
// Port of the server collector (radar/coletor.py) and local climate radar
// (data/clima/local.py): every source is fetched directly from the phone.
// In the APK, CapacitorHttp patches fetch() so requests run natively (no CORS).
(() => {
  "use strict";
  const D = window.ARGOS_DADOS;
  const UA = "ARGOS-mobile/1.0 (+https://github.com/viniciusandradde/mcp-brasil)";
  const NIVEIS = ["Normal", "Perigo Potencial", "Perigo", "Grande Perigo"];
  const MODELOS = { ecmwf_ifs025: "ECMWF IFS", icon_global: "DWD ICON", gfs_seamless: "NOAA GFS" };
  const VARIAVEIS_HORA = "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,"
    + "wind_gusts_10m,precipitation,precipitation_probability,cape,weather_code,uv_index";

  // ---- Storage -----------------------------------------------------------------
  const store = {
    get(k, padrao) {
      try { const v = localStorage.getItem("argos:" + k); return v == null ? padrao : JSON.parse(v); }
      catch (_) { return padrao; }
    },
    set(k, v) { try { localStorage.setItem("argos:" + k, JSON.stringify(v)); } catch (_) {} },
  };

  const CONFIG_PADRAO = {
    cidades: [
      { nome: "Dourados", uf: "MS", geocodigo: "5003702" },
      { nome: "Campo Grande", uf: "MS", geocodigo: "5002704" },
    ],
    ipca: ["brasil", "campo_grande"],
    clima: { uf: "MS", cidade: "Dourados", bairro: "", lat: null, lon: null },
    temas: [],
    openMeteoKey: "",
    intervaloMin: 15,
    notificar: { inmet: true, riscoLocal: true, surtos: true, criticos: false, boletim: true },
    boletimHora: 7,
  };
  function config() {
    const c = store.get("config", {});
    return { ...CONFIG_PADRAO, ...c, notificar: { ...CONFIG_PADRAO.notificar, ...(c.notificar || {}) },
      clima: { ...CONFIG_PADRAO.clima, ...(c.clima || {}) } };
  }
  const salvarConfig = (c) => store.set("config", c);

  // ---- HTTP --------------------------------------------------------------------
  function qs(params) {
    return Object.entries(params).filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");
  }
  async function http(url, { params, tipo = "json", headers = {}, timeout = 30000, tentativas = 2 } = {}) {
    const alvo = params ? url + (url.includes("?") ? "&" : "?") + qs(params) : url;
    let erro;
    for (let i = 0; i < tentativas; i++) {
      try {
        const r = await Promise.race([
          fetch(alvo, { headers }),
          new Promise((_, rej) => setTimeout(() => rej(new Error("tempo esgotado")), timeout)),
        ]);
        if (!r.ok) throw new Error("HTTP " + r.status);
        if (tipo === "text") return await r.text();
        const t = await r.text();
        return JSON.parse(t);
      } catch (e) {
        erro = e;
        if (i + 1 < tentativas) await new Promise((ok) => setTimeout(ok, 800 * (i + 1)));
      }
    }
    throw erro;
  }
  const memo = new Map();
  async function cache(chave, ttlMs, fn) {
    const m = memo.get(chave);
    if (m && Date.now() - m.t < ttlMs) return m.v;
    const v = await fn();
    memo.set(chave, { t: Date.now(), v });
    return v;
  }
  async function pool(itens, n, fn) {
    const saida = new Array(itens.length);
    let i = 0;
    await Promise.all(Array.from({ length: Math.min(n, itens.length) }, async () => {
      while (i < itens.length) { const k = i++; saida[k] = await fn(itens[k], k); }
    }));
    return saida;
  }
  function openMeteo(url, params) {
    const key = config().openMeteoKey;
    if (!key) return [url, params];
    return [url.replace("https://api.", "https://customer-api.")
      .replace("https://geocoding-api.", "https://customer-geocoding-api.")
      .replace("https://air-quality-api.", "https://customer-air-quality-api."), { ...params, apikey: key }];
  }

  // ---- Text helpers ----------------------------------------------------------
  const norm = (t) => String(t || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const reCritico = new RegExp("\\b(?:" + D.CRITICO.join("|") + ")\\b");
  const reAlto = new RegExp("\\b(?:" + D.ALTO.join("|") + ")\\b");
  function classificar(texto) {
    const t = norm(texto);
    return reCritico.test(t) ? "critico" : reAlto.test(t) ? "alto" : "normal";
  }
  const PESO = { normal: 0, alto: 1, critico: 2 };
  function textoHtml(html) {
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    return (doc.body ? doc.body.textContent : "").replace(/\s+/g, " ").trim();
  }
  function distanciaKm(lat1, lon1, lat2, lon2) {
    const r = 6371, rad = Math.PI / 180;
    const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
    const a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
    return 2 * r * Math.asin(Math.sqrt(a));
  }
  function noAnel(lon, lat, anel) {
    let dentro = false;
    for (let i = 0, j = anel.length - 1; i < anel.length; j = i++) {
      const [xi, yi] = anel[i], [xj, yj] = anel[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi) dentro = !dentro;
    }
    return dentro;
  }
  function pontoNoPoligono(lat, lon, geo) {
    if (!geo) return false;
    const polis = geo.type === "Polygon" ? [geo.coordinates || []] : geo.type === "MultiPolygon" ? geo.coordinates || [] : [];
    return polis.some((p) => p.length && noAnel(lon, lat, p[0]) && !p.slice(1).some((b) => noAnel(lon, lat, b)));
  }

  // ---- News (RSS / Atom / RDF) -----------------------------------------------
  function parseFeed(xml, fonteId) {
    const doc = new DOMParser().parseFromString(xml, "text/xml");
    if (doc.getElementsByTagName("parsererror").length) return [];
    const itens = [...doc.getElementsByTagName("item"), ...doc.getElementsByTagName("entry")];
    const txt = (el, ...nomes) => {
      for (const n of nomes) { const e = el.getElementsByTagName(n)[0]; if (e && e.textContent.trim()) return e.textContent.trim(); }
      return "";
    };
    const saida = [];
    for (const it of itens.slice(0, 40)) {
      const titulo = textoHtml(txt(it, "title"));
      let link = txt(it, "link");
      if (!link) {
        const ls = [...it.getElementsByTagName("link")];
        const alt = ls.find((l) => (l.getAttribute("rel") || "alternate") === "alternate") || ls[0];
        link = alt ? alt.getAttribute("href") || "" : "";
      }
      if (!titulo || !link) continue;
      const resumo = textoHtml(txt(it, "description", "summary", "content", "content:encoded")).slice(0, 320);
      const data = txt(it, "pubDate", "dc:date", "published", "updated");
      const d = data ? new Date(data) : null;
      saida.push({ link, fonte: fonteId, titulo, resumo, nivel: classificar(titulo + " " + resumo),
        publicado_em: d && !isNaN(d) ? d.toISOString() : null });
    }
    return saida;
  }

  async function coletarNoticias(estado) {
    const ids = Object.keys(D.FONTES);
    const falhas = [];
    const lotes = await pool(ids, 8, async (id) => {
      try { return parseFeed(await http(D.FONTES[id].url, { tipo: "text", timeout: 20000, tentativas: 1 }), id); }
      catch (_) { falhas.push(id); return []; }
    });
    const agora = new Date().toISOString();
    const porLink = new Map((estado.noticias || []).map((n) => [n.link, n]));
    for (const n of lotes.flat()) {
      const f = D.FONTES[n.fonte];
      const antigo = porLink.get(n.link);
      porLink.set(n.link, { ...n, fonte_nome: f.nome, categoria: f.categoria, escopo: f.escopo, idioma: f.idioma,
        publicado_em: n.publicado_em || antigo?.publicado_em || agora, coletado_em: antigo?.coletado_em || agora });
    }
    const limite = Date.now() - 7 * 86400e3;
    estado.noticias = [...porLink.values()].filter((n) => new Date(n.publicado_em).getTime() >= limite)
      .sort((a, b) => b.publicado_em.localeCompare(a.publicado_em)).slice(0, 1500);
    return `${lotes.flat().length} notícias, ${falhas.length} fontes com falha`;
  }

  // ---- ENSO (NOAA CPC) -------------------------------------------------------
  function parseOni(texto, ultimos = 12) {
    const out = [];
    for (const linha of texto.split(/\r?\n/)) {
      const p = linha.trim().split(/\s+/);
      if (p.length < 3 || !/^\d+$/.test(p[1])) continue;
      const v = parseFloat(p[p.length - 1]);
      if (!isNaN(v)) out.push({ trimestre: p[0], ano: +p[1], oni: v });
    }
    return out.slice(-ultimos);
  }
  function parseSemanal(texto, ultimos = 12) {
    const out = [];
    for (const linha of texto.split(/\r?\n/)) {
      const p = linha.trim().split(/\s+/);
      if (p.length !== 9 || !/^\d{2}[A-Z]{3}\d{4}$/.test(p[0])) continue;
      const v = p.slice(1).map(Number);
      out.push({ semana: p[0], nino12: v[1], nino3: v[3], nino34: v[5], nino4: v[7] });
    }
    return out.slice(-ultimos);
  }
  function parseDiscussao(html) {
    const t = textoHtml(html);
    const a = t.match(/ENSO Alert System Status:\s*(.+?)\s+Synopsis:/);
    const s = t.match(/Synopsis:\s*(.+?)(?:\s+[A-Z][a-z]+ Niño strengthened|\.\s)/);
    return { alerta: a ? a[1].trim() : "", sinopse: s ? s[1].trim() + "." : "" };
  }
  async function coletarEnso(estado) {
    const base = "https://www.cpc.ncep.noaa.gov";
    const [disc, oni, roni, sem] = await Promise.all([
      http(base + "/products/analysis_monitoring/enso_advisory/ensodisc.shtml", { tipo: "text" }),
      http(base + "/data/indices/oni.ascii.txt", { tipo: "text" }),
      http(base + "/data/indices/RONI.ascii.txt", { tipo: "text" }).catch(() => ""),
      http(base + "/data/indices/wksst9120.for", { tipo: "text" }),
    ]);
    const { alerta, sinopse } = parseDiscussao(disc);
    const r = new Map(parseOni(roni).map((x) => [x.ano + x.trimestre, x.oni]));
    const o = parseOni(oni).map((x) => ({ ...x, roni: r.get(x.ano + x.trimestre) ?? null }));
    const ultimo = o[o.length - 1] || {};
    const fase = ultimo.oni >= 0.5 ? (ultimo.oni >= 1.5 ? "El Niño forte" : "El Niño") : ultimo.oni <= -0.5 ? "La Niña" : "Neutro";
    estado.enso = { status: { alerta, sinopse, fase, atualizado_em: new Date().toISOString() }, oni: o, semanal: parseSemanal(sem) };
    return `${alerta || "?"} / ONI ${ultimo.oni}`;
  }

  // ---- Arboviroses (InfoDengue) -------------------------------------------
  async function resumoArbo(geocodigo, doenca) {
    const ano = new Date().getFullYear();
    const lista = await http("https://info.dengue.mat.br/api/alertcity", { params: {
      geocode: geocodigo, disease: doenca, format: "json", ew_start: 1, ew_end: 53, ey_start: ano, ey_end: ano } });
    if (!Array.isArray(lista) || !lista.length) return null;
    lista.sort((a, b) => (a.SE || 0) - (b.SE || 0));
    const u = lista[lista.length - 1];
    return { doenca, semana: u.SE, nivel: u.nivel, casos_semana: Math.round(u.casos || 0),
      casos_ano: lista.reduce((s, a) => s + Math.round(a.casos || 0), 0),
      incidencia_100k: Math.round((u.p_inc100k || 0) * 10) / 10, rt: u.Rt == null ? null : Math.round(u.Rt * 100) / 100 };
  }
  async function coletarArbo(estado) {
    const cfg = config();
    const tarefas = cfg.cidades.flatMap((c) => D.DOENCAS.map((d) => [c, d]));
    const res = await pool(tarefas, 4, async ([c, d]) => {
      try { const r = await resumoArbo(c.geocodigo, d); return r && { ...r, municipio: `${c.nome}/${c.uf}`, geocodigo: c.geocodigo }; }
      catch (_) { return null; }
    });
    const ok = res.filter(Boolean);
    if (!ok.length && tarefas.length) throw new Error("InfoDengue indisponível");
    estado.arboviroses = ok;
    return `${ok.length} séries`;
  }

  // ---- Alimentos (IPCA SIDRA 7060) ---------------------------------------
  async function coletarAlimentos(estado) {
    const cfg = config();
    const local = cfg.ipca.map((l) => D.LOCALIDADES_IPCA[l]?.codigo).filter(Boolean).join("/");
    const url = `https://apisidra.ibge.gov.br/values/t/7060/${local}/v/63,2265/p/last%201/c315/${Object.keys(D.ITENS_IPCA).join(",")}`;
    const linhas = await http(url, { timeout: 60000 });
    const reg = new Map();
    const numero = (v) => (v == null || ["", "-", "...", "X"].includes(v) ? null : isNaN(+v) ? null : +v);
    for (const r of (Array.isArray(linhas) ? linhas : []).slice(1)) {
      const k = r.D4C + "|" + r.D1N;
      const x = reg.get(k) || { codigo: r.D4C, item: D.ITENS_IPCA[r.D4C] || r.D4N, localidade: r.D1N, mes: r.D3N,
        variacao_mes: null, variacao_12m: null };
      if (r.D2C === "63") x.variacao_mes = numero(r.V); else if (r.D2C === "2265") x.variacao_12m = numero(r.V);
      reg.set(k, x);
    }
    const itens = [...reg.values()];
    estado.alimentos = { mes: itens[0]?.mes || "", itens };
    return `${itens.length} registros`;
  }

  // ---- Câmbio (Frankfurter / BCE) --------------------------------------------
  async function coletarCambio(estado) {
    const inicio = new Date(Date.now() - 90 * 86400e3).toISOString().slice(0, 10);
    const [usd, eur] = await Promise.all([
      http(`https://api.frankfurter.dev/v1/${inicio}..`, { params: { base: "USD", symbols: "BRL,EUR,CNY,ARS,GBP" } }),
      http("https://api.frankfurter.dev/v1/latest", { params: { base: "EUR", symbols: "BRL" } }),
    ]);
    const dias = Object.keys(usd.rates || {}).sort();
    const ult = dias[dias.length - 1];
    const atual = Object.entries(usd.rates[ult] || {}).map(([moeda, valor]) => ({ base: "USD", moeda, valor, data: ult }));
    if (eur.rates?.BRL) atual.push({ base: "EUR", moeda: "BRL", valor: eur.rates.BRL, data: eur.date });
    estado.cambio = { atual, usd_brl: dias.map((d) => ({ data: d, valor: usd.rates[d].BRL })) };
    return `${dias.length} dias`;
  }

  // ---- Clima das cidades (Open-Meteo) ----------------------------------------
  async function coordenadasCidade(c) {
    if (c.lat != null) return c;
    const [url, params] = openMeteo("https://geocoding-api.open-meteo.com/v1/search",
      { name: c.nome, count: 10, language: "pt", countryCode: "BR" });
    const r = await cache("geo:" + c.geocodigo, 7 * 86400e3, () => http(url, { params }));
    const achado = (r.results || []).find((x) => x.admin1 === D.UF_NOMES[c.uf]) || (r.results || [])[0];
    if (!achado) throw new Error("cidade não encontrada: " + c.nome);
    c.lat = achado.latitude; c.lon = achado.longitude;
    return c;
  }
  // ---- Medição real: estação automática do INMET --------------------------------
  const ESTACAO_DISTANCIA_MAX_KM = 60, ESTACAO_IDADE_MAX_MS = 3 * 3600e3;
  const numero = (v) => (v === "" || v == null || isNaN(Number(v)) ? null : Number(v));
  // The endpoint is undocumented: anything stale, distant or incomplete falls back to the model.
  // Its distance is unreliable (71 km for the station inside Campo Grande): coordinates win.
  function parseEstacao(payload, agora = Date.now(), lat = null, lon = null) {
    const e = (payload && payload.estacao) || {}, d = (payload && payload.dados) || {};
    const temperatura = numero(d.TEM_INS), latE = numero(e.LATITUDE), lonE = numero(e.LONGITUDE);
    const distancia = lat != null && lon != null && latE != null && lonE != null
      ? Math.round(distanciaKm(lat, lon, latE, lonE) * 10) / 10 : numero(e.DISTANCIA_EM_KM);
    if (temperatura == null || distancia == null || distancia > ESTACAO_DISTANCIA_MAX_KM) return null;
    const hora = String(d.HR_MEDICAO || "");
    const quando = Date.parse(`${d.DT_MEDICAO}T${hora.slice(0, 2)}:${hora.slice(2, 4)}:00Z`);
    if (isNaN(quando) || agora - quando > ESTACAO_IDADE_MAX_MS) return null;
    const kmh = (v) => (numero(v) == null ? null : Math.round(numero(v) * 36) / 10);
    const codigo = String(e.CODIGO || d.CD_ESTACAO || ""), nome = String(e.NOME || d.DC_NOME || "");
    return { rotulo: `INMET ${codigo} ${nome}`, codigo, nome, distancia_km: distancia,
      quando: new Date(quando).toISOString(), temperatura, umidade: numero(d.UMD_INS), vento_kmh: kmh(d.VEN_VEL),
      rajada_kmh: kmh(d.VEN_RAJ), lat: latE, lon: lonE };
  }
  async function estacaoProxima(geocodigo, lat, lon) {
    if (!geocodigo) return null;
    return parseEstacao(await http("https://apiprevmet3.inmet.gov.br/estacao/proxima/" + geocodigo), Date.now(), lat, lon);
  }
  // ---- Medição real: estações da Embrapa (a cada 15 min) --------------------------
  const GUIA_CLIMA = "https://www.cpao.embrapa.br/gc/api/v1/guiaclima", GUIA_CLIMA_RAIO_KM = 25;
  const GUIA_CLIMA_ESTACOES = [[1, "Dourados Embrapa", -22.2753, -54.8183], [5, "Dourados UFGD", -22.2333, -54.9861],
    [3, "Rio Brilhante", -21.8461, -54.5383], [4, "Ivinhema", -22.3889, -53.8869], [6, "Naviraí", -23.0258, -54.1894]];
  function parseGuiaClima(real, hoje, estacao, lat, lon, agora = Date.now()) {
    const [codigo, nome, latE, lonE] = estacao, temperatura = numero(real && real.temp_c_avg);
    const m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}:\d{2})$/.exec(String(real && real.day));
    if (temperatura == null || !m) return null;
    const quando = Date.parse(`${m[3]}-${m[2]}-${m[1]}T${m[4]}:00-04:00`); // local time, no offset in the API
    if (isNaN(quando) || agora - quando > ESTACAO_IDADE_MAX_MS) return null;
    const mesmoDia = hoje && hoje.day === `${m[3]}-${m[2]}-${m[1]}`, vento = numero(real.u2m_ms);
    return { rotulo: `Embrapa Guia Clima · ${nome}`, codigo: String(codigo), nome, distancia_km: Math.round(distanciaKm(lat, lon, latE, lonE) * 10) / 10,
      quando: new Date(quando).toISOString(), temperatura, umidade: numero(real.urc_pctg_avg), vento_kmh: vento == null ? null : Math.round(vento * 36) / 10,
      rajada_kmh: null, hoje_max: mesmoDia ? numero(hoje.temp_c_max) : null, hoje_min: mesmoDia ? numero(hoje.temp_c_min) : null, lat: latE, lon: lonE };
  }
  async function guiaClimaProximo(lat, lon) {
    const e = [...GUIA_CLIMA_ESTACOES].sort((a, b) => distanciaKm(lat, lon, a[2], a[3]) - distanciaKm(lat, lon, b[2], b[3]))[0];
    if (distanciaKm(lat, lon, e[2], e[3]) > GUIA_CLIMA_RAIO_KM) return null;
    const params = { cod_estacao: e[0] };
    const [real, hoje] = await Promise.all([http(GUIA_CLIMA + "/tempoReal", { params }), http(GUIA_CLIMA + "/leituraAtual", { params }).catch(() => ({}))]);
    return parseGuiaClima(real, hoje, e, lat, lon);
  }
  async function medicaoLocal(geocodigo, lat, lon) {
    const leitura = await guiaClimaProximo(lat, lon).catch(() => null);
    return leitura || estacaoProxima(geocodigo, lat, lon);
  }
  // Official daily forecast as {ISO date: [min, max]}; near days are split by period.
  function parsePrevisaoInmet(payload, geocodigo) {
    const saida = {};
    for (const [dia, conteudo] of Object.entries((payload && payload[geocodigo]) || {})) {
      if (!conteudo || typeof conteudo !== "object") continue;
      const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(dia);
      const sub = Object.values(conteudo).filter((p) => p && typeof p === "object");
      const periodos = sub.length ? sub : [conteudo];
      const mins = periodos.map((p) => numero(p.temp_min)).filter((v) => v != null);
      const maxs = periodos.map((p) => numero(p.temp_max)).filter((v) => v != null);
      if (m && mins.length && maxs.length) saida[`${m[3]}-${m[2]}-${m[1]}`] = [Math.min(...mins), Math.max(...maxs)];
    }
    return saida;
  }
  const previsaoInmet = (geocodigo) => cache("prev-inmet:" + geocodigo, 3 * 3600e3, async () =>
    parsePrevisaoInmet(await http("https://apiprevmet3.inmet.gov.br/previsao/" + geocodigo, { timeout: 40000 }), geocodigo));
  // Lowest and highest daily maximum among the models, for days with two or more.
  function parseFaixa(d) {
    const di = (d && d.daily) || {}, faixa = {};
    (di.time || []).forEach((dia, i) => {
      const vs = Object.keys(MODELOS).map((k) => (di["temperature_2m_max_" + k] || [])[i]).filter((v) => v != null);
      if (vs.length >= 2) faixa[dia] = [Math.min(...vs), Math.max(...vs)];
    });
    return faixa;
  }
  async function faixaModelos(lat, lon) {
    const [url, params] = openMeteo("https://api.open-meteo.com/v1/forecast", { latitude: lat, longitude: lon,
      timezone: "auto", forecast_days: 5, daily: "temperature_2m_max", models: Object.keys(MODELOS).join(",") });
    return parseFaixa(await http(url, { params }));
  }
  async function coletarClima(estado) {
    const cfg = config();
    const res = await pool(cfg.cidades, 3, async (c) => {
      try {
        await coordenadasCidade(c);
        const [url, params] = openMeteo("https://api.open-meteo.com/v1/forecast", {
          latitude: c.lat, longitude: c.lon, timezone: "auto", forecast_days: 5,
          current: "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
          daily: "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code" });
        const [d, leitura, faixa, oficial] = await Promise.all([http(url, { params }),
          medicaoLocal(c.geocodigo, c.lat, c.lon).catch(() => null), faixaModelos(c.lat, c.lon).catch(() => ({})),
          previsaoInmet(c.geocodigo).catch(() => ({}))]);
        const a = d.current || {}, di = d.daily || {};
        return { cidade: `${c.nome}/${c.uf}`, temperatura: leitura ? leitura.temperatura : a.temperature_2m,
          umidade: leitura?.umidade ?? a.relative_humidity_2m, vento: leitura?.vento_kmh ?? a.wind_speed_10m, codigo: a.weather_code,
          estacao: leitura?.rotulo ?? null, estacao_km: leitura?.distancia_km ?? null, observado_em: leitura?.quando ?? null,
          hoje_max: leitura?.hoje_max ?? null, hoje_min: leitura?.hoje_min ?? null,
          previsao: (di.time || []).map((t, i) => ({ data: t, tmin: oficial[t]?.[0] ?? di.temperature_2m_min[i], tmax: oficial[t]?.[1] ?? di.temperature_2m_max[i],
            tmax_baixa: faixa[t]?.[0] ?? null, tmax_alta: faixa[t]?.[1] ?? null, fonte: oficial[t] ? "INMET" : "Open-Meteo",
            chuva_mm: di.precipitation_sum[i], prob_chuva: di.precipitation_probability_max[i], codigo: di.weather_code[i] })) };
      } catch (_) { return null; }
    });
    salvarConfig({ ...cfg, cidades: cfg.cidades }); // keep geocoded coordinates
    const ok = res.filter(Boolean);
    if (!ok.length && cfg.cidades.length) throw new Error("Open-Meteo indisponível (limite diário ou rede)");
    estado.clima = ok;
    return `${ok.length} cidades`;
  }

  // ---- Avisos INMET ------------------------------------------------------------
  const avisosAtivos = () => cache("inmet", 600e3, async () => {
    const d = await http("https://apiprevmet3.inmet.gov.br/avisos/ativos", { timeout: 40000 });
    return Object.values(d || {}).filter(Array.isArray).flat();
  });
  const textoLista = (v) => {
    const t = String(v || "").trim();
    return t.startsWith("[") && t.endsWith("]") ? t.slice(1, -1).split("', '").map((p) => p.replace(/^['" ]+|['" ]+$/g, "")).filter(Boolean).join(" · ") : t;
  };
  function resumirAviso(a) {
    let geo = null;
    try { geo = JSON.parse(a.poligono || "null"); } catch (_) {}
    return { id: a.id || a.descricao + a.data_inicio, evento: a.descricao || "", severidade: a.severidade || "", cor: a.aviso_cor || "",
      inicio: `${String(a.data_inicio || "").slice(0, 10)} ${a.hora_inicio || ""}`.trim(),
      fim: `${String(a.data_fim || "").slice(0, 10)} ${a.hora_fim || ""}`.trim(),
      riscos: textoLista(a.riscos), instrucoes: textoLista(a.instrucoes), geocodes: String(a.geocodes || ""), poligono: geo };
  }
  async function coletarAvisos(estado) {
    const cfg = config();
    const todos = (await avisosAtivos()).map(resumirAviso);
    const contagem = {};
    for (const a of todos) { const k = `${a.evento} (${a.severidade})`; contagem[k] = (contagem[k] || 0) + 1; }
    const naArea = todos.filter((a) => cfg.cidades.some((c) => a.geocodes.includes(c.geocodigo)))
      .map((a) => ({ ...a, cidades: cfg.cidades.filter((c) => a.geocodes.includes(c.geocodigo)).map((c) => c.nome), poligono: undefined }));
    estado.avisos = { total: todos.length, resumo: Object.entries(contagem).sort((a, b) => b[1] - a[1]).slice(0, 8), na_area: naArea };
    return `${todos.length} avisos vigentes, ${naArea.length} nas suas cidades`;
  }

  // ---- Terremotos (USGS) -------------------------------------------------------
  async function coletarTerremotos(estado) {
    const d = await http("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson");
    estado.terremotos = (d.features || []).map((f) => ({ magnitude: f.properties.mag, local: f.properties.place,
      quando: new Date(f.properties.time).toISOString(), link: f.properties.url, tsunami: !!f.properties.tsunami }))
      .sort((a, b) => b.magnitude - a.magnitude).slice(0, 15);
    return `${estado.terremotos.length} terremotos`;
  }

  const ETAPAS = { noticias: coletarNoticias, enso: coletarEnso, arboviroses: coletarArbo, alimentos: coletarAlimentos,
    cambio: coletarCambio, clima: coletarClima, avisos_inmet: coletarAvisos, terremotos: coletarTerremotos };

  async function coletarTudo(aoProgredir) {
    const estado = store.get("estado", {});
    estado.coletas = estado.coletas || {};
    await Promise.all(Object.entries(ETAPAS).map(async ([nome, fn]) => {
      const t0 = Date.now();
      try {
        const msg = await fn(estado);
        estado.coletas[nome] = { ok: true, mensagem: msg, quando: new Date().toISOString(), ms: Date.now() - t0 };
      } catch (e) {
        estado.coletas[nome] = { ...(estado.coletas[nome] || {}), ok: false, mensagem: String(e.message || e), quando: new Date().toISOString() };
      }
      if (aoProgredir) aoProgredir(nome, estado.coletas[nome]);
    }));
    estado.atualizado_em = new Date().toISOString();
    store.set("estado", estado);
    return estado;
  }

  // ---- Panel view (same shape as the server's /api/painel) -------------------
  function filtrar(noticias, f = {}) {
    const termos = (f.termos || []).map(norm).filter(Boolean), excluir = (f.excluir || []).map(norm).filter(Boolean);
    const min = PESO[f.nivel_minimo || "normal"];
    return noticias.filter((n) => {
      if (f.escopo && f.escopo !== "todos" && n.escopo !== f.escopo) return false;
      if (f.categorias && f.categorias.length && !f.categorias.includes(n.categoria)) return false;
      if (PESO[n.nivel] < min) return false;
      const alvo = norm(n.titulo + " " + (f.apenas_titulo ? "" : n.resumo));
      if (termos.length && !termos.some((t) => alvo.includes(t))) return false;
      return !excluir.some((t) => alvo.includes(t));
    });
  }
  const separar = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);
  function painel(filtro = {}) {
    const estado = store.get("estado", {});
    const cfg = config();
    const noticias = estado.noticias || [];
    const contagem = { normal: 0, alto: 0, critico: 0 };
    for (const n of noticias) contagem[n.nivel] = (contagem[n.nivel] || 0) + 1;
    const surtos = filtrar(noticias, { termos: D.TERMOS_SURTO, categorias: ["saude", "epidemias"], nivel_minimo: "alto" });
    return {
      atualizado_em: estado.atualizado_em, contagem,
      criticos: noticias.filter((n) => n.nivel === "critico"),
      surtos: surtos.slice(0, 30),
      feed: filtrar(noticias, { termos: separar(filtro.q), escopo: filtro.escopo, categorias: filtro.categoria ? [filtro.categoria] : [],
        nivel_minimo: filtro.nivel }).slice(0, 300),
      temas: cfg.temas.map((t) => ({ ...t, noticias: filtrar(noticias, { termos: separar(t.termos), excluir: separar(t.excluir),
        escopo: t.escopo, categorias: t.categorias, nivel_minimo: t.nivel_minimo }).slice(0, 200) })),
      enso: estado.enso || { oni: [], semanal: [] },
      arboviroses: estado.arboviroses || [],
      clima: estado.clima || [],
      avisos: estado.avisos || { total: 0, resumo: [], na_area: [] },
      alimentos: estado.alimentos || { mes: "", itens: [] },
      cambio: estado.cambio || { atual: [], usd_brl: [] },
      terremotos: estado.terremotos || [],
      coletas: estado.coletas || {},
      precos: precos(),
    };
  }

  // ---- Own market price survey (local) ---------------------------------------
  function precos() {
    const lista = store.get("precos", []);
    const limite = Date.now() - 30 * 86400e3;
    const grupos = {};
    for (const p of lista) {
      if (new Date(p.data).getTime() < limite) continue;
      const k = norm(p.produto) + "|" + p.unidade;
      (grupos[k] ||= { produto: p.produto, unidade: p.unidade, valores: [], mercados: new Set() });
      grupos[k].valores.push(p.preco); grupos[k].mercados.add(norm(p.mercado));
    }
    const medias = Object.values(grupos).map((g) => ({ produto: g.produto, unidade: g.unidade,
      media: g.valores.reduce((a, b) => a + b, 0) / g.valores.length, minimo: Math.min(...g.valores),
      maximo: Math.max(...g.valores), mercados: g.mercados.size })).sort((a, b) => a.produto.localeCompare(b.produto));
    return { cidade: config().cidades[0] ? `${config().cidades[0].nome}/${config().cidades[0].uf}` : "", medias, registros: lista.length };
  }
  function registrarPreco(p) {
    const preco = parseFloat(String(p.preco).replace(",", "."));
    if (!p.produto || !p.mercado || !(preco > 0)) throw new Error("Preencha produto, mercado e preço.");
    const lista = store.get("precos", []);
    lista.push({ produto: p.produto.trim(), mercado: p.mercado.trim(), preco, unidade: (p.unidade || "un").trim(),
      data: p.data || new Date().toISOString().slice(0, 10) });
    store.set("precos", lista.slice(-2000));
  }

  // ---- Local climate radar (neighbourhood level) -----------------------------
  async function nominatim(params) {
    const ultimo = memo.get("nominatim:t")?.v || 0;
    const espera = 1100 - (Date.now() - ultimo);
    if (espera > 0) await new Promise((ok) => setTimeout(ok, espera));
    memo.set("nominatim:t", { t: 0, v: Date.now() });
    const r = await http("https://nominatim.openstreetmap.org/search", { tentativas: 1,
      params: { format: "jsonv2", addressdetails: 1, countrycodes: "br", ...params }, headers: { "User-Agent": UA } });
    return Array.isArray(r) ? r : [];
  }
  function geocodigoIbge(cidade, uf) {
    const m = (D.MUNICIPIOS[uf] || []).find(([, n]) => norm(n) === norm(cidade));
    return m ? m[0] : "";
  }
  async function localizar({ uf, cidade, bairro, lat, lon }) {
    const geocodigo = geocodigoIbge(cidade, uf);
    if (lat != null && lon != null) {
      return { lat, lon, nome: `Ponto ${lat.toFixed(5)}, ${lon.toFixed(5)}` + (cidade ? ` — ${cidade}/${uf}` : ""),
        municipio: cidade, uf, geocodigo, fonte: "coordenada informada", precisao: "ponto" };
    }
    const chave = ["local", norm(cidade), uf, norm(bairro)].join("|");
    const guardado = store.get(chave);
    if (guardado && Date.now() - guardado.t < 7 * 86400e3) return guardado.v;
    const estado = D.UF_NOMES[uf] || uf;
    let local = null;
    if (bairro) {
      try {
        for (const r of await nominatim({ q: `${bairro}, ${cidade}, ${estado}`, limit: 5 })) {
          const end = r.address || {};
          if (["city", "town", "municipality", "village", "city_district"].some((k) => norm(end[k]) === norm(cidade))) {
            local = { lat: +r.lat, lon: +r.lon, fonte: "OpenStreetMap (Nominatim)",
              precisao: ["suburb", "neighbourhood", "quarter", "city_block"].includes(r.addresstype) ? "bairro" : "rua" };
            break;
          }
        }
      } catch (_) {}
      if (!local) {
        try {
          const d = await http("https://photon.komoot.io/api/", { params: { q: `${bairro} ${cidade}`, limit: 30 }, headers: { "User-Agent": UA }, tentativas: 1 });
          const pts = (d.features || []).filter((f) => norm(f.properties.city) === norm(cidade)
            && (norm(f.properties.district) + " " + norm(f.properties.name)).includes(norm(bairro))).map((f) => f.geometry.coordinates);
          if (pts.length) local = { lat: pts.reduce((s, p) => s + p[1], 0) / pts.length, lon: pts.reduce((s, p) => s + p[0], 0) / pts.length,
            fonte: `OpenStreetMap (Photon, ${pts.length} referências)`, precisao: "bairro" };
        } catch (_) {}
      }
    }
    if (local) {
      local = { ...local, nome: `${bairro}, ${cidade}/${uf}`, municipio: cidade, uf, geocodigo };
      store.set(chave, { t: Date.now(), v: local });
      return local;
    }
    const c = await coordenadasCidade({ nome: cidade, uf, geocodigo });
    return { lat: c.lat, lon: c.lon, nome: `${cidade}/${uf}` + (bairro ? ` (bairro '${bairro}' não encontrado)` : ""),
      municipio: cidade, uf, geocodigo, fonte: "Open-Meteo Geocoding (GeoNames)", precisao: "municipio" };
  }
  async function listarBairros(cidade, uf) {
    const chave = ["bairros", norm(cidade), uf].join("|");
    const g = store.get(chave);
    if (g && Date.now() - g.t < 7 * 86400e3 && g.v.length) return g.v;
    const q = `[out:json][timeout:25];area["boundary"="administrative"]["admin_level"="8"]["name"="${cidade.replace(/"/g, "")}"]->.a;`
      + 'nwr["place"~"^(suburb|neighbourhood|quarter)$"](area.a);out center tags;';
    for (const url of ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]) {
      try {
        const d = await http(url, { params: { data: q }, headers: { "User-Agent": UA }, timeout: 30000, tentativas: 1 });
        const m = new Map();
        for (const e of d.elements || []) { const n = e.tags?.name, c = e.center || e; if (n && c.lat != null) m.set(n, { nome: n, lat: c.lat, lon: c.lon }); }
        const v = [...m.values()].sort((a, b) => norm(a.nome).localeCompare(norm(b.nome)));
        store.set(chave, { t: Date.now(), v });
        return v;
      } catch (_) {}
    }
    return [];
  }
  async function observacao(lat, lon) {
    const bbox = [lat - 2.2, lon - 2.2, lat + 2.2, lon + 2.2].map((v) => v.toFixed(2)).join(",");
    const d = await http("https://aviationweather.gov/api/data/metar", { params: { bbox, format: "json", hours: 3 } });
    if (!Array.isArray(d) || !d.length) return null;
    const ult = {};
    for (const m of d) if (!ult[m.icaoId] || (m.obsTime || 0) > (ult[m.icaoId].obsTime || 0)) ult[m.icaoId] = m;
    const m = Object.values(ult).sort((a, b) => distanciaKm(lat, lon, a.lat, a.lon) - distanciaKm(lat, lon, b.lat, b.lon))[0];
    const kmh = (v) => (typeof v === "number" ? Math.round(v * 1.852 * 10) / 10 : null);
    return { estacao: m.icaoId, nome: m.name || "", distancia_km: Math.round(distanciaKm(lat, lon, m.lat, m.lon) * 10) / 10,
      quando: new Date((m.obsTime || 0) * 1000).toISOString(), temperatura: m.temp, ponto_orvalho: m.dewp,
      vento_kmh: kmh(m.wspd), rajada_kmh: kmh(m.wgst), fenomeno: m.wxString || "", bruto: m.rawOb || "", lat: m.lat, lon: m.lon };
  }
  async function previsao(lat, lon) {
    const [url, params] = openMeteo("https://api.open-meteo.com/v1/forecast", {
      latitude: lat.toFixed(4), longitude: lon.toFixed(4), hourly: VARIAVEIS_HORA,
      daily: "temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,precipitation_sum",
      models: "best_match," + Object.keys(MODELOS).join(","), timezone: "auto", forecast_days: 3 });
    const d = await http(url, { params, timeout: 40000 });
    d.fonte = "Open-Meteo (ECMWF, ICON, GFS)";
    return d;
  }
  async function previsaoMetNorway(lat, lon) {
    const d = await http("https://api.met.no/weatherapi/locationforecast/2.0/complete",
      { params: { lat: lat.toFixed(4), lon: lon.toFixed(4) }, headers: { "User-Agent": UA }, timeout: 40000 });
    const off = Math.max(-5, Math.min(-2, Math.round(lon / 15)));
    const h = Object.fromEntries(["time", ...VARIAVEIS_HORA.split(",")].map((k) => [k, []]));
    for (const it of (d.properties?.timeseries || []).slice(0, 72)) {
      const t = new Date(new Date(it.time).getTime() + off * 3600e3).toISOString().slice(0, 13) + ":00";
      const inst = it.data.instant.details, prox = it.data.next_1_hours || {};
      const simb = prox.summary?.symbol_code || "";
      h.time.push(t); h.temperature_2m.push(inst.air_temperature ?? null);
      h.apparent_temperature.push(inst.apparent_air_temperature ?? inst.air_temperature ?? null);
      h.relative_humidity_2m.push(inst.relative_humidity ?? null);
      h.wind_speed_10m.push(inst.wind_speed != null ? Math.round(inst.wind_speed * 36) / 10 : null);
      h.wind_gusts_10m.push(null); h.precipitation.push(prox.details?.precipitation_amount ?? null);
      h.precipitation_probability.push(null); h.cape.push(null);
      h.weather_code.push(simb.includes("thunder") ? 95 : 0); h.uv_index.push(inst.ultraviolet_index_clear_sky ?? null);
    }
    return { utc_offset_seconds: off * 3600, hourly: h, daily: {}, elevation: null,
      fonte: "MET Norway (reserva — sem rajadas, CAPE ou consenso de modelos)" };
  }
  const serie = (d, bloco, v, modelo = "best_match") => [...((d[bloco] || {})[`${v}_${modelo}`] || (d[bloco] || {})[v] || [])];
  function proximasHoras(d, horas = 48) {
    const tempos = serie(d, "hourly", "time");
    const agora = new Date(Date.now() + (d.utc_offset_seconds || 0) * 1000).toISOString().slice(0, 13) + ":00";
    let ini = tempos.findIndex((t) => t >= agora); if (ini < 0) ini = 0;
    const out = { time: tempos.slice(ini, ini + horas) };
    for (const v of VARIAVEIS_HORA.split(",")) out[v] = serie(d, "hourly", v).slice(ini, ini + horas);
    return out;
  }
  function consenso(d) {
    return serie(d, "daily", "time").map((dia, i) => {
      const linha = { dia, modelos: {} };
      for (const [k, nome] of Object.entries(MODELOS)) {
        const v = (x) => serie(d, "daily", x, k)[i] ?? null;
        linha.modelos[nome] = { tmax: v("temperature_2m_max"), tmin: v("temperature_2m_min"), rajada: v("wind_gusts_10m_max"), chuva: v("precipitation_sum") };
      }
      for (const c of ["tmax", "rajada", "chuva"]) {
        const vs = Object.values(linha.modelos).map((m) => m[c]).filter((x) => x != null);
        linha[c + "_spread"] = vs.length ? Math.round((Math.max(...vs) - Math.min(...vs)) * 10) / 10 : null;
        linha[c + "_max"] = vs.length ? Math.max(...vs) : null;
      }
      return linha;
    });
  }
  function pico(t, vs) {
    let m = null;
    (vs || []).forEach((v, i) => { if (v != null && (m == null || v > m[0])) m = [v, t[i]]; });
    return m || [0, ""];
  }
  function avaliarRiscos(h, cons) {
    const t = h.time || [], r = [];
    const R = (tipo, nivel, valor, quando, criterio) => r.push({ tipo, nivel, rotulo: NIVEIS[nivel], valor, quando, criterio });
    const [sens, qs] = pico(t, h.apparent_temperature), [tmax] = pico(t, h.temperature_2m);
    R("calor", sens >= 54 ? 3 : sens >= 41 ? 2 : sens >= 32 || tmax >= 35 ? 1 : 0, `sensação ${sens.toFixed(0)}°C · máx ${tmax.toFixed(0)}°C`, qs,
      "Índice de calor (NOAA): 32-41 atenção · 41-54 perigo · >54 perigo extremo");
    const temRaj = (h.wind_gusts_10m || []).some((v) => v != null);
    const [raj, qr] = pico(t, temRaj ? h.wind_gusts_10m : h.wind_speed_10m);
    const rajMod = cons.length ? Math.max(...cons.map((c) => c.rajada_max || 0)) : 0;
    const pior = Math.max(raj, rajMod);
    R("ventania", pior >= 100 ? 3 : pior >= 60 ? 2 : pior >= 40 ? 1 : 0,
      temRaj ? `rajada ${raj.toFixed(0)} km/h (pior modelo ${rajMod.toFixed(0)})` : `vento ${raj.toFixed(0)} km/h (rajadas indisponíveis)`, qr,
      "INMET: 40-60 km/h perigo potencial · 60-100 perigo · >100 grande perigo");
    const [cape, qc] = pico(t, h.cape);
    const wc = h.weather_code || [];
    const trov = t.filter((_, i) => [95, 96, 99].includes(wc[i]));
    const gran = wc.some((c) => c === 96 || c === 99);
    R("tempestade", gran && cape >= 2500 ? 3 : (trov.length && cape >= 1500) || cape >= 2500 ? 2 : trov.length || cape >= 1000 ? 1 : 0,
      `CAPE ${cape.toFixed(0)} J/kg · ${trov.length}h com trovoada` + (gran ? " · granizo" : ""), trov[0] || qc,
      "Energia convectiva (CAPE) >1000 favorece tempestades; >2500 severas");
    const [ch, qch] = pico(t, h.precipitation);
    const chDia = cons.length ? Math.max(...cons.map((c) => c.chuva_max || 0)) : 0;
    R("chuva", ch > 60 || chDia > 100 ? 3 : ch >= 30 || chDia >= 50 ? 2 : ch >= 20 || chDia >= 30 ? 1 : 0,
      `${ch.toFixed(1)} mm/h · até ${chDia.toFixed(0)} mm/dia`, qch, "INMET: 20-30 mm/h perigo potencial · 30-60 perigo · >60 grande perigo");
    let umin = [100, ""];
    (h.relative_humidity_2m || []).forEach((u, i) => { if (u != null && u < umin[0]) umin = [u, t[i]]; });
    R("umidade", umin[0] < 12 ? 3 : umin[0] < 20 ? 2 : umin[0] <= 30 ? 1 : 0, `mínima ${umin[0].toFixed(0)}%`, umin[1],
      "INMET: 30-20% perigo potencial · 20-12% perigo · <12% grande perigo");
    return r;
  }
  const focosBrasil = () => cache("focos", 3600e3, async () => {
    const hoje = new Date();
    for (const dia of [hoje, new Date(hoje.getTime() - 86400e3)]) {
      const ymd = dia.toISOString().slice(0, 10).replace(/-/g, "");
      try {
        const csv = await http(`https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_${ymd}.csv`,
          { tipo: "text", timeout: 60000, tentativas: 1 });
        const [cab, ...linhas] = csv.trim().split(/\r?\n/);
        const col = cab.split(",");
        const ix = (n) => col.indexOf(n);
        const [iLat, iLon, iData, iSat, iRisco, iDias] = ["lat", "lon", "data_hora_gmt", "satelite", "risco_fogo", "numero_dias_sem_chuva"].map(ix);
        const out = linhas.map((l) => l.split(",")).map((c) => [+c[iLat], +c[iLon], c[iData] || "", c[iSat] || "", c[iRisco] || null, c[iDias] || null])
          .filter((f) => !isNaN(f[0]) && !isNaN(f[1]));
        if (out.length) return out;
      } catch (_) {}
    }
    return [];
  });
  async function focosProximos(lat, lon, raio = 50) {
    return (await focosBrasil()).filter((f) => Math.abs(f[0] - lat) <= 1 && Math.abs(f[1] - lon) <= 1)
      .map((f) => ({ lat: f[0], lon: f[1], distancia_km: Math.round(distanciaKm(lat, lon, f[0], f[1]) * 10) / 10, quando: f[2],
        satelite: f[3], risco_fogo: f[4], dias_sem_chuva: f[5] })).filter((f) => f.distancia_km <= raio)
      .sort((a, b) => a.distancia_km - b.distancia_km);
  }
  async function relatorioLocal(sel) {
    const local = await localizar(sel);
    const nomes = ["inmet", "metar", "previsao", "focos", "estacao"];
    const res = await Promise.allSettled([avisosAtivos(), observacao(local.lat, local.lon), previsao(local.lat, local.lon), focosProximos(local.lat, local.lon), medicaoLocal(local.geocodigo, local.lat, local.lon)]);
    const [avisos, obs, prev0, focos, estacao] = res.map((r) => (r.status === "fulfilled" ? r.value : null));
    let falhas = nomes.filter((_, i) => res[i].status === "rejected");
    let prev = prev0;
    if (!prev) {
      try { prev = await previsaoMetNorway(local.lat, local.lon); falhas = falhas.map((f) => (f === "previsao" ? "open-meteo (usando MET Norway)" : f)); }
      catch (_) { prev = null; }
    }
    const horas = prev ? proximasHoras(prev) : {};
    const cons = prev ? consenso(prev) : [];
    const ordem = { "Grande Perigo": 0, Perigo: 1, "Perigo Potencial": 2 };
    const avisosLocal = (avisos || []).map((a) => {
      const x = resumirAviso(a);
      x.dentro_do_poligono = pontoNoPoligono(local.lat, local.lon, x.poligono);
      return x;
    }).filter((a) => a.dentro_do_poligono || (local.geocodigo && a.geocodes.includes(local.geocodigo)))
      .sort((a, b) => (ordem[a.severidade] ?? 3) - (ordem[b.severidade] ?? 3));
    const r = { local, avisos: avisosLocal, observacao: obs, estacao, horas, consenso: cons,
      riscos: horas.time && horas.time.length ? avaliarRiscos(horas, cons) : [], focos: focos || [],
      elevacao_m: prev ? prev.elevation : null, fonte_previsao: prev ? prev.fonte : "", falhas, gerado_em: new Date().toISOString() };
    store.set("clima_ultimo", r);
    return r;
  }

  window.ArgosMotor = { config, salvarConfig, coletarTudo, painel, registrarPreco, relatorioLocal, listarBairros,
    classificar, parseEstacao, parseFaixa, parseGuiaClima, parsePrevisaoInmet, parseFeed, parseOni, parseSemanal, parseDiscussao, pontoNoPoligono, avaliarRiscos, store, ETAPAS: Object.keys(ETAPAS) };
})();
