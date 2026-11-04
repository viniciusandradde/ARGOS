// ARGOS mobile — UI (same hacker look as the web /painel and /clima pages).
(() => {
  "use strict";
  const M = window.ArgosMotor, D = window.ARGOS_DADOS;
  const $ = (id) => document.getElementById(id);
  const VERSAO = "1.1.0";
  const URL_APK = "https://github.com/viniciusandradde/ARGOS/raw/ccr-d79070a6-p6sovy/mobile/releases/argos-ultima.apk";
  const CAP = window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform() ? window.Capacitor : null;
  const P = CAP ? CAP.Plugins : {};
  const RUNNER = "br.com.vsa.argos.vigia";
  const CATS = { geral: "geral", politica: "política", economia: "economia", saude: "saúde", epidemias: "epidemias",
    clima: "clima", desastres: "desastres", justica: "justiça", legislativo: "legislativo", governo: "governo" };
  const NIVEL_COR = { critico: "red", alto: "amber", normal: "dim" };
  const ARBO = { 1: ["green", "■□□□", "VERDE"], 2: ["amber", "■■□□", "AMARELO"], 3: ["amber", "■■■□", "LARANJA"], 4: ["red", "■■■■", "VERMELHO"] };
  const TEMPO = { 0: "céu limpo", 1: "sol", 2: "parc. nublado", 3: "nublado", 45: "neblina", 51: "garoa", 53: "garoa", 61: "chuva fraca",
    63: "chuva", 65: "chuva forte", 80: "pancadas", 81: "pancadas fortes", 82: "pancadas violentas", 95: "trovoadas", 96: "trovoadas c/ granizo", 99: "trovoadas c/ granizo" };
  const SUB = { sala: "// SALA DE SITUAÇÃO", clima: "// RADAR CLIMÁTICO", feed: "// FEED GLOBAL", config: "// CONFIGURAÇÃO" };
  let dados = null, aba = "feed", view = "sala", restante = 0, coletando = false, mapa = null, camadas = null;

  // ---- helpers -----------------------------------------------------------------
  function el(tag, attrs = {}, ...filhos) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "on") for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn);
      else if (k === "class") n.className = v; else n.setAttribute(k, v);
    }
    for (const f of filhos) if (f != null) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
    return n;
  }
  const preencher = (id, ...nos) => $(id).replaceChildren(...nos.flat().filter((n) => n != null));
  const num = (v, d = 2) => v == null || isNaN(v) ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (v) => v == null ? el("span", { class: "dim" }, "—") :
    el("span", { class: v >= 3 ? "red" : v > 0 ? "amber" : v <= -3 ? "cyan" : "green" }, (v > 0 ? "▲ +" : v < 0 ? "▼ " : "  ") + num(v) + "%");
  const hora = (t) => t ? t.slice(8, 10) + "/" + t.slice(5, 7) + " " + t.slice(11, 16) : "";
  const vazio = (t) => el("p", { class: "dim" }, t);
  function atras(iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "min";
    if (s < 86400) return Math.round(s / 3600) + "h";
    return Math.round(s / 86400) + "d";
  }
  function abrir(url) {
    if (P.Browser) P.Browser.open({ url }); else window.open(url, "_blank", "noopener");
  }
  const link = (href, texto) => el("a", { href, on: { click: (e) => { e.preventDefault(); abrir(href); } } }, texto);
  let toastT;
  function toast(t) {
    $("toast").textContent = t; $("toast").classList.remove("hidden");
    clearTimeout(toastT); toastT = setTimeout(() => $("toast").classList.add("hidden"), 6000);
  }
  function spark(valores, cor, w = 300, h = 46, zero = false) {
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`); svg.setAttribute("width", "100%"); svg.setAttribute("height", h);
    valores = valores.filter((v) => v != null);
    if (valores.length < 2) return svg;
    const min = Math.min(...valores, zero ? 0 : Infinity), max = Math.max(...valores, zero ? 0 : -Infinity);
    const y = (v) => h - 4 - ((v - min) / ((max - min) || 1)) * (h - 8);
    const add = (t, a) => { const e = document.createElementNS(ns, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); svg.append(e); };
    if (zero) add("line", { x1: 0, x2: w, y1: y(0), y2: y(0), stroke: "#0f3a1f", "stroke-dasharray": "3 3" });
    add("polyline", { points: valores.map((v, i) => `${(i / (valores.length - 1)) * w},${y(v)}`).join(" "), fill: "none", stroke: cor, "stroke-width": 2 });
    add("circle", { cx: w, cy: y(valores[valores.length - 1]), r: 3, fill: cor });
    return svg;
  }
  const itemNoticia = (n) => el("li", {},
    el("span", { class: "tag " + NIVEL_COR[n.nivel] }, n.nivel.toUpperCase()), link(n.link, n.titulo),
    el("div", { class: "meta" }, `${n.fonte_nome} · ${CATS[n.categoria] || n.categoria} · ${n.escopo} · há ${atras(n.publicado_em)}`));

  // ---- Sala de situação ----------------------------------------------------------
  function renderEnso(e) {
    if (!e.status) { preencher("enso", vazio("Aguardando primeira coleta da NOAA…")); return; }
    const u = e.oni[e.oni.length - 1] || {}, s = e.semanal[e.semanal.length - 1] || {};
    const cor = (u.oni || 0) >= 1.5 ? "red" : (u.oni || 0) >= 0.5 ? "amber" : (u.oni || 0) <= -0.5 ? "cyan" : "green";
    $("enso-at").textContent = "há " + atras(e.status.atualizado_em);
    const sinal = (v) => (v > 0 ? "+" : "") + num(v, 1);
    preencher("enso",
      el("div", { class: "row" }, el("span", { class: "tag red blink" }, "STATUS"), el("b", { class: "red glow" }, (e.status.alerta || "—").toUpperCase())),
      el("div", { class: "row", style: "margin:8px 0;gap:16px;align-items:flex-end" },
        el("div", {}, el("div", { class: "dim" }, `ONI ${u.trimestre || ""} ${u.ano || ""}`), el("div", { class: "big " + cor + " glow" }, (u.oni > 0 ? "+" : "") + num(u.oni) + "°C")),
        el("div", {}, el("div", { class: "dim" }, "NIÑO 3.4"), el("div", { class: "big amber" }, sinal(s.nino34))),
        el("div", {}, el("div", { class: "dim" }, "NIÑO 1+2"), el("div", { class: "big red" }, sinal(s.nino12)))),
      el("div", { class: cor }, (e.status.fase || "").toUpperCase()),
      spark(e.oni.map((o) => o.oni), "#ffb000", 300, 50, true),
      el("div", { class: "dim", style: "font-size:11px" }, "ONI — " + e.oni.map((o) => o.trimestre).join(" · ")),
      el("p", { style: "margin:8px 0 0" }, e.status.sinopse || ""),
      el("p", { class: "dim", style: "margin:6px 0 0;font-size:11px" }, "BR: chuva acima da média e enchentes no Sul · seca no Norte/Nordeste · calor no Centro-Oeste (MS)."));
  }
  function renderArbo(lista) {
    if (!lista.length) { preencher("arbo", vazio("Aguardando dados do InfoDengue…")); return; }
    preencher("arbo", el("table", {},
      el("tr", {}, el("th", {}, "MUNICÍPIO"), el("th", {}, "DOENÇA"), el("th", {}, "NÍVEL"), el("th", { class: "n" }, "SEM."), el("th", { class: "n" }, "ANO"), el("th", { class: "n" }, "RT")),
      ...lista.map((a) => {
        const [cor, bl, nome] = ARBO[a.nivel] || ["dim", "□□□□", "—"];
        return el("tr", {}, el("td", {}, a.municipio.split("/")[0]), el("td", {}, a.doenca.slice(0, 6)),
          el("td", { class: cor }, el("span", { class: "blk" }, bl), " " + nome.slice(0, 4)),
          el("td", { class: "n" }, a.casos_semana), el("td", { class: "n" }, Number(a.casos_ano).toLocaleString("pt-BR")),
          el("td", { class: "n " + ((a.rt || 0) > 1 ? "red" : "green") }, a.rt == null ? "—" : (a.rt > 1 ? "▲" : "▼") + num(a.rt)));
      })),
      el("p", { class: "dim", style: "font-size:11px" }, `Semana ${String(lista[0].semana).slice(4)}/${String(lista[0].semana).slice(0, 4)} · Rt > 1 = transmissão em expansão`));
  }
  function origemTemperatura(c) {
    if (!c.estacao) return "previsão do modelo (sem estação disponível)";
    const hora = new Date(c.observado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const extremos = c.hoje_max != null ? ` · hoje ${num(c.hoje_min, 1)}–${num(c.hoje_max, 1)}°` : "";
    return `medido · ${c.estacao} · ${num(c.estacao_km, 0)} km · ${hora}${extremos}`;
  }
  function renderClima(clima, avisos) {
    const blocos = clima.map((c) => el("div", { style: "margin-bottom:10px" },
      el("div", { class: "row" }, el("b", { class: "green" }, c.cidade.toUpperCase()),
        el("span", { class: "big cyan", style: "font-size:24px" }, num(c.temperatura, 1) + "°C"), el("span", {}, TEMPO[c.codigo] || "")),
      el("div", { class: "dim" }, `umid ${num(c.umidade, 0)}% · vento ${num(c.vento, 0)} km/h`),
      el("div", { class: "dim", style: "font-size:11px" }, origemTemperatura(c)),
      el("table", {}, ...c.previsao.map((p) => el("tr", {},
        el("td", { class: "dim" }, new Date(p.data + "T12:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit" })),
        el("td", {}, `${num(p.tmin, 0)}–${num(p.tmax, 0)}°`, p.tmax_alta != null ? el("div", { class: "dim", style: "font-size:11px" }, `modelos ${num(p.tmax_baixa, 0)}–${num(p.tmax_alta, 0)}°`) : null),
        el("td", { class: p.prob_chuva >= 70 ? "cyan" : "dim" }, `☂ ${num(p.prob_chuva, 0)}%`),
        el("td", { class: "n" }, num(p.chuva_mm, 1) + "mm"))))));
    preencher("clima", blocos.length ? blocos : vazio("Aguardando previsão…"),
      el("div", { class: "green", style: "margin-top:6px" }, `INMET · ${avisos.total} avisos vigentes no país`),
      avisos.resumo.slice(0, 5).map(([k, v]) => el("div", { class: k.includes("Grande Perigo") ? "red" : k.includes("(Perigo)") ? "amber" : "dim" }, `${v}× ${k}`)),
      el("div", { class: "amber", style: "margin-top:6px" }, `${avisos.na_area.length} aviso(s) nas suas cidades`),
      el("ul", { class: "lst" }, ...avisos.na_area.map((a) => el("li", {},
        el("span", { class: "tag " + (a.severidade === "Perigo Potencial" ? "amber" : "red") }, a.severidade.toUpperCase()),
        `${a.evento} · ${a.cidades.join(", ")}`, el("div", { class: "meta" }, `${a.inicio} → ${a.fim}`)))));
  }
  function renderAlimentos(a) {
    $("ipca-mes").textContent = a.mes || "";
    if (!a.itens.length) { preencher("alimentos", vazio("Aguardando IPCA…")); return; }
    const locais = [...new Set(a.itens.map((i) => i.localidade))], porItem = {};
    for (const i of a.itens) (porItem[i.item] ||= {})[i.localidade] = i;
    const altas = a.itens.filter((i) => i.variacao_mes != null && !i.item.startsWith("Alimentação")).sort((x, y) => y.variacao_mes - x.variacao_mes).slice(0, 3);
    preencher("alimentos",
      el("div", { class: "red", style: "margin-bottom:6px" }, "MAIORES ALTAS: " + altas.map((i) => `${i.item} ${i.localidade.split(" ")[0]} +${num(i.variacao_mes)}%`).join(" · ")),
      el("div", { style: "overflow-x:auto" }, el("table", {},
        el("tr", {}, el("th", {}, "ITEM"), ...locais.flatMap((l) => [el("th", { class: "n" }, l.split(" (")[0].toUpperCase().slice(0, 10) + " MÊS"), el("th", { class: "n" }, "12M")])),
        ...Object.entries(porItem).map(([item, pl]) => el("tr", {}, el("td", {}, item),
          ...locais.flatMap((l) => [el("td", { class: "n" }, pct(pl[l]?.variacao_mes)), el("td", { class: "n" }, pct(pl[l]?.variacao_12m))]))))),
      el("p", { class: "dim", style: "font-size:11px" }, "Dourados não é pesquisada pelo IBGE — Campo Grande é a referência regional."));
  }
  function renderPrecos(p) {
    $("precos-cidade").textContent = p.cidade;
    preencher("precos", p.medias.length ? el("table", {},
      el("tr", {}, el("th", {}, "PRODUTO"), el("th", { class: "n" }, "MÉDIA"), el("th", { class: "n" }, "MÍN"), el("th", { class: "n" }, "MÁX"), el("th", { class: "n" }, "MERC.")),
      ...p.medias.map((m) => el("tr", {}, el("td", {}, `${m.produto} (${m.unidade})`), el("td", { class: "n green" }, "R$ " + num(m.media)),
        el("td", { class: "n cyan" }, num(m.minimo)), el("td", { class: "n amber" }, num(m.maximo)), el("td", { class: "n" }, m.mercados))))
      : vazio("Nenhum preço registrado nos últimos 30 dias. Registre abaixo o que encontrar nos mercados — fica salvo só no seu celular."));
  }
  function renderCambio(c) {
    const get = (b, m) => c.atual.find((x) => x.base === b && x.moeda === m);
    const usd = get("USD", "BRL"), eur = get("EUR", "BRL");
    if (!usd) { preencher("cambio", vazio("Aguardando cotações…")); return; }
    $("cambio-data").textContent = usd.data;
    const s = c.usd_brl.map((x) => x.valor);
    const v30 = s.length > 20 ? (s[s.length - 1] / s[s.length - 21] - 1) * 100 : null;
    preencher("cambio",
      el("div", { class: "row", style: "gap:16px" },
        el("div", {}, el("div", { class: "dim" }, "USD/BRL"), el("div", { class: "big green glow" }, num(usd.valor, 4))),
        eur ? el("div", {}, el("div", { class: "dim" }, "EUR/BRL"), el("div", { class: "big cyan" }, num(eur.valor, 4))) : null,
        el("div", {}, el("div", { class: "dim" }, "~30 DIAS"), pct(v30))),
      spark(s, "#33ff77"),
      el("div", { class: "row", style: "gap:12px" }, ...["CNY", "ARS", "GBP"].map((m) => get("USD", m)).filter(Boolean).map((x) => el("span", { class: "dim" }, `USD/${x.moeda} ${num(x.valor)}`))));
  }
  function renderSismos(t) {
    preencher("sismos", t.length ? el("table", {}, ...t.map((s) => el("tr", {},
      el("td", { class: s.magnitude >= 6 ? "red" : "amber" }, "M" + num(s.magnitude, 1)), el("td", {}, link(s.link, s.local)),
      el("td", { class: "n dim" }, atras(s.quando)), el("td", {}, s.tsunami ? el("span", { class: "tag red" }, "TSUNAMI") : "")))) : vazio("Sem dados."));
  }
  function renderColetas(c) {
    preencher("coletas", el("table", {}, ...M.ETAPAS.map((k) => {
      const r = c[k];
      return el("tr", {}, el("td", { class: r ? (r.ok ? "green" : "red") : "dim", style: "white-space:nowrap" }, r ? (r.ok ? "[OK]" : "[FAIL]") : "[--]"),
        el("td", {}, k, el("div", { class: "dim", style: "font-size:11px" }, r ? r.mensagem.slice(0, 70) : "pendente")),
        el("td", { class: "n dim" }, r ? atras(r.quando) : ""));
    })), el("p", { class: "dim", style: "font-size:11px" }, "Tudo é coletado direto das fontes públicas pelo seu celular, sem servidor."));
  }
  function renderFeed() {
    const abas = [["feed", "FEED"], ["criticos", "CRÍTICOS"], ...dados.temas.map((t) => ["tema-" + t.id, (t.alertar ? "🔔 " : "") + t.nome.toUpperCase()])];
    preencher("abas", abas.map(([id, rot]) => el("button", { type: "button", class: aba === id ? "on" : "", on: { click: () => { aba = id; renderFeed(); } } }, rot)));
    let lista = dados.feed;
    if (aba === "criticos") lista = dados.criticos;
    else if (aba.startsWith("tema-")) lista = (dados.temas.find((t) => "tema-" + t.id === aba) || { noticias: [] }).noticias;
    $("filtros").classList.toggle("hidden", aba !== "feed");
    $("feed-n").textContent = lista.length + " itens";
    preencher("feed", lista.length ? lista.slice(0, 200).map(itemNoticia) : vazio(dados.atualizado_em ? "Nada encontrado para este filtro." : "Coletando as 48 fontes…"));
  }
  function render() {
    dados = M.painel({ q: $("f-q").value, escopo: $("f-escopo").value, categoria: $("f-cat").value, nivel: $("f-nivel").value });
    $("n-crit").textContent = dados.contagem.critico || 0;
    $("n-alto").textContent = dados.contagem.alto || 0;
    $("n-total").textContent = Object.values(dados.contagem).reduce((a, b) => a + b, 0);
    const recentes = dados.criticos.filter((n) => Date.now() - new Date(n.publicado_em) < 6 * 3600e3).length;
    $("badge-feed").textContent = recentes; $("badge-feed").classList.toggle("hidden", !recentes);
    preencher("ticker", dados.criticos.slice(0, 25).map((n) => link(n.link, `${n.titulo} — ${n.fonte_nome}`)));
    $("crit-n").textContent = dados.criticos.length + " em 7 dias";
    preencher("criticos", dados.criticos.length ? dados.criticos.slice(0, 30).map(itemNoticia) : vazio("Sem alertas críticos."));
    $("surtos-n").textContent = dados.surtos.length + " sinais";
    preencher("surtos", dados.surtos.length ? dados.surtos.map(itemNoticia) : vazio("Nenhum sinal de surto nas fontes."));
    renderEnso(dados.enso); renderArbo(dados.arboviroses); renderClima(dados.clima, dados.avisos);
    renderAlimentos(dados.alimentos); renderPrecos(dados.precos); renderCambio(dados.cambio);
    renderSismos(dados.terremotos); renderColetas(dados.coletas); renderFeed();
  }

  async function coletar() {
    if (coletando) return;
    coletando = true; restante = M.config().intervaloMin * 60;
    $("led").className = "led busy"; $("estado").textContent = "COLETANDO";
    let feitas = 0;
    try {
      await M.coletarTudo(() => { feitas++; $("estado").textContent = `COLETANDO ${feitas}/${M.ETAPAS.length}`; render(); });
      const falhas = Object.values(M.painel().coletas).filter((c) => !c.ok).length;
      $("led").className = falhas > 3 ? "led off" : "led"; $("estado").textContent = falhas ? `ONLINE · ${falhas} FALHA(S)` : "ONLINE";
      sincronizarVigia(); vigiarAgora(false);
    } catch (e) { $("led").className = "led off"; $("estado").textContent = "OFFLINE"; }
    coletando = false; render();
  }

  // ---- Radar climático local ----------------------------------------------------
  const NCOR = ["#33ff77", "#ffd400", "#ff8c00", "#ff3355"];
  const SEV_NIVEL = { "Perigo Potencial": 1, "Perigo": 2, "Grande Perigo": 3 };
  const ROTULO = { calor: "CALOR", ventania: "VENTANIA", tempestade: "TEMPESTADE", chuva: "CHUVA FORTE", umidade: "BAIXA UMIDADE" };
  const UFS = Object.keys(D.MUNICIPIOS).sort();
  function iniciarMapa() {
    if (mapa || !window.L) return;
    const c = M.config().clima;
    mapa = L.map("mapa", { zoomControl: true, attributionControl: true }).setView([c.lat ?? -22.22, c.lon ?? -54.81], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
    camadas = L.layerGroup().addTo(mapa);
    mapa.on("click", (e) => { salvarClima({ lat: +e.latlng.lat.toFixed(6), lon: +e.latlng.lng.toFixed(6) }); analisar(); });
  }
  function salvarClima(parcial) { const c = M.config(); c.clima = { ...c.clima, ...parcial }; M.salvarConfig(c); return c.clima; }
  function grafico(tempos, series, opts = {}) {
    const W = 640, H = 200, ml = 38, mr = 10, mt = 10, mb = 24, ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", "100%");
    const todos = series.flatMap((s) => s.valores.filter((v) => v != null)).concat((opts.limiares || []).map((l) => l.v));
    if (!todos.length) return svg;
    let min = opts.min ?? Math.min(...todos), max = opts.max ?? Math.max(...todos);
    if (max === min) max = min + 1;
    const n = tempos.length, x = (i) => ml + (i / Math.max(n - 1, 1)) * (W - ml - mr), y = (v) => mt + (1 - (v - min) / (max - min)) * (H - mt - mb);
    const add = (tag, a, txt) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); if (txt != null) e.textContent = txt; svg.append(e); };
    for (let k = 0; k <= 4; k++) { const v = min + (k / 4) * (max - min);
      add("line", { x1: ml, x2: W - mr, y1: y(v), y2: y(v), stroke: "#0f3a1f" });
      add("text", { x: ml - 4, y: y(v) + 4, fill: "#4f8f63", "font-size": 13, "text-anchor": "end" }, Math.round(v)); }
    tempos.forEach((t, i) => { if (t.slice(11, 13) === "00" || i === 0) {
      add("line", { x1: x(i), x2: x(i), y1: mt, y2: H - mb, stroke: "#0f3a1f", "stroke-dasharray": "2 3" });
      add("text", { x: x(i) + 2, y: H - 6, fill: "#4f8f63", "font-size": 13 }, t.slice(8, 10) + "/" + t.slice(5, 7)); } });
    for (const l of opts.limiares || []) {
      add("line", { x1: ml, x2: W - mr, y1: y(l.v), y2: y(l.v), stroke: l.cor, "stroke-dasharray": "5 4" });
      add("text", { x: W - mr - 2, y: y(l.v) - 3, fill: l.cor, "font-size": 12, "text-anchor": "end" }, l.rotulo); }
    for (const s of series) {
      if (s.barras) { const bw = Math.max(2, (W - ml - mr) / n - 2);
        s.valores.forEach((v, i) => { if (v) add("rect", { x: x(i) - bw / 2, y: y(v), width: bw, height: Math.max(0, y(min) - y(v)), fill: s.cor, opacity: .8 }); });
      } else add("polyline", { points: s.valores.map((v, i) => v == null ? null : `${x(i)},${y(v)}`).filter(Boolean).join(" "), fill: "none",
        stroke: s.cor, "stroke-width": s.largura || 2.5, "stroke-dasharray": s.tracejado ? "4 3" : "" });
    }
    return svg;
  }
  const legenda = (itens) => el("div", { class: "dim", style: "font-size:11px;margin-top:4px" }, ...itens.flatMap(([cor, t]) => [el("span", { style: `color:${cor}` }, "■ "), t + "   "]));

  function renderLocal(r) {
    const loc = r.local, h = r.horas, o = r.observacao, e = r.estacao;
    $("cl-status").textContent = "ok"; $("cl-gerado").textContent = "gerado " + new Date(r.gerado_em).toLocaleTimeString("pt-BR");
    preencher("cl-local", el("div", { class: "green", style: "font-size:15px;font-weight:800" }, loc.nome),
      el("div", { class: "kv", style: "margin-top:8px" },
        el("span", { class: "dim" }, "coordenada"), el("span", {}, `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`),
        el("span", { class: "dim" }, "precisão"), el("span", { class: loc.precisao === "municipio" ? "amber" : "green" }, loc.precisao.toUpperCase()),
        el("span", { class: "dim" }, "localização"), el("span", {}, loc.fonte),
        el("span", { class: "dim" }, "IBGE"), el("span", {}, loc.geocodigo || "—"),
        el("span", { class: "dim" }, "altitude"), el("span", {}, r.elevacao_m != null ? num(r.elevacao_m, 0) + " m" : "—"),
        el("span", { class: "dim" }, "previsão"), el("span", {}, r.fonte_previsao || "—")),
      r.falhas.length ? el("p", { class: "amber" }, "Fontes indisponíveis: " + r.falhas.join(", ")) : null);
    const oficial = r.avisos.reduce((m, a) => Math.max(m, SEV_NIVEL[a.severidade] || 0), 0);
    const pior = r.avisos.find((a) => (SEV_NIVEL[a.severidade] || 0) === oficial);
    preencher("cl-riscos", el("div", { class: "card l" + oficial }, el("div", { class: "t" }, "AVISO OFICIAL INMET"),
      el("div", { class: "n" + (oficial >= 2 ? " blink" : "") }, oficial ? pior.severidade.toUpperCase() : "SEM AVISO"),
      el("div", { class: "v" }, oficial ? `${pior.evento} · até ${pior.fim.slice(-5)}` : "nenhum aviso cobre este ponto"),
      el("div", { class: "c" }, "polígono oficial do INMET")),
      r.riscos.map((x) => el("div", { class: "card l" + x.nivel }, el("div", { class: "t" }, ROTULO[x.tipo] || x.tipo),
        el("div", { class: "n" }, x.rotulo.toUpperCase()), el("div", { class: "v" }, x.valor + (x.quando ? ` · pico ${hora(x.quando)}` : "")),
        el("div", { class: "c" }, x.criterio))));
    preencher("cl-avisos", r.avisos.length ? r.avisos.map((a) => el("li", {},
      el("span", { class: "tag", style: `color:${a.cor || "#ffb000"}` }, a.severidade.toUpperCase()), el("b", {}, a.evento), ` · ${a.inicio} → ${a.fim}`,
      el("div", { class: a.dentro_do_poligono ? "green" : "dim", style: "font-size:11px" }, a.dentro_do_poligono ? "✓ ponto dentro da área do aviso" : "município citado no aviso"),
      el("div", { style: "font-size:12px" }, a.riscos.slice(0, 260)),
      a.instrucoes ? el("div", { class: "dim", style: "font-size:11px" }, "→ " + a.instrucoes.slice(0, 220)) : null))
      : vazio("Nenhum aviso do INMET vigente para este ponto."));
    const blocoEstacao = e ? [el("div", { class: "green" }, e.rotulo),
      el("div", { class: "dim", style: "font-size:11px" }, `a ${num(e.distancia_km, 1)} km · ${new Date(e.quando).toLocaleString("pt-BR")}`),
      el("div", { class: "row", style: "gap:16px;margin:8px 0" },
        el("div", {}, el("div", { class: "dim" }, "MEDIDO"), el("div", { class: "big cyan" }, num(e.temperatura, 1) + "°C")),
        el("div", {}, el("div", { class: "dim" }, "MODELO"), el("div", { class: "big green" }, num(h.temperature_2m?.[0], 1) + "°C")),
        el("div", {}, el("div", { class: "dim" }, "UMIDADE"), el("div", { class: "big amber", style: "font-size:20px" }, num(e.umidade, 0) + "%")))] : [];
    preencher("cl-obs", blocoEstacao, o ? [el("div", { class: "green" }, `${o.estacao} · ${o.nome}`),
      el("div", { class: "dim", style: "font-size:11px" }, `a ${num(o.distancia_km, 1)} km · ${new Date(o.quando).toLocaleString("pt-BR")}`),
      el("div", { class: "row", style: "gap:16px;margin:8px 0" },
        el("div", {}, el("div", { class: "dim" }, "MEDIDO"), el("div", { class: "big cyan" }, num(o.temperatura, 0) + "°C")),
        el("div", {}, el("div", { class: "dim" }, "MODELO"), el("div", { class: "big green" }, num(h.temperature_2m?.[0], 0) + "°C")),
        el("div", {}, el("div", { class: "dim" }, "VENTO"), el("div", { class: "big amber", style: "font-size:20px" }, num(o.vento_kmh, 0) + (o.rajada_kmh ? "/" + num(o.rajada_kmh, 0) : "") + " km/h"))),
      o.fenomeno ? el("div", { class: "red" }, "Fenômeno: " + o.fenomeno) : null,
      el("code", { class: "dim", style: "font-size:11px;word-break:break-all" }, o.bruto)] : e ? null : vazio("Nenhuma estação transmitindo perto deste ponto."));
    preencher("cl-focos", r.focos.length
      ? [el("div", { class: "big red" }, r.focos.length), el("div", {}, `foco(s) em até 50 km · mais próximo a ${num(r.focos[0].distancia_km, 1)} km`),
        el("table", {}, ...r.focos.slice(0, 6).map((f) => el("tr", {}, el("td", {}, num(f.distancia_km, 1) + " km"), el("td", { class: "dim" }, f.satelite),
          el("td", { class: "n dim" }, f.quando.slice(5, 16)))))]
      : [el("div", { class: "big green" }, "0"), el("div", { class: "dim" }, "nenhum foco de queimada em 50 km (INPE, hoje/ontem)")]);
    if (h.time && h.time.length) {
      preencher("g-temp", grafico(h.time, [{ valores: h.apparent_temperature, cor: "#ff3355" }, { valores: h.temperature_2m, cor: "#33ff77" }],
        { limiares: [{ v: 32, cor: "#ffd400", rotulo: "atenção 32" }, { v: 41, cor: "#ff8c00", rotulo: "perigo 41" }] }),
        legenda([["#33ff77", "temperatura"], ["#ff3355", "sensação térmica"]]));
      preencher("g-vento", grafico(h.time, [{ valores: h.wind_gusts_10m, cor: "#ff8c00" }, { valores: h.wind_speed_10m, cor: "#36d6ff", largura: 1.5 }],
        { min: 0, limiares: [{ v: 40, cor: "#ffd400", rotulo: "40" }, { v: 60, cor: "#ff8c00", rotulo: "60 perigo" }] }),
        legenda([["#36d6ff", "vento médio"], ["#ff8c00", "rajadas"]]));
      preencher("g-chuva", grafico(h.time, [{ valores: h.precipitation_probability.map((p) => p == null ? null : p / 10), cor: "#4f8f63", tracejado: true, largura: 1.5 },
        { valores: h.precipitation, cor: "#36d6ff", barras: true }], { min: 0, limiares: [{ v: 20, cor: "#ffd400", rotulo: "20 mm/h" }] }),
        legenda([["#36d6ff", "chuva mm/h"], ["#4f8f63", "probabilidade ÷10"]]));
      preencher("g-cape", grafico(h.time, [{ valores: h.cape, cor: "#ff3355" }],
        { min: 0, limiares: [{ v: 1000, cor: "#ffd400", rotulo: "1000" }, { v: 2500, cor: "#ff3355", rotulo: "2500 severo" }] }),
        legenda([["#ff3355", "CAPE (energia convectiva)"]]));
    }
    const mods = r.consenso.length ? Object.keys(r.consenso[0].modelos) : [];
    preencher("cl-consenso", r.consenso.length ? el("div", { style: "overflow-x:auto" }, el("table", {},
      el("tr", {}, el("th", {}, "DIA"), ...mods.map((m) => el("th", { class: "n" }, m)), el("th", { class: "n" }, "±Tmáx"), el("th", { class: "n" }, "±rajada")),
      ...r.consenso.map((c) => el("tr", {}, el("td", {}, c.dia.slice(8, 10) + "/" + c.dia.slice(5, 7)),
        ...mods.map((m) => { const v = c.modelos[m]; return el("td", { class: "n" }, `${num(v.tmax, 0)}° ${num(v.rajada, 0)}km/h ${num(v.chuva, 1)}mm`); }),
        el("td", { class: "n " + (c.tmax_spread >= 4 ? "red" : c.tmax_spread >= 2 ? "amber" : "green") }, num(c.tmax_spread / 2, 1) + "°"),
        el("td", { class: "n " + (c.rajada_spread >= 20 ? "red" : c.rajada_spread >= 10 ? "amber" : "green") }, num(c.rajada_spread / 2, 0)))))) : vazio("Sem consenso (previsão de reserva)."));
    if (mapa) {
      camadas.clearLayers();
      const preenchido = r.avisos.find((a) => a.dentro_do_poligono && a.poligono);
      for (const a of r.avisos) if (a.poligono) L.geoJSON(a.poligono, { style: { color: a.cor || "#ffb000", weight: 1.5, fill: a === preenchido, fillOpacity: .08, dashArray: a.severidade === "Perigo Potencial" ? "6 4" : null } }).bindPopup(`${a.evento} — ${a.severidade}`).addTo(camadas);
      for (const f of r.focos) L.circleMarker([f.lat, f.lon], { radius: 5, color: "#ff3355", fillOpacity: .9 }).addTo(camadas);
      if (o) L.circleMarker([o.lat, o.lon], { radius: 6, color: "#36d6ff", fillOpacity: .9 }).bindPopup(`${o.estacao} ${num(o.temperatura, 0)}°C`).addTo(camadas);
      L.circleMarker([loc.lat, loc.lon], { radius: 9, color: "#33ff77", weight: 3, fillOpacity: .3 }).bindPopup(loc.nome).addTo(camadas);
      mapa.setView([loc.lat, loc.lon], loc.precisao === "municipio" ? 12 : 14);
    }
  }
  async function analisar() {
    const c = M.config().clima;
    $("cl-status").textContent = "analisando…";
    try {
      const r = await M.relatorioLocal(c);
      renderLocal(r);
      salvarClima({ ponto: { lat: r.local.lat, lon: r.local.lon, nome: r.local.nome.replace(/ \(bairro.*$/, "") } });
      sincronizarVigia();
    } catch (e) { $("cl-status").textContent = "erro: " + (e.message || e); }
  }
  function opcoesCidades(ufSel, cidSel, uf, cidade) {
    $(ufSel).replaceChildren(...UFS.map((u) => el("option", { value: u }, u)));
    $(ufSel).value = uf;
    $(cidSel).replaceChildren(...(D.MUNICIPIOS[uf] || []).map(([g, n]) => el("option", { value: n, "data-g": g }, n)));
    if (cidade) $(cidSel).value = cidade;
  }
  async function carregarBairros() {
    const c = M.config().clima;
    $("cl-bairros").replaceChildren();
    const b = await M.listarBairros(c.cidade, c.uf).catch(() => []);
    $("cl-bairros").replaceChildren(...b.map((x) => el("option", { value: x.nome })));
  }
  function iniciarClima() {
    const c = M.config().clima;
    opcoesCidades("cl-uf", "cl-cidade", c.uf, c.cidade);
    $("cl-bairro").value = c.bairro || "";
    $("cl-uf").addEventListener("change", () => { opcoesCidades("cl-uf", "cl-cidade", $("cl-uf").value);
      salvarClima({ uf: $("cl-uf").value, cidade: $("cl-cidade").value, bairro: "", lat: null, lon: null }); $("cl-bairro").value = ""; carregarBairros(); });
    $("cl-cidade").addEventListener("change", () => { salvarClima({ cidade: $("cl-cidade").value, bairro: "", lat: null, lon: null }); $("cl-bairro").value = ""; carregarBairros(); analisar(); });
    $("cl-analisar").addEventListener("click", () => { salvarClima({ bairro: $("cl-bairro").value.trim(), lat: null, lon: null }); analisar(); });
    $("cl-bairro").addEventListener("keydown", (e) => { if (e.key === "Enter") $("cl-analisar").click(); });
    $("cl-gps").addEventListener("click", async () => {
      try {
        const pos = P.Geolocation ? await P.Geolocation.getCurrentPosition({ enableHighAccuracy: true, timeout: 15000 })
          : await new Promise((ok, err) => navigator.geolocation.getCurrentPosition(ok, err, { enableHighAccuracy: true, timeout: 15000 }));
        salvarClima({ lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) }); analisar();
      } catch (_) { toast("Não foi possível obter a localização. Verifique a permissão de localização do ARGOS."); }
    });
    const ult = M.store.get("clima_ultimo");
    if (ult) renderLocal(ult);
  }

  // ---- Background watcher + notifications ---------------------------------------
  function configVigia() {
    const c = M.config();
    return { cidades: c.cidades, ponto: c.clima.ponto || null, temas: c.temas, notificar: c.notificar, boletimHora: c.boletimHora,
      tzOffsetMin: new Date().getTimezoneOffset(), openMeteoKey: c.openMeteoKey,
      criterios: { CRITICO: D.CRITICO, TERMOS_SURTO: D.TERMOS_SURTO } };
  }
  async function prepararNotificacoes() {
    if (!P.LocalNotifications) return;
    try {
      await P.LocalNotifications.createChannel({ id: "argos_urgente", name: "ARGOS · Alertas urgentes", description: "Avisos INMET de perigo, riscos iminentes, surtos e temas 🔔",
        importance: 5, visibility: 1, vibration: true, lights: true, lightColor: "#FF3355" });
      await P.LocalNotifications.createChannel({ id: "argos_boletim", name: "ARGOS · Boletim da manhã", description: "Resumo diário: clima, avisos, arboviroses, El Niño, câmbio",
        importance: 3, visibility: 1, vibration: false });
      const p = await P.LocalNotifications.checkPermissions();
      if (p.display !== "granted") await P.LocalNotifications.requestPermissions();
    } catch (_) {}
  }
  async function sincronizarVigia() {
    const config = configVigia();
    if (P.BackgroundRunner) {
      try { await P.BackgroundRunner.dispatchEvent({ label: RUNNER, event: "configurar", details: { config } }); } catch (_) {}
    } else localStorage.setItem("argos:kv:config", JSON.stringify(config));
  }
  async function vigiarAgora(boletim) {
    try {
      if (P.BackgroundRunner) return await P.BackgroundRunner.dispatchEvent({ label: RUNNER, event: "vigiarAgora", details: { boletim } });
      return await window.ArgosVigia.vigiar({ forcar: true, boletim });
    } catch (e) { return { erro: String(e) }; }
  }
  if (!CAP) { // browser preview: shim the runner APIs
    window.CapacitorKV = { get: (k) => ({ value: localStorage.getItem("argos:kv:" + k) }), set: (k, v) => localStorage.setItem("argos:kv:" + k, v), remove: (k) => localStorage.removeItem("argos:kv:" + k) };
    window.CapacitorNotifications = { schedule: (lista) => lista.forEach((n) => toast(n.title + " — " + n.body)) };
  }

  // ---- Configuração -------------------------------------------------------------
  function renderConfig() {
    const c = M.config();
    preencher("lista-cidades", c.cidades.map((x, i) => el("span", { class: "tag green", style: "padding:4px 8px;font-size:12px" }, `${x.nome}/${x.uf} `,
      el("a", { href: "#", on: { click: (e) => { e.preventDefault(); const k = M.config(); k.cidades.splice(i, 1); M.salvarConfig(k); renderConfig(); sincronizarVigia(); } } }, "✕"))));
    preencher("lista-temas", c.temas.length ? c.temas.map((t) => el("span", { class: "tag green", style: "padding:4px 8px;font-size:12px" }, (t.alertar ? "🔔 " : "") + t.nome + " ",
      el("a", { href: "#", on: { click: (e) => { e.preventDefault(); if (!confirm("Remover o tema " + t.nome + "?")) return;
        const k = M.config(); k.temas = k.temas.filter((x) => x.id !== t.id); M.salvarConfig(k); if (aba === "tema-" + t.id) aba = "feed"; renderConfig(); render(); sincronizarVigia(); } } }, "✕")))
      : el("span", { class: "dim" }, "Nenhum tema ainda (ex.: reforma tributária, H5N1, preço do boi)."));
    preencher("cfg-ipca", Object.entries(D.LOCALIDADES_IPCA).map(([k, v]) => el("label", {},
      Object.assign(el("input", { type: "checkbox", value: k }), { checked: c.ipca.includes(k) }), v.nome)));
    for (const [id, k] of [["n-inmet", "inmet"], ["n-risco", "riscoLocal"], ["n-surtos", "surtos"], ["n-criticos", "criticos"], ["n-boletim", "boletim"]]) $(id).checked = !!c.notificar[k];
    $("cfg-hora").value = String(c.boletimHora); $("cfg-intervalo").value = String(c.intervaloMin); $("cfg-om").value = c.openMeteoKey || "";
  }
  function salvarPreferencias() {
    const c = M.config();
    c.notificar = { inmet: $("n-inmet").checked, riscoLocal: $("n-risco").checked, surtos: $("n-surtos").checked, criticos: $("n-criticos").checked, boletim: $("n-boletim").checked };
    c.boletimHora = +$("cfg-hora").value; c.intervaloMin = +$("cfg-intervalo").value; c.openMeteoKey = $("cfg-om").value.trim();
    c.ipca = [...$("cfg-ipca").querySelectorAll("input:checked")].map((i) => i.value);
    M.salvarConfig(c); sincronizarVigia();
  }
  function iniciarConfig() {
    opcoesCidades("c-uf", "c-cidade", "MS", "Dourados");
    $("c-uf").addEventListener("change", () => opcoesCidades("c-uf", "c-cidade", $("c-uf").value));
    $("c-add").addEventListener("click", () => {
      const opt = $("c-cidade").selectedOptions[0]; if (!opt) return;
      const c = M.config();
      if (!c.cidades.some((x) => x.geocodigo === opt.dataset.g)) c.cidades.push({ nome: opt.value, uf: $("c-uf").value, geocodigo: opt.dataset.g });
      M.salvarConfig(c); renderConfig(); sincronizarVigia(); toast(`${opt.value} adicionada. Atualize para coletar.`);
    });
    for (const [k, v] of Object.entries(CATS)) {
      $("f-cat").append(el("option", { value: k }, v));
      $("t-cats").append(el("label", {}, el("input", { type: "checkbox", value: k }), v));
    }
    for (let h = 5; h <= 10; h++) $("cfg-hora").append(el("option", { value: String(h) }, String(h).padStart(2, "0") + ":00"));
    for (const id of ["n-inmet", "n-risco", "n-surtos", "n-criticos", "n-boletim", "cfg-hora", "cfg-intervalo"]) $(id).addEventListener("change", salvarPreferencias);
    $("cfg-ipca").addEventListener("change", salvarPreferencias);
    $("cfg-salvar").addEventListener("click", () => { salvarPreferencias(); toast("Configurações salvas."); });
    $("cfg-limpar").addEventListener("click", () => {
      if (!confirm("Apagar notícias, indicadores e preços salvos neste celular? (as configurações ficam)")) return;
      for (const k of ["estado", "precos", "clima_ultimo"]) localStorage.removeItem("argos:" + k);
      render(); toast("Dados locais apagados.");
    });
    $("n-teste").addEventListener("click", async () => {
      salvarPreferencias(); await prepararNotificacoes(); await sincronizarVigia();
      toast("Gerando boletim e verificando alertas…");
      const r = await vigiarAgora(true);
      toast(r && r.erro ? "Falha: " + r.erro : `Vigia executado: ${r?.enviados ?? 0} notificação(ões) enviada(s).`);
    });
    $("form-tema").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const c = M.config();
      const t = { id: Date.now().toString(36), nome: $("t-nome").value.trim(), termos: $("t-termos").value, excluir: $("t-excluir").value,
        escopo: $("t-escopo").value, nivel_minimo: $("t-nivel").value, alertar: $("t-alertar").checked,
        categorias: [...$("t-cats").querySelectorAll("input:checked")].map((i) => i.value) };
      if (!t.nome || !t.termos.trim()) { $("t-msg").textContent = "Informe nome e termos."; return; }
      c.temas.push(t); M.salvarConfig(c); ev.target.reset(); $("t-msg").textContent = "";
      aba = "tema-" + t.id; renderConfig(); render(); sincronizarVigia(); toast(`Tema "${t.nome}" criado.`);
    });
    $("sobre").replaceChildren(
      el("b", { class: "green" }, `ARGOS mobile v${VERSAO}`), " · motor local · 48 fontes RSS · NOAA · INMET · InfoDengue · IBGE · Open-Meteo · USGS · INPE · BCE.",
      el("br"), el("a", { href: URL_APK, target: "_blank", rel: "noopener", class: "green" }, "⬇ Baixar a versão mais recente do app"),
      el("br"), "© 2026 VSA Soluções em Tecnologia. Todos os direitos reservados. Software licenciado — veja LICENCA-ARGOS.md.");
  }

  // ---- Navegação, relógio, inicialização ----------------------------------------
  function mostrar(v) {
    view = v;
    for (const n of ["sala", "clima", "feed", "config"]) $("v-" + n).classList.toggle("hidden", n !== v);
    document.querySelectorAll("nav.bar button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    $("sub").textContent = SUB[v];
    window.scrollTo(0, 0);
    if (v === "clima") { iniciarMapa(); setTimeout(() => mapa && mapa.invalidateSize(), 60); if (!M.store.get("clima_ultimo")) analisar(); }
    if (v === "config") renderConfig();
  }
  document.querySelectorAll("nav.bar button").forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.v)));
  $("btn-atualizar").addEventListener("click", () => (view === "clima" ? analisar() : coletar()));
  $("f-aplicar").addEventListener("click", render);
  $("f-q").addEventListener("keydown", (e) => { if (e.key === "Enter") render(); });
  for (const id of ["f-escopo", "f-nivel", "f-cat"]) $(id).addEventListener("change", render);
  $("pr-data").value = new Date().toISOString().slice(0, 10);
  $("form-preco").addEventListener("submit", (ev) => {
    ev.preventDefault();
    try {
      M.registrarPreco({ produto: $("pr-produto").value, mercado: $("pr-mercado").value, preco: $("pr-preco").value, unidade: $("pr-unidade").value, data: $("pr-data").value });
      $("pr-produto").value = ""; $("pr-preco").value = ""; render(); toast("Preço registrado.");
    } catch (e) { toast(e.message); }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      const ult = M.painel().atualizado_em;
      if (!ult || Date.now() - new Date(ult) > M.config().intervaloMin * 60e3) coletar();
    }
  });
  setInterval(() => {
    $("relogio").textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    restante -= 1;
    $("contagem").textContent = coletando ? "…" : "⏱" + Math.max(0, Math.floor(restante / 60)) + "m";
    if (restante <= 0 && !coletando && document.visibilityState === "visible") coletar();
  }, 1000);

  iniciarConfig(); iniciarClima(); render();
  const ultimo = M.painel().atualizado_em;
  restante = ultimo ? M.config().intervaloMin * 60 - (Date.now() - new Date(ultimo)) / 1000 : 0;
  $("estado").textContent = ultimo ? "ONLINE · CACHE" : "INICIANDO"; $("led").className = ultimo ? "led" : "led busy";
  prepararNotificacoes().then(sincronizarVigia);
  const inicial = (location.hash || "").replace("#", "");
  if (["sala", "clima", "feed", "config"].includes(inicial)) mostrar(inicial);
  window.ArgosApp = { coletar, analisar, mostrar, vigiarAgora };
})();
