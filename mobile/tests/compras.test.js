"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../www/js/compras");
const N = require("../www/js/nfce");
const chave = "50261100000000000100650010000000011000000000";

test("o QR usa somente o portal autorizado, por HTTPS, e confere modelo, ambiente e dígito", () => {
  const base = "http://www.dfe.ms.gov.br/nfce/qrcode?p=";
  assert.equal(N.consulta(base + chave + "%7C3%7C1").chave, chave);
  assert.match(N.consulta(base + chave + "|3|1").url, /^https:/);
  for (const url of [base + chave + "|3|2", base.replace("ms.gov.br", "ms.gov.br.example") + chave,
    base + chave.slice(0, -1) + "1|3|1", base + chave.replace("6500", "5500") + "|3|1"]) {
    assert.throws(() => N.consulta(url));
  }
});

test("a nota agrega itens repetidos, preserva extras e faltas e reutiliza os vínculos", () => {
  const cat = C.vazio();
  C.ajustar(cat, "Café", "un", "meta", 5);
  C.ajustar(cat, "Café", "un", "saldo", 1);
  C.ajustar(cat, "Café", "un", "avulso", 3);
  C.ajustar(cat, "Leite", "L", "avulso", 2);
  const id = C.idProduto("CAFE", "UND");
  const cafe = { nome: "CAFE PCT 500G", unidade: "UN", codigo: "445", quantidade: 1 };
  const nota = { chave, produtos: [cafe, cafe, { nome: "Manga", unidade: "KG", quantidade: 0.125, codigo: "99" }] };
  const compra = C.registrar(cat, nota, [id, id]);
  assert.deepEqual(compra.comparacao.map(p => [p.nome, p.previsto, p.comprado]),
    [["Café", 4, 2], ["Leite", 2, 0], ["Manga", 0, 0.125]]);
  assert.equal(C.sugerirVinculo(cat, nota, cafe), id);
  assert.equal(cat.produtos[id].avulso, 1);
  assert.equal(C.falta(cat.produtos[id]), 2);
  C.ajustar(cat, "Café", "un", "consumo", "0,25");
  assert.equal(C.falta(cat.produtos[id]), 2.25);
  assert.equal(compra.comparacao[0].previsto, 4);
});

test("quantidades inválidas, unidades incompatíveis e consumo acima do saldo são rejeitados", () => {
  const cat = C.vazio();
  for (const q of ["-1", "x", "", "Infinity", "1.00001"]) assert.throws(() => C.ajustar(cat, "A", "UN", "saldo", q));
  C.ajustar(cat, "A", "KG", "saldo", 1);
  assert.throws(() => C.ajustar(cat, "A", "KG", "consumo", 2));
  const nota = { chave, produtos: [{ nome: "A", unidade: "G", quantidade: 1 }] };
  assert.throws(() => C.registrar(cat, nota, [C.idProduto("A", "KG")]));
  assert.equal(cat.produtos[C.idProduto("A", "KG")].saldo, 1);
});
