"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const F = require("../www/js/fiscalflow");

const nota = { chave: "50261100000000000100650010000000011000000000", mercado: "Mercado de demonstração", data: "2026-11-20",
  total: 15990, produtos: [{ nome: "Arroz", codigo: "1", unidade: "UN", quantidade: 2, preco: 89.95, total: 17990 }],
  comparacao: [], registro: 1 };

test("payload mínimo em centavos, sem dados sensíveis e com total fiscal preservado", () => {
  const p = F.payload(nota);
  assert.deepEqual(Object.keys(p).sort(), ["currency", "fiscal_key", "items", "merchant", "purchase_date", "purchase_id",
    "revision", "schema_version", "total_cents"]);
  assert.equal(p.total_cents, 15990, "total da nota, não a soma dos itens (desconto)");
  assert.deepEqual(p.items, [{ description: "Arroz", quantity: 2, unit: "UN", total_cents: 17990 }]);
  assert.equal(p.purchase_id, "argos-" + nota.chave);
  for (const ruim of [{ chave: "1" }, { data: "20/11/2026" }, { total: 10.5 }, { total: 0 }]) {
    assert.throws(() => F.payload({ ...nota, ...ruim }));
  }
});

test("destino na fila conforme a resposta do FiscalFlow", () => {
  assert.equal(F.resultado(201, 0, 0).acao, "remover");
  assert.equal(F.resultado(200, 3, 0).acao, "remover");
  assert.equal(F.resultado(409, 0, 0).acao, "conflito");
  assert.equal(F.resultado(401, 0, 0).acao, "sessao");
  assert.equal(F.resultado(400, 0, 0).acao, "rejeitada");
  assert.deepEqual(F.resultado(0, 0, 1000), { acao: "reagendar", tentativas: 1, proxima: 31000 });
  assert.deepEqual(F.resultado(503, 2, 0), { acao: "reagendar", tentativas: 3, proxima: 120000 });
  assert.equal(F.resultado(429, 30, 0).proxima, 6 * 3600000, "teto de 6 horas");
});

test("somente HTTPS (ou servidor local de teste) e sem credenciais na URL", () => {
  assert.ok(F.urlValida("https://fiscalflow.exemplo.invalid"));
  assert.ok(F.urlValida("http://127.0.0.1:18090"));
  for (const u of ["http://fiscalflow.exemplo.invalid", "https://u:s@x.invalid", "ftp://x", "nada", "https://x.invalid/?t=1"]) {
    assert.ok(!F.urlValida(u), u);
  }
});

test("forma de pagamento da NFC-e: códigos tPag, troco descontado do dinheiro e envio no payload", () => {
  const N = require("../www/js/nfce");
  const f = N.formasPagamento([{ tPag: "01", vPag: "60.00" }, { tPag: "03", vPag: "20.00" }, { tPag: "17", vPag: "5.50" },
    { tPag: "11", vPag: "1.00" }, { tPag: "99", vPag: "2.00" }, { tPag: "90", vPag: "0.00" }], 300);
  assert.deepEqual(f, [{ type: "dinheiro", amount_cents: 5700 }, { type: "credito", amount_cents: 2000 }, { type: "pix", amount_cents: 550 },
    { type: "vale", amount_cents: 100 }, { type: "outro", amount_cents: 200 }]);
  assert.deepEqual(F.payload({ ...nota, pagamentos: [{ type: "debito", amount_cents: 15990 }] }).payment_methods, [{ type: "debito", amount_cents: 15990 }]);
  assert.equal(F.payload(nota).payment_methods, undefined);
});

test("linha de orçamento por categoria, sem diferenciar maiúsculas", () => {
  const r = { categories: [{ category: "Supermercado", budget_cents: 150000, realized_cents: 5700, pending_cents: 0, available_cents: 144300 }] };
  assert.equal(F.linhaOrcamento(r, "supermercado").available_cents, 144300);
  assert.equal(F.linhaOrcamento(r, "Lazer"), null);
  assert.equal(F.linhaOrcamento(null, "x"), null);
});

test("destino da nota: workspace válido entra no payload; inválido é ignorado", () => {
  assert.equal(F.payload(nota, 1, "abcdefghijklmno").workspace_id, "abcdefghijklmno");
  assert.equal(F.payload(nota, 1, "").workspace_id, undefined);
  assert.equal(F.payload(nota, 1, "../x").workspace_id, undefined);
});

// localStorage mínimo para as funções que guardam a configuração (Node não tem Web Storage por padrão).
function armazenamento() {
  const m = new Map();
  globalThis.localStorage = { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) };
}
const resposta = (status, corpo = {}) => ({ status, ok: status >= 200 && status < 300, json: async () => corpo });

test("cancelamento vai como nova revisão com status cancelled; nota ativa não leva status", () => {
  assert.equal(F.payload(nota).status, undefined);
  const c = F.payload(nota, 3, "", "cancelled");
  assert.equal(c.status, "cancelled");
  assert.equal(c.revision, 3);
});

test("testar conexão separa endereço inválido, sem resposta (rede/Tailscale) e erro HTTP", async () => {
  assert.equal((await F.testar("http://servidor.invalid")).motivo, "endereco");
  assert.equal((await F.testar("https://ff.invalid", async () => resposta(200))).ok, true);
  assert.equal((await F.testar("https://ff.invalid/", async () => resposta(502))).motivo, "http");
  assert.equal((await F.testar("https://ff.invalid", async () => { throw new TypeError("Failed to fetch"); })).motivo, "rede");
});

test("entrar mantém destino e categoria do mesmo servidor e pessoa; senha nunca é guardada", async () => {
  armazenamento();
  await F.entrar("https://ff.invalid/", "a@exemplo.invalid", "segredo", async () => resposta(200, { token: "t1" }), 1000);
  F.definirDestino("abcdefghijklmno", "Família"); F.definirCategoria("Mercado");
  await F.entrar("https://ff.invalid", "a@exemplo.invalid", "segredo", async () => resposta(200, { token: "t2" }), 2000);
  const c = F.lerConfig();
  assert.deepEqual([c.token, c.workspace, c.categoria, c.renovado], ["t2", "abcdefghijklmno", "Mercado", 2000]);
  assert.ok(!JSON.stringify(c).includes("segredo"));
  await F.entrar("https://outro.invalid", "a@exemplo.invalid", "segredo", async () => resposta(200, { token: "t3" }));
  assert.equal(F.lerConfig().workspace, undefined, "outro servidor: destino zerado");
  await assert.rejects(F.entrar("https://ff.invalid", "a@exemplo.invalid", "x", async () => resposta(400)), /não conferem/);
  await assert.rejects(F.entrar("https://ff.invalid", "a@exemplo.invalid", "x", async () => { throw new TypeError(); }), /Tailscale/);
});

test("sessão renovada uma vez por dia; 401 encerra a sessão; sem rede nada muda", async () => {
  armazenamento();
  await F.entrar("https://ff.invalid", "a@exemplo.invalid", "s", async () => resposta(200, { token: "t1" }), 0);
  assert.equal(await F.renovar({ agora: 3600000, fetchImpl: async () => resposta(200, { token: "x" }) }), "nada");
  assert.equal(await F.renovar({ agora: 25 * 3600000, fetchImpl: async () => { throw new TypeError(); } }), "sem_rede");
  assert.equal(F.lerConfig().token, "t1");
  assert.equal(await F.renovar({ agora: 25 * 3600000, fetchImpl: async () => resposta(200, { token: "t2" }) }), "renovada");
  assert.deepEqual([F.lerConfig().token, F.lerConfig().renovado], ["t2", 25 * 3600000]);
  assert.equal(await F.renovar({ agora: 50 * 3600000, fetchImpl: async () => resposta(401) }), "expirada");
  assert.equal(F.ativo(), false);
  assert.equal(F.configurado(), true, "o endereço fica: a fila espera o novo login");
});

test("destinos: lista só com escrita; sem rede ou erro devolve null (o app mantém o destino)", async () => {
  armazenamento();
  await F.entrar("https://ff.invalid", "a@exemplo.invalid", "s", async () => resposta(200, { token: "t" }));
  const itens = [{ id: "a", name: "Casa", role: "editor" }, { id: "b", name: "Leitura", role: "viewer" }];
  assert.deepEqual(await F.destinos({ fetchImpl: async () => resposta(200, { items: itens }) }), [{ id: "a", nome: "Casa" }]);
  assert.equal(await F.destinos({ fetchImpl: async () => { throw new TypeError(); } }), null);
  assert.equal(await F.destinos({ fetchImpl: async () => resposta(502) }), null);
});

test("Pix estático (tPag 20) também é pix", () => {
  const N = require("../www/js/nfce");
  assert.deepEqual(N.formasPagamento([{ tPag: "20", vPag: "10.00" }]), [{ type: "pix", amount_cents: 1000 }]);
});
