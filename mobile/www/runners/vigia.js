// ARGOS mobile — background watcher ("vigia").
//
// Runs in Capacitor Background Runner's headless JS engine (Android WorkManager,
// every ~15 min even with the app closed). No DOM here: only fetch, CapacitorKV and
// CapacitorNotifications. The same code is loaded in the WebView for the browser
// preview, where KV/notifications are shimmed by app.js.
//
// Policy:
//   URGENTE  (channel argos_urgente — sound + vibration, any time)
//     - INMET warning "Perigo"/"Grande Perigo" covering a monitored city or the radar point
//     - imminent model risk (next 12 h) at level Perigo+ at the radar point
//     - critical outbreak / health emergency news (WHO, ECDC, UN, Agência Brasil saúde)
//     - news matching a theme marked with 🔔 (and all critical news, if enabled)
//   BOLETIM  (channel argos_boletim — once a day, from the configured hour, default 07:00)
//     - forecast for each city, INMET warnings, arboviruses, El Niño, USD/BRL, top critical news
/* global CapacitorKV, CapacitorNotifications */
var ArgosVigia = (function () {
  "use strict";
  var UA = "ARGOS-mobile/1.0 (+https://github.com/viniciusandradde/mcp-brasil)";
  var SEVERO = { "Perigo": 2, "Grande Perigo": 3 };
  var FEEDS_URGENTES = [
    ["OMS", "https://www.who.int/rss-feeds/news-english.xml"],
    ["ECDC", "https://www.ecdc.europa.eu/en/taxonomy/term/1307/feed"],
    ["ONU saúde", "https://news.un.org/feed/subscribe/en/news/topic/health/feed/rss.xml"],
    ["Agência Brasil saúde", "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml"],
    ["Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"],
    ["g1", "https://g1.globo.com/rss/g1/"],
  ];

  // ---- KV helpers ------------------------------------------------------------
  function kvGet(k, padrao) {
    try { var r = CapacitorKV.get(k); var v = r && r.value; return v ? JSON.parse(v) : padrao; }
    catch (e) { return padrao; }
  }
  function kvSet(k, v) { try { CapacitorKV.set(k, JSON.stringify(v)); } catch (e) { /* ignore */ } }

  // ---- utils ------------------------------------------------------------------
  function norm(t) {
    var s = String(t || "");
    if (s.normalize) s = s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    return s.toLowerCase();
  }
  function hash(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h % 2000000000) + 1000;
  }
  function qs(p) {
    return Object.keys(p).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(p[k]); }).join("&");
  }
  function getJson(url, headers) {
    return fetch(url, { headers: headers || {} }).then(function (r) {
      if (r.status && r.status >= 400) throw new Error("HTTP " + r.status);
      return r.text();
    }).then(function (t) { return JSON.parse(t); });
  }
  function getText(url) {
    return fetch(url, { headers: { "User-Agent": UA } }).then(function (r) {
      if (r.status && r.status >= 400) throw new Error("HTTP " + r.status);
      return r.text();
    });
  }
  function seguro(p, padrao) { return p.then(function (v) { return v; }, function () { return padrao; }); }
  function agoraLocal(cfg) { return new Date(Date.now() - (cfg.tzOffsetMin || 240) * 60000); } // use UTC getters
  function hojeLocal(cfg) { return agoraLocal(cfg).toISOString().slice(0, 10); }
  function num(v, d) { return v == null || isNaN(v) ? "—" : Number(v).toFixed(d == null ? 0 : d).replace(".", ","); }
  function omUrl(cfg, url) {
    return cfg.openMeteoKey ? url.replace("https://api.", "https://customer-api.") : url;
  }
  function omParams(cfg, p) { if (cfg.openMeteoKey) p.apikey = cfg.openMeteoKey; return p; }

  function noAnel(lon, lat, anel) {
    var dentro = false;
    for (var i = 0, j = anel.length - 1; i < anel.length; j = i++) {
      var xi = anel[i][0], yi = anel[i][1], xj = anel[j][0], yj = anel[j][1];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi) dentro = !dentro;
    }
    return dentro;
  }
  function noPoligono(lat, lon, geo) {
    if (!geo) return false;
    var polis = geo.type === "Polygon" ? [geo.coordinates || []] : geo.type === "MultiPolygon" ? geo.coordinates || [] : [];
    return polis.some(function (p) {
      return p.length && noAnel(lon, lat, p[0]) && !p.slice(1).some(function (b) { return noAnel(lon, lat, b); });
    });
  }

  // ---- RSS without DOM --------------------------------------------------------
  function limpar(t) {
    return String(t || "").replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1").replace(/<[^>]+>/g, " ")
      .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
      .replace(/&#39;|&apos;/g, "'").replace(/&#(\d+);/g, function (_, n) { return String.fromCharCode(+n); })
      .replace(/\s+/g, " ").trim();
  }
  function tag(bloco, nome) {
    var m = bloco.match(new RegExp("<" + nome + "(?:\\s[^>]*)?>([\\s\\S]*?)</" + nome + ">", "i"));
    return m ? limpar(m[1]) : "";
  }
  function parseRss(xml, fonte) {
    var itens = xml.match(/<item[\s>][\s\S]*?<\/item>|<entry[\s>][\s\S]*?<\/entry>/gi) || [];
    return itens.slice(0, 30).map(function (b) {
      var link = tag(b, "link");
      if (!link) { var m = b.match(/<link[^>]*href="([^"]+)"/i); link = m ? m[1] : ""; }
      var data = tag(b, "pubDate") || tag(b, "dc:date") || tag(b, "published") || tag(b, "updated");
      var d = data ? new Date(data) : null;
      return { fonte: fonte, titulo: tag(b, "title"), link: link, resumo: tag(b, "description").slice(0, 300),
        quando: d && !isNaN(d.getTime()) ? d.getTime() : Date.now() };
    }).filter(function (n) { return n.titulo && n.link; });
  }

  // ---- checks -------------------------------------------------------------------
  function checarInmet(cfg) {
    return getJson("https://apiprevmet3.inmet.gov.br/avisos/ativos").then(function (d) {
      var todos = [];
      Object.keys(d || {}).forEach(function (k) { if (Array.isArray(d[k])) todos = todos.concat(d[k]); });
      var eventos = [], naArea = [];
      todos.forEach(function (a) {
        var geocodes = String(a.geocodes || "");
        var cidades = (cfg.cidades || []).filter(function (c) { return geocodes.indexOf(c.geocodigo) >= 0; })
          .map(function (c) { return c.nome; });
        var ponto = cfg.ponto, noPonto = false;
        if (ponto && ponto.lat != null) {
          try { noPonto = noPoligono(ponto.lat, ponto.lon, JSON.parse(a.poligono || "null")); } catch (e) { noPonto = false; }
        }
        if (!cidades.length && !noPonto) return;
        naArea.push(a);
        if (!SEVERO[a.severidade] || !cfg.notificar.inmet) return;
        var onde = noPonto ? ponto.nome + (cidades.length ? " · " + cidades.join(", ") : "") : cidades.join(", ");
        eventos.push({ id: "inmet:" + (a.id || a.descricao + a.data_inicio) , urgente: true,
          titulo: "⚠ INMET " + String(a.severidade).toUpperCase() + ": " + a.descricao,
          texto: onde + " · " + String(a.data_inicio || "").slice(0, 10) + " " + (a.hora_inicio || "") + " → " +
            String(a.data_fim || "").slice(0, 10) + " " + (a.hora_fim || "") + ". " +
            String(a.riscos || "").replace(/[[\]']/g, "").slice(0, 220) });
      });
      return { eventos: eventos, naArea: naArea };
    });
  }

  function riscosIminentes(cfg) {
    var p = cfg.ponto || cfg.cidades[0];
    if (!p || p.lat == null || !cfg.notificar.riscoLocal) return Promise.resolve([]);
    var url = omUrl(cfg, "https://api.open-meteo.com/v1/forecast") + "?" + qs(omParams(cfg, {
      latitude: p.lat.toFixed(4), longitude: p.lon.toFixed(4), timezone: "auto", forecast_hours: 12,
      hourly: "apparent_temperature,wind_gusts_10m,precipitation,cape,weather_code" }));
    return getJson(url).then(function (d) {
      var h = d.hourly || {}, t = h.time || [], ev = [], dia = hojeLocal(cfg);
      function pior(serie) {
        var m = null;
        (serie || []).forEach(function (v, i) { if (v != null && (!m || v > m[0])) m = [v, t[i]]; });
        return m || [0, ""];
      }
      var raj = pior(h.wind_gusts_10m), ch = pior(h.precipitation), cal = pior(h.apparent_temperature), cape = pior(h.cape);
      var trov = t.filter(function (_, i) { return [95, 96, 99].indexOf((h.weather_code || [])[i]) >= 0; });
      var nome = p.nome || "seu local";
      var hora = function (x) { return x ? x.slice(11, 16) : ""; };
      if (raj[0] >= 60) ev.push({ id: "risco:vento:" + dia, urgente: true, titulo: "💨 VENTANIA " + (raj[0] >= 100 ? "GRANDE PERIGO" : "PERIGO") + " em " + nome,
        texto: "Rajadas de até " + num(raj[0]) + " km/h por volta das " + hora(raj[1]) + ". Recolha objetos soltos e evite árvores." });
      if (ch[0] >= 30) ev.push({ id: "risco:chuva:" + dia, urgente: true, titulo: "🌧 CHUVA FORTE " + (ch[0] > 60 ? "GRANDE PERIGO" : "PERIGO") + " em " + nome,
        texto: num(ch[0], 1) + " mm/h previstos por volta das " + hora(ch[1]) + ". Risco de alagamentos." });
      if (cal[0] >= 41) ev.push({ id: "risco:calor:" + dia, urgente: true, titulo: "🔥 CALOR PERIGOSO em " + nome,
        texto: "Sensação térmica de " + num(cal[0]) + " °C por volta das " + hora(cal[1]) + ". Hidrate-se e evite sol forte." });
      if (trov.length && cape[0] >= 1500) ev.push({ id: "risco:tempestade:" + dia, urgente: true, titulo: "⛈ TEMPESTADE em " + nome,
        texto: "Trovoadas a partir das " + hora(trov[0]) + " · CAPE " + num(cape[0]) + " J/kg" +
          ((h.weather_code || []).some(function (c) { return c === 96 || c === 99; }) ? " · risco de granizo" : "") + "." });
      return ev;
    });
  }

  function noticiasUrgentes(cfg) {
    var crit = new RegExp("\\b(?:" + (cfg.criterios.CRITICO || []).join("|") + ")\\b");
    var surto = (cfg.criterios.TERMOS_SURTO || []).map(norm);
    var temas = (cfg.temas || []).filter(function (t) { return t.alertar; });
    return Promise.all(FEEDS_URGENTES.map(function (f) {
      return seguro(getText(f[1]).then(function (x) { return parseRss(x, f[0]); }), []);
    })).then(function (listas) {
      var ev = [], limite = Date.now() - 6 * 3600e3, todas = [];
      listas.forEach(function (l) { todas = todas.concat(l); });
      todas.forEach(function (n) {
        if (n.quando < limite) return;
        var alvo = norm(n.titulo + " " + n.resumo);
        var critico = crit.test(alvo);
        var saude = ["OMS", "ECDC", "ONU saúde", "Agência Brasil saúde"].indexOf(n.fonte) >= 0;
        var tema = temas.filter(function (t) {
          var termos = String(t.termos || "").split(",").map(norm).filter(Boolean);
          var excl = String(t.excluir || "").split(",").map(norm).filter(Boolean);
          return termos.some(function (x) { return alvo.indexOf(x) >= 0; }) && !excl.some(function (x) { return alvo.indexOf(x) >= 0; });
        })[0];
        var ehSurto = saude && critico && surto.some(function (x) { return alvo.indexOf(x) >= 0; });
        if (tema || (ehSurto && cfg.notificar.surtos) || (critico && cfg.notificar.criticos)) {
          ev.push({ id: "news:" + n.link, urgente: true,
            titulo: (tema ? "🔔 " + tema.nome : ehSurto ? "☣ SURTO / EMERGÊNCIA" : "■ CRÍTICO") + " · " + n.fonte,
            texto: n.titulo });
        }
      });
      return { eventos: ev, noticias: todas };
    });
  }

  // ---- morning bulletin ---------------------------------------------------------
  var TEMPO = { 0: "céu limpo", 1: "sol", 2: "parc. nublado", 3: "nublado", 45: "neblina", 51: "garoa", 53: "garoa",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 80: "pancadas", 81: "pancadas fortes", 82: "pancadas violentas",
    95: "trovoadas", 96: "trovoadas c/ granizo", 99: "trovoadas c/ granizo" };
  var ARBO = { 1: "verde", 2: "amarelo", 3: "laranja", 4: "VERMELHO" };

  function boletim(cfg, inmet, noticias) {
    var cidades = (cfg.cidades || []).filter(function (c) { return c.lat != null; }).slice(0, 4);
    var ano = agoraLocal(cfg).getUTCFullYear();
    var tarefas = [
      Promise.all(cidades.map(function (c) {
        var url = omUrl(cfg, "https://api.open-meteo.com/v1/forecast") + "?" + qs(omParams(cfg, {
          latitude: c.lat, longitude: c.lon, timezone: "auto", forecast_days: 1,
          daily: "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_gusts_10m_max,weather_code" }));
        return seguro(getJson(url).then(function (d) {
          var x = d.daily || {};
          return "• " + c.nome + ": " + num(x.temperature_2m_min && x.temperature_2m_min[0]) + "–" + num(x.temperature_2m_max && x.temperature_2m_max[0]) +
            "°C, " + (TEMPO[x.weather_code && x.weather_code[0]] || "") + ", chuva " + num(x.precipitation_probability_max && x.precipitation_probability_max[0]) +
            "% (" + num(x.precipitation_sum && x.precipitation_sum[0], 1) + " mm), rajadas " + num(x.wind_gusts_10m_max && x.wind_gusts_10m_max[0]) + " km/h";
        }), "• " + c.nome + ": previsão indisponível");
      })),
      Promise.all((cfg.cidades || []).slice(0, 4).map(function (c) {
        return Promise.all(["dengue", "chikungunya", "zika"].map(function (doenca) {
          return seguro(getJson("https://info.dengue.mat.br/api/alertcity?" + qs({ geocode: c.geocodigo, disease: doenca, format: "json",
            ew_start: 1, ew_end: 53, ey_start: ano, ey_end: ano })).then(function (l) {
            if (!Array.isArray(l) || !l.length) return null;
            l.sort(function (a, b) { return (a.SE || 0) - (b.SE || 0); });
            var u = l[l.length - 1];
            return { doenca: doenca, nivel: u.nivel, rt: u.Rt };
          }), null);
        })).then(function (rs) {
          var ok = rs.filter(Boolean).filter(function (r) { return r.nivel >= 2; });
          return ok.length ? "• " + c.nome + ": " + ok.map(function (r) {
            return r.doenca + " " + ARBO[r.nivel] + (r.rt > 1 ? " (Rt " + num(r.rt, 2) + " ▲)" : "");
          }).join(", ") : null;
        });
      })),
      seguro(getText("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt").then(function (t) {
        var linhas = t.trim().split(/\r?\n/), u = linhas[linhas.length - 1].trim().split(/\s+/);
        var v = parseFloat(u[u.length - 1]);
        return "El Niño: ONI " + u[0] + " " + u[1] + " = " + (v > 0 ? "+" : "") + num(v, 2) + " °C" + (v >= 1.5 ? " (forte)" : v >= 0.5 ? "" : " (neutro/La Niña)");
      }), null),
      seguro(getJson("https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL").then(function (d) {
        return "Dólar: R$ " + num(d.rates.BRL, 4) + " (" + d.date + ")";
      }), null),
    ];
    return Promise.all(tarefas).then(function (r) {
      var avisos = inmet ? inmet.naArea : [];
      var sev = {};
      avisos.forEach(function (a) { var k = a.descricao + " (" + a.severidade + ")"; sev[k] = (sev[k] || 0) + 1; });
      var crit = new RegExp("\\b(?:" + (cfg.criterios.CRITICO || []).join("|") + ")\\b");
      var criticas = (noticias || []).filter(function (n) { return n.quando > Date.now() - 24 * 3600e3 && crit.test(norm(n.titulo + " " + n.resumo)); });
      var linhas = ["CLIMA HOJE"].concat(r[0]);
      linhas.push("AVISOS INMET: " + (avisos.length ? Object.keys(sev).map(function (k) { return sev[k] + "× " + k; }).join("; ") : "nenhum nas suas cidades"));
      var arbo = r[1].filter(Boolean);
      linhas.push("ARBOVIROSES: " + (arbo.length ? "" : "sem alerta acima de verde"));
      linhas = linhas.concat(arbo);
      if (r[2]) linhas.push(r[2]);
      if (r[3]) linhas.push(r[3]);
      if (criticas.length) {
        linhas.push("CRÍTICOS 24H (" + criticas.length + "):");
        criticas.slice(0, 3).forEach(function (n) { linhas.push("• " + n.titulo.slice(0, 110)); });
      }
      var resumo = (r[0][0] || "").replace("• ", "") + (avisos.length ? " · " + avisos.length + " aviso(s) INMET" : "");
      return { id: "boletim:" + hojeLocal(cfg), urgente: false, titulo: "☀ Boletim ARGOS · " + hojeLocal(cfg).split("-").reverse().join("/"),
        texto: resumo, longo: linhas.join("\n") };
    });
  }

  // ---- main ---------------------------------------------------------------------
  function enviar(eventos) {
    var vistos = kvGet("vistos", {}), agora = Date.now(), novos = [];
    Object.keys(vistos).forEach(function (k) { if (agora - vistos[k] > 8 * 86400e3) delete vistos[k]; });
    eventos.forEach(function (e) { if (!vistos[e.id]) { vistos[e.id] = agora; novos.push(e); } });
    kvSet("vistos", vistos);
    if (novos.length) {
      // Bulletin first, then up to 5 urgent alerts; any excess is grouped into one notification.
      var ordem = novos.filter(function (e) { return !e.urgente; }).concat(novos.filter(function (e) { return e.urgente; }));
      var lote = ordem.slice(0, 6), resto = ordem.slice(6);
      if (resto.length) {
        lote.push({ id: "grupo:" + agora, urgente: true, titulo: "⚠ +" + resto.length + " alertas ARGOS",
          texto: resto.map(function (e) { return e.titulo; }).join(" · ").slice(0, 200),
          longo: resto.map(function (e) { return "• " + e.titulo; }).join("\n") });
      }
      CapacitorNotifications.schedule(lote.map(function (e) {
        return { id: hash(e.id), title: e.titulo, body: e.texto, largeBody: e.longo || e.texto,
          channelId: e.urgente ? "argos_urgente" : "argos_boletim", smallIcon: "ic_stat_argos", autoCancel: true,
          group: e.urgente ? "argos_urgente" : "argos_boletim" };
      }));
    }
    return novos;
  }

  function vigiar(opcoes) {
    var cfg = kvGet("config", null);
    if (!cfg) return Promise.resolve({ enviados: [], motivo: "sem configuração (abra o app)" });
    opcoes = opcoes || {};
    var estado = kvGet("estado_vigia", {});
    var agora = Date.now();
    var precisaNoticias = opcoes.forcar || !estado.noticias || agora - estado.noticias > 25 * 60e3;
    var precisaRisco = opcoes.forcar || !estado.risco || agora - estado.risco > 55 * 60e3;
    var local = agoraLocal(cfg), hora = local.getUTCHours();
    var hoje = hojeLocal(cfg);
    var querBoletim = cfg.notificar.boletim && (opcoes.boletim || (estado.boletim !== hoje && hora >= (cfg.boletimHora || 7) && hora < 12));

    return Promise.all([
      seguro(checarInmet(cfg), null),
      precisaRisco ? seguro(riscosIminentes(cfg), []) : Promise.resolve([]),
      precisaNoticias || querBoletim ? seguro(noticiasUrgentes(cfg), { eventos: [], noticias: [] }) : Promise.resolve({ eventos: [], noticias: [] }),
    ]).then(function (r) {
      var eventos = (r[0] ? r[0].eventos : []).concat(r[1], r[2].eventos);
      if (precisaRisco) estado.risco = agora;
      if (precisaNoticias) estado.noticias = agora;
      var fim = querBoletim
        ? boletim(cfg, r[0], r[2].noticias).then(function (b) {
          if (opcoes.boletim) b.id += ":" + agora; // manual preview always shows
          eventos.push(b); estado.boletim = hoje;
        }, function () { /* bulletin best effort */ })
        : Promise.resolve();
      return fim.then(function () {
        estado.ultima = agora;
        kvSet("estado_vigia", estado);
        var enviados = enviar(eventos);
        kvSet("ultimos_eventos", eventos.slice(-30));
        return { enviados: enviados.length, eventos: eventos.length, quando: new Date(agora).toISOString() };
      });
    });
  }

  return { vigiar: vigiar, parseRss: parseRss, noPoligono: noPoligono };
})();

if (typeof CapacitorKV !== "undefined" && typeof window === "undefined") {
  addEventListener("vigiar", function (resolve, reject) {
    ArgosVigia.vigiar({}).then(resolve, function (e) { reject(String(e)); });
  });
  addEventListener("vigiarAgora", function (resolve, reject, args) {
    ArgosVigia.vigiar({ forcar: true, boletim: !!(args && args.boletim) }).then(resolve, function (e) { reject(String(e)); });
  });
  addEventListener("configurar", function (resolve, reject, args) {
    try { CapacitorKV.set("config", JSON.stringify(args.config)); resolve({ ok: true }); }
    catch (e) { reject(String(e)); }
  });
  addEventListener("ultimos", function (resolve) {
    var r = CapacitorKV.get("ultimos_eventos");
    resolve({ eventos: r && r.value ? JSON.parse(r.value) : [], estado: JSON.parse((CapacitorKV.get("estado_vigia") || {}).value || "{}") });
  });
}
