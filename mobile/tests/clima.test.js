// Offline tests for the weather helpers of the local engine. Run: npm test (in mobile/)
const test = require("node:test");
const assert = require("node:assert");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const WWW = path.join(__dirname, "..", "www");
const window = {};
const contexto = { window, localStorage: { getItem: () => null, setItem() {} }, console, URL, URLSearchParams, setTimeout, clearTimeout };
vm.createContext(contexto);
for (const f of ["dados.js", "motor.js"]) vm.runInContext(fs.readFileSync(path.join(WWW, "js", f), "utf8"), contexto);
const M = window.ArgosMotor;

const AGORA = Date.parse("2026-11-04T21:50:00Z");
const LEITURA = {
  estacao: { CODIGO: "A721", NOME: "DOURADOS", DISTANCIA_EM_KM: "9", LATITUDE: "-22.19", LONGITUDE: "-54.91" },
  dados: { DT_MEDICAO: "2026-11-04", HR_MEDICAO: "2100", TEM_INS: "32.8", UMD_INS: "46", VEN_VEL: "1.3", VEN_RAJ: "11.8" },
};

test("estação: converte a leitura do INMET", () => {
  const r = M.parseEstacao(LEITURA, AGORA);
  assert.strictEqual(r.codigo, "A721");
  assert.strictEqual(r.temperatura, 32.8);
  assert.strictEqual(r.umidade, 46);
  assert.strictEqual(r.vento_kmh, 4.7);
  assert.strictEqual(r.quando, "2026-11-04T21:00:00.000Z");
});

test("estação: recusa leitura antiga, distante ou sem temperatura", () => {
  assert.strictEqual(M.parseEstacao(LEITURA, AGORA + 4 * 3600e3), null);
  assert.strictEqual(M.parseEstacao({ ...LEITURA, estacao: { ...LEITURA.estacao, DISTANCIA_EM_KM: "90" } }, AGORA), null);
  assert.strictEqual(M.parseEstacao({ ...LEITURA, dados: { ...LEITURA.dados, TEM_INS: "" } }, AGORA), null);
  assert.strictEqual(M.parseEstacao({}, AGORA), null);
});

test("estação: coordenadas valem mais que a distância informada pela API", () => {
  const cg = { ...LEITURA, estacao: { ...LEITURA.estacao, DISTANCIA_EM_KM: "71", LATITUDE: "-20.45", LONGITUDE: "-54.61" } };
  assert.ok(M.parseEstacao(cg, AGORA, -20.4428, -54.6464).distancia_km < 5);
  assert.strictEqual(M.parseEstacao(LEITURA, AGORA, -20.44, -54.64), null);
});

const EMBRAPA = [1, "Dourados Embrapa", -22.2753, -54.8183];
const REAL = { day: "04/11/2026 18:00", temp_c_avg: "31.9", urc_pctg_avg: "52.0", u2m_ms: "4.3" };
const HOJE = { day: "2026-11-04", temp_c_max: "35.4", temp_c_min: "24.5" };

test("Embrapa: converte a leitura, o fuso local e os extremos do dia", () => {
  const r = M.parseGuiaClima(REAL, HOJE, EMBRAPA, -22.22, -54.81, Date.parse("2026-11-04T22:07:00Z"));
  assert.strictEqual(r.temperatura, 31.9);
  assert.strictEqual(r.hoje_max, 35.4);
  assert.strictEqual(r.vento_kmh, 15.5);
  assert.strictEqual(r.quando, "2026-11-04T22:00:00.000Z");
  assert.ok(r.distancia_km < 10);
});

test("Embrapa: recusa leitura antiga ou vazia e ignora extremos de outro dia", () => {
  const agora = Date.parse("2026-11-04T22:07:00Z");
  assert.strictEqual(M.parseGuiaClima(REAL, HOJE, EMBRAPA, -22.22, -54.81, agora + 4 * 3600e3), null);
  assert.strictEqual(M.parseGuiaClima({ ...REAL, temp_c_avg: "" }, HOJE, EMBRAPA, -22.22, -54.81, agora), null);
  assert.strictEqual(M.parseGuiaClima(REAL, { ...HOJE, day: "2026-11-03" }, EMBRAPA, -22.22, -54.81, agora).hoje_max, null);
});

test("previsão INMET: junta períodos e aceita dias simples", () => {
  const p = M.parsePrevisaoInmet({ "5003702": { "04/11/2026": { manha: { temp_min: 23, temp_max: 36 }, tarde: { temp_min: 24, temp_max: 35 } },
    "06/11/2026": { temp_min: 23, temp_max: 34, resumo: "Chuva" } } }, "5003702");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(p)), { "2026-11-04": [23, 36], "2026-11-06": [23, 34] });
});

test("faixa: extremos dos modelos por dia, exigindo ao menos dois", () => {
  const faixa = M.parseFaixa({ daily: { time: ["2026-11-04", "2026-11-05"],
    temperature_2m_max_ecmwf_ifs025: [33.2, null], temperature_2m_max_icon_global: [35, null], temperature_2m_max_gfs_seamless: [36.7, 33] } });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(faixa)), { "2026-11-04": [33.2, 36.7] });
});
