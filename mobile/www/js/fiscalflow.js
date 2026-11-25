// Integração opcional com o FiscalFlow (contrato ARGOS v1, ADR-007 do FiscalFlow).
// A nota confirmada entra numa fila IndexedDB própria e só sai dela após confirmação
// do servidor. Valores em centavos. Não envia CPF, XML, URL do QR nem dados de cartão.
// Consumo e baixa de estoque nunca são enviados (não são despesa).
"use strict";

const FiscalFlow = (() => {
  const CONFIG = "argos-fiscalflow";
  const ROTA = "/api/integrations/argos/v1/purchases";
  const BACKOFF_BASE = 30000;        // 30 s
  const BACKOFF_MAX = 6 * 3600000;   // 6 h

  // HTTPS obrigatório, exceto aparelho/servidor local de teste.
  function urlValida(url) {
    try {
      const u = new URL(url);
      const local = u.hostname === "127.0.0.1" || u.hostname === "localhost";
      return (u.protocol === "https:" || (local && u.protocol === "http:")) && !u.username && !u.password && !u.search && !u.hash;
    } catch { return false; }
  }

  function texto(v, max) { return String(v ?? "").trim().slice(0, max); }

  // Monta o payload mínimo a partir da nota registrada em Compras.
  function payload(nota, revisao = 1) {
    if (!/^\d{44}$/.test(nota?.chave || "")) throw new Error("Nota sem chave fiscal válida.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(nota.data || "")) throw new Error("Nota sem data válida.");
    if (!Number.isSafeInteger(nota.total) || nota.total <= 0) throw new Error("Nota sem total válido.");
    const itens = (nota.produtos || []).slice(0, 500).map(p => ({
      description: texto(p.nome, 120), quantity: Number(p.quantidade) > 0 ? Number(p.quantidade) : 1,
      unit: texto(p.unidade, 10), total_cents: Number.isSafeInteger(p.total) && p.total >= 0 ? p.total : 0,
    }));
    return {
      schema_version: 1, purchase_id: "argos-" + nota.chave, fiscal_key: nota.chave,
      merchant: texto(nota.mercado, 200) || "Estabelecimento não identificado", purchase_date: nota.data,
      total_cents: nota.total, currency: "BRL", revision: revisao, items: itens,
      ...(Array.isArray(nota.pagamentos) && nota.pagamentos.length ? { payment_methods: nota.pagamentos.slice(0, 10) } : {}),
    };
  }

  // Decide o destino do item da fila após a resposta HTTP (status 0 = sem rede).
  function resultado(status, tentativas, agora) {
    if (status >= 200 && status < 300) return { acao: "remover" };
    if (status === 409) return { acao: "conflito" };          // revisão humana no FiscalFlow
    if (status === 401 || status === 403) return { acao: "sessao" }; // precisa entrar de novo
    if (status === 400 || status === 404 || status === 413) return { acao: "rejeitada" };
    const n = tentativas + 1;
    return { acao: "reagendar", tentativas: n, proxima: agora + Math.min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (n - 1)) };
  }

  // ---- Configuração (sem senha guardada; somente URL, e-mail e token de sessão) ----
  const lerConfig = () => { try { return JSON.parse(localStorage.getItem(CONFIG)) || {}; } catch { return {}; } };
  const salvarConfig = c => localStorage.setItem(CONFIG, JSON.stringify(c));

  async function entrar(url, email, senha, fetchImpl = fetch) {
    url = String(url || "").trim().replace(/\/+$/, "");
    if (!urlValida(url)) throw new Error("Informe o endereço HTTPS do FiscalFlow.");
    const r = await fetchImpl(url + "/api/collections/users/auth-with-password", {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit",
      body: JSON.stringify({ identity: email, password: senha }),
    });
    if (!r.ok) throw new Error("Não foi possível entrar no FiscalFlow.");
    const dados = await r.json();
    salvarConfig({ url, email: texto(email, 200), token: dados.token });
  }
  const sair = () => salvarConfig({ ...lerConfig(), token: "" });
  const ativo = () => { const c = lerConfig(); return !!(c.url && c.token); };

  // ---- Fila IndexedDB (banco separado do argos-compras) ----
  let conexao;
  function banco() {
    if (!conexao) conexao = new Promise((resolve, reject) => {
      const req = indexedDB.open("argos-fiscalflow", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("fila", { keyPath: "chave" });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }).catch(e => { conexao = null; throw e; });
    return conexao;
  }
  async function operar(modo, fn) {
    const db = await banco();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("fila", modo);
      const r = fn(tx.objectStore("fila"));
      tx.oncomplete = () => resolve(r?.result);
      tx.onabort = () => reject(tx.error);
    });
  }

  // Enfileira (ou mantém) a nota; uma nota já na fila não é duplicada.
  async function enfileirar(nota, agora = Date.now()) {
    const corpo = payload(nota);
    return operar("readwrite", s => {
      const g = s.get(nota.chave);
      g.onsuccess = () => { if (!g.result) s.put({ chave: nota.chave, payload: corpo, estado: "pendente", tentativas: 0, proxima: agora }); };
      return g;
    });
  }
  const listar = () => operar("readonly", s => s.getAll());

  // Envia os itens vencidos (ou todos os pendentes, com forcar = envio manual). Nunca remove sem 2xx.
  async function processar({ fetchImpl = fetch, agora = Date.now(), forcar = false } = {}) {
    const cfg = lerConfig();
    const contagem = { enviadas: 0, pendentes: 0, conflitos: 0, rejeitadas: 0, sessao: false };
    if (!cfg.url || !cfg.token) return contagem;
    for (const item of await listar()) {
      if (item.estado !== "pendente" || (!forcar && item.proxima > agora) || contagem.sessao) { if (item.estado === "pendente") contagem.pendentes++; continue; }
      let status = 0;
      try {
        const r = await fetchImpl(cfg.url + ROTA, {
          method: "POST", credentials: "omit",
          headers: { "Content-Type": "application/json", Authorization: cfg.token },
          body: JSON.stringify(item.payload),
        });
        status = r.status;
      } catch { status = 0; }
      const d = resultado(status, item.tentativas, agora);
      if (d.acao === "remover") { await operar("readwrite", s => s.delete(item.chave)); contagem.enviadas++; continue; }
      if (d.acao === "sessao") { contagem.sessao = true; contagem.pendentes++; continue; }
      const novo = d.acao === "reagendar" ? { ...item, tentativas: d.tentativas, proxima: d.proxima }
        : { ...item, estado: d.acao === "conflito" ? "conflito" : "rejeitada" };
      await operar("readwrite", s => s.put(novo));
      if (d.acao === "reagendar") contagem.pendentes++; else if (d.acao === "conflito") contagem.conflitos++; else contagem.rejeitadas++;
    }
    if (contagem.sessao) sair();
    return contagem;
  }

  // Orçamento do mês no FiscalFlow para uma categoria (somente leitura). Retorna null sem conexão ou categoria.
  function linhaOrcamento(resposta, categoria) {
    const alvo = String(categoria || "").trim().toLocaleLowerCase("pt-BR");
    return (resposta?.categories || []).find(c => String(c.category).toLocaleLowerCase("pt-BR") === alvo) || null;
  }
  async function orcamento({ fetchImpl = fetch, data = new Date() } = {}) {
    const cfg = lerConfig();
    if (!cfg.url || !cfg.token) return null;
    const r = await fetchImpl(`${cfg.url}/api/integrations/argos/v1/budget?year=${data.getFullYear()}&month=${data.getMonth() + 1}`,
      { headers: { Authorization: cfg.token }, credentials: "omit" });
    if (r.status === 401 || r.status === 403) { sair(); return null; }
    if (!r.ok) throw new Error("Orçamento indisponível.");
    return linhaOrcamento(await r.json(), cfg.categoria || "Supermercado");
  }
  const definirCategoria = categoria => salvarConfig({ ...lerConfig(), categoria: texto(categoria, 100) || "Supermercado" });

  return { urlValida, payload, resultado, entrar, sair, ativo, lerConfig, enfileirar, listar, processar, linhaOrcamento, orcamento, definirCategoria };
})();
if (typeof module !== "undefined") module.exports = FiscalFlow;
