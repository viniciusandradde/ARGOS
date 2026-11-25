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
