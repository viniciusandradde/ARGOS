// Offline tests for the background watcher (no DOM, mocked fetch). Run: npm test (in mobile/)
const test = require("node:test");
const assert = require("node:assert");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const WWW = path.join(__dirname, "..", "www");
const D = (() => { const w = {}; vm.runInNewContext(fs.readFileSync(path.join(WWW, "js/dados.js"), "utf8"), { window: w }); return w.ARGOS_DADOS; })();

const QUADRADO = { type: "Polygon", coordinates: [[[-55, -23], [-54, -23], [-54, -22], [-55, -22], [-55, -23]]] };
const agoraRss = new Date().toUTCString();
const RESPOSTAS = {
  "apiprevmet3.inmet.gov.br": { hoje: [
    { id: 1, descricao: "Tempestade", severidade: "Perigo", geocodes: "5003702,5002704", poligono: JSON.stringify(QUADRADO),
      data_inicio: "2026-11-04", hora_inicio: "00:00", data_fim: "2026-11-04", hora_fim: "23:59", riscos: "['Rajadas de vento', 'Granizo']" },
    { id: 2, descricao: "Baixa umidade", severidade: "Perigo Potencial", geocodes: "5003702", poligono: "{}",
      data_inicio: "2026-11-04", hora_inicio: "10:00", data_fim: "2026-11-04", hora_fim: "18:00" },
    { id: 3, descricao: "Tempestade", severidade: "Grande Perigo", geocodes: "4314902", poligono: "{}" }] },
  "api.open-meteo.com": { hourly: { time: ["2026-11-04T13:00", "2026-11-04T14:00"], apparent_temperature: [36, 42],
    wind_gusts_10m: [40, 72], precipitation: [0, 12], cape: [1200, 3100], weather_code: [3, 96] },
    daily: { temperature_2m_min: [22], temperature_2m_max: [34], precipitation_probability_max: [80], precipitation_sum: [12],
      wind_gusts_10m_max: [72], weather_code: [96] } },
  "info.dengue.mat.br": [{ SE: 202644, nivel: 4, Rt: 1.2, casos: 30 }],
  "www.cpc.ncep.noaa.gov": "SEAS YR TOTAL ANOM\n JJA 2026 28.9 1.90\n ASO 2026 29.2 2.46\n",
  "api.frankfurter.dev": { date: "2026-11-04", rates: { BRL: 5.4654 } },
  "www.who.int": `<rss><channel><item><title>WHO declares outbreak of Marburg virus</title><link>https://who.int/x</link><pubDate>${agoraRss}</pubDate></item></channel></rss>`,
  "agenciabrasil.ebc.com.br": `<rss><channel><item><title><![CDATA[Casos de dengue disparam em MS]]></title><link>https://ab/x</link><pubDate>${agoraRss}</pubDate></item></channel></rss>`,
};

function novoContexto() {
  const kv = {}, enviados = [], handlers = {};
  const fetch = async (url) => {
    const host = new URL(url).host;
    const corpo = RESPOSTAS[host];
    if (corpo === undefined) return { status: 503, text: async () => "" };
    return { status: 200, text: async () => (typeof corpo === "string" ? corpo : JSON.stringify(corpo)) };
  };
  const ctx = vm.createContext({ fetch, console, setTimeout, Date, JSON, Promise,
    addEventListener: (n, fn) => { handlers[n] = fn; },
    CapacitorKV: { get: (k) => ({ value: kv[k] }), set: (k, v) => { kv[k] = v; } },
    CapacitorNotifications: { schedule: (l) => enviados.push(...l) } });
  vm.runInContext(fs.readFileSync(path.join(WWW, "runners/vigia.js"), "utf8") + ";this.V=ArgosVigia;", ctx);
  kv.config = JSON.stringify({
    cidades: [{ nome: "Dourados", uf: "MS", geocodigo: "5003702", lat: -22.22, lon: -54.8 }],
    ponto: { lat: -22.5, lon: -54.5, nome: "Monte Carlo" }, temas: [{ nome: "Dengue MS", termos: "dengue", alertar: true }],
    notificar: { inmet: true, riscoLocal: true, surtos: true, criticos: false, boletim: true },
    boletimHora: 7, tzOffsetMin: 240, criterios: { CRITICO: D.CRITICO, TERMOS_SURTO: D.TERMOS_SURTO } });
  return { ctx, kv, enviados, handlers };
}

test("ponto no polígono (ray casting com GeoJSON)", () => {
  const { ctx } = novoContexto();
  assert.equal(ctx.V.noPoligono(-22.5, -54.5, QUADRADO), true);
  assert.equal(ctx.V.noPoligono(-21.5, -54.5, QUADRADO), false);
});

test("RSS sem DOM: CDATA, entidades e Atom", () => {
  const { ctx } = novoContexto();
  const itens = ctx.V.parseRss('<feed><entry><title>A &amp; B</title><link href="https://x/1"/><updated>2026-11-04T10:00:00Z</updated></entry></feed>', "t");
  assert.equal(itens[0].titulo, "A & B");
  assert.equal(itens[0].link, "https://x/1");
});

test("urgentes + boletim, com deduplicação entre rodadas", async () => {
  const { enviados, handlers } = novoContexto();
  const r = await new Promise((ok, err) => handlers.vigiarAgora(ok, err, { boletim: true }));
  const urgentes = enviados.filter((n) => n.channelId === "argos_urgente");
  const titulos = urgentes.flatMap((n) => [n.title, ...(n.title.startsWith("⚠ +") ? String(n.largeBody).split("\n").map((l) => l.replace(/^• /, "")) : [])]);
  assert.ok(titulos.some((t) => t.startsWith("⚠ INMET PERIGO: Tempestade")), titulos.join("\n"));
  assert.ok(!titulos.some((t) => t.includes("Baixa umidade")), "Perigo Potencial não é urgente");
  assert.ok(!titulos.some((t) => t.includes("GRANDE PERIGO: Tempestade")), "aviso de outra cidade (Porto Alegre) ignorado");
  assert.ok(titulos.some((t) => t.startsWith("💨 VENTANIA")));
  assert.ok(titulos.some((t) => t.startsWith("⛈ TEMPESTADE")));
  assert.ok(titulos.some((t) => t.startsWith("🔥 CALOR")));
  assert.ok(titulos.some((t) => t.startsWith("☣ SURTO")), "Marburg na OMS");
  assert.ok(titulos.some((t) => t.startsWith("🔔 Dengue MS")), "tema com sino");
  const boletim = enviados.find((n) => n.channelId === "argos_boletim");
  assert.ok(boletim && /Dourados: 22–34°C/.test(boletim.largeBody), boletim && boletim.largeBody);
  assert.match(boletim.largeBody, /chikungunya VERMELHO|dengue VERMELHO/);
  assert.match(boletim.largeBody, /ONI ASO 2026 = \+2,46/);
  assert.ok(enviados.filter((n) => n.channelId === "argos_urgente").every((n) => Number.isInteger(n.id) && n.id > 0));
  assert.ok(enviados.length <= 7, "no máximo 6 + 1 agrupada");
  assert.ok(r.enviados >= enviados.length);

  const antes = enviados.length;
  await new Promise((ok, err) => handlers.vigiarAgora(ok, err, {}));
  assert.equal(enviados.length, antes, "nada repetido na segunda rodada");
});

test("boletim só a partir da hora configurada e uma vez por dia", async () => {
  const { kv, enviados, handlers } = novoContexto();
  const cfg = JSON.parse(kv.config);
  cfg.boletimHora = 0; cfg.notificar = { ...cfg.notificar, inmet: false, riscoLocal: false, surtos: false };
  cfg.temas = []; kv.config = JSON.stringify(cfg);
  await new Promise((ok, err) => handlers.vigiar(ok, err));
  const hora = new Date(Date.now() - 240 * 60000).getUTCHours();
  const esperado = hora < 12 ? 1 : 0;
  assert.equal(enviados.filter((n) => n.channelId === "argos_boletim").length, esperado);
  await new Promise((ok, err) => handlers.vigiar(ok, err));
  assert.equal(enviados.filter((n) => n.channelId === "argos_boletim").length, esperado);
});
