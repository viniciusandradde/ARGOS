// Quantidades usam a precisão comercial da NFC-e (quatro casas); totais estão em centavos.
"use strict";

const Compras = (() => {
  const arredondar = n => Number(n.toFixed(4));
  const normalizar = s => s.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").toUpperCase();
  function unidade(valor) {
    const u = normalizar(valor);
    return ["UND", "UNID", "UNIDADE", "UNIDADES"].includes(u) ? "UN" : u;
  }
  const idProduto = (nome, u) => JSON.stringify([normalizar(nome), unidade(u)]);
  const idVinculo = (nota, p) => JSON.stringify([nota.chave.slice(6, 20), p.codigo, normalizar(p.nome), unidade(p.unidade)]);
  const falta = p => arredondar(Math.max(0, p.avulso, p.meta - p.saldo));
  const vazio = () => ({ produtos: {}, vinculos: {} });

  function quantidade(valor) {
    const v = String(valor).trim().replace(",", ".");
    if (!/^\d+(\.\d{1,4})?$/.test(v) || !Number.isSafeInteger(Math.round(Number(v) * 10000))) {
      throw new Error("Informe uma quantidade positiva ou zero, com até quatro casas decimais.");
    }
    return Number(v);
  }

  function produto(catalogo, nome, un) {
    nome = nome.trim();
    const u = unidade(un);
    if (!nome || !u) throw new Error("Preencha o produto e a unidade.");
    const id = idProduto(nome, u);
    return catalogo.produtos[id] ??= { id, nome, unidade: u, saldo: 0, meta: 0, avulso: 0 };
  }

  function ajustar(cat, nome, un, operacao, valor) {
    const q = quantidade(valor);
    const p = produto(cat, nome, un);
    switch (operacao) {
      case "meta": p.meta = q; break;
      case "avulso": p.avulso = q; break;
      case "saldo": p.saldo = q; break;
      case "consumo":
        if (q <= 0 || q > p.saldo) throw new Error("O consumo deve ser maior que zero e caber no saldo.");
        p.saldo = arredondar(p.saldo - q);
        break;
      default: throw new Error("Operação inválida.");
    }
  }

  function sugerirVinculo(cat, nota, item) {
    return cat.vinculos[idVinculo(nota, item)] || idProduto(item.nome, item.unidade);
  }

  function registrar(cat, nota, escolhas) {
    const antes = new Map();
    for (const p of Object.values(cat.produtos)) {
      const previsto = falta(p);
      if (previsto) antes.set(p.id, { nome: p.nome, unidade: p.unidade, previsto, avulso: p.avulso, comprado: 0 });
    }
    const produtos = nota.produtos.map((item, i) => {
      const id = escolhas[i] || sugerirVinculo(cat, nota, item);
      const p = cat.produtos[id] || produto(cat, item.nome, item.unidade);
      if (p.id !== id || p.unidade !== unidade(item.unidade)) throw new Error("Confira a unidade do vínculo.");
      const q = quantidade(item.quantidade);
      if (!q) throw new Error("Produto sem quantidade.");
      p.saldo = arredondar(p.saldo + q);
      p.avulso = arredondar(Math.max(0, p.avulso - q));
      cat.vinculos[idVinculo(nota, item)] = p.id;
      const linha = antes.get(p.id) || { nome: p.nome, unidade: p.unidade, previsto: 0, avulso: 0, comprado: 0 };
      linha.comprado = arredondar(linha.comprado + q);
      antes.set(p.id, linha);
      return { ...item, produtoId: p.id };
    });
    return { ...nota, produtos, comparacao: Array.from(antes.values()), registro: Date.now() };
  }

  // Read current stock and insert the unique receipt in the same transaction, including across tabs.
  let conexao;
  function banco() {
    if (!conexao) conexao = new Promise((resolve, reject) => {
      const req = indexedDB.open("argos-compras", 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore("catalogo");
        req.result.createObjectStore("notas", { keyPath: "chave" });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }).catch(e => { conexao = null; throw e; });
    return conexao;
  }

  async function alterar(aplicar) {
    const db = await banco();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["catalogo", "notas"], "readwrite");
      const store = tx.objectStore("catalogo");
      const req = store.get(1);
      let erro;
      req.onsuccess = () => {
        try {
          const cat = req.result || vazio();
          const nota = aplicar(cat);
          if (nota) tx.objectStore("notas").add(nota);
          store.put(cat, 1);
        } catch (e) { erro = e; tx.abort(); }
      };
      tx.oncomplete = () => resolve();
      tx.onabort = () => reject(erro || (tx.error?.name === "ConstraintError"
        ? new Error("Esta NFC-e já foi registrada.") : new Error("Falha ao salvar a compra no aparelho.")));
    });
  }

  async function ler() {
    const db = await banco();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["catalogo", "notas"]);
      const c = tx.objectStore("catalogo").get(1);
      const n = tx.objectStore("notas").getAll();
      tx.oncomplete = () => resolve({ cat: c.result || vazio(), notas: n.result.sort((a, b) => b.registro - a.registro) });
      tx.onabort = () => reject(tx.error);
    });
  }
  // ---- Backup: estoque, listas e histórico deste aparelho, para guardar ou levar a outro aparelho/app ----
  const FORMATO = "argos-compras";
  async function exportar(agora = new Date()) {
    const { cat, notas } = await ler();
    return { formato: FORMATO, versao: 1, exportado_em: agora.toISOString(), catalogo: cat, notas };
  }
  function validarBackup(obj) {
    if (!obj || obj.formato !== FORMATO || obj.versao !== 1) throw new Error("Este arquivo não é um backup de compras do ARGOS.");
    const c = obj.catalogo;
    if (!c || typeof c !== "object" || !c.produtos || typeof c.produtos !== "object" || Array.isArray(c.produtos)) {
      throw new Error("Backup sem catálogo de produtos válido.");
    }
    if (!Array.isArray(obj.notas) || obj.notas.length > 20000) throw new Error("Backup com lista de notas inválida.");
    const chaves = new Set();
    for (const n of obj.notas) {
      if (!/^\d{44}$/.test(n?.chave || "") || chaves.has(n.chave)) throw new Error("Backup com nota sem chave válida ou repetida.");
      chaves.add(n.chave);
    }
    return { catalogo: { produtos: c.produtos, vinculos: c.vinculos && typeof c.vinculos === "object" ? c.vinculos : {} }, notas: obj.notas };
  }
  // Substitui as compras deste aparelho pelo conteúdo do backup (uma transação: tudo ou nada).
  async function restaurar(obj) {
    const dados = validarBackup(obj);
    const db = await banco();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["catalogo", "notas"], "readwrite");
      tx.objectStore("catalogo").put(dados.catalogo, 1);
      const notas = tx.objectStore("notas");
      notas.clear();
      for (const n of dados.notas) notas.put(n);
      tx.oncomplete = () => resolve(dados.notas.length);
      tx.onabort = () => reject(tx.error || new Error("Falha ao restaurar o backup."));
    });
  }
  return { unidade, idProduto, falta, vazio, ajustar, sugerirVinculo, registrar, alterar, ler, exportar, validarBackup, restaurar };
})();
if (typeof module !== "undefined") module.exports = Compras;
