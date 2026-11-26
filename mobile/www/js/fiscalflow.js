// Integração opcional com o FiscalFlow (contrato ARGOS v1, ADR-007/012 do FiscalFlow).
// A nota confirmada entra numa fila IndexedDB própria e só sai dela após confirmação do servidor; o que já foi aceito
// fica em "enviadas" (com a revisão), para cancelar depois. Valores em centavos. Não envia CPF, XML, URL do QR nem
// dados de cartão. Consumo e baixa de estoque nunca são enviados (não são despesa).
"use strict";

const FiscalFlow = (() => {
  const CONFIG = "argos-fiscalflow";
  const ROTA = "/api/integrations/argos/v1/purchases";
  const BACKOFF_BASE = 30000;          // 30 s
  const BACKOFF_MAX = 6 * 3600000;     // 6 h
  const RENOVAR_MS = 24 * 3600000;     // renova a sessão uma vez por dia (o token do PocketBase expira)

  // HTTPS obrigatório, exceto aparelho/servidor local de teste.
  function urlValida(url) {
    try {
      const u = new URL(url);
      const local = u.hostname === "127.0.0.1" || u.hostname === "localhost";
      return (u.protocol === "https:" || (local && u.protocol === "http:")) && !u.username && !u.password && !u.search && !u.hash;
    } catch { return false; }
  }
  const limparUrl = url => String(url || "").trim().replace(/\/+$/, "");

  function texto(v, max) { return String(v ?? "").trim().slice(0, max); }

  // Monta o payload mínimo a partir da nota registrada em Compras.
  function payload(nota, revisao = 1, workspaceId = "", status = "active") {
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
      ...(status === "cancelled" ? { status: "cancelled" } : {}),
      ...(Array.isArray(nota.pagamentos) && nota.pagamentos.length ? { payment_methods: nota.pagamentos.slice(0, 10) } : {}),
      ...(/^[a-z0-9]{15}$/.test(workspaceId || "") ? { workspace_id: workspaceId } : {}),
    };
  }

  // Decide o destino do item da fila após a resposta HTTP (status 0 = sem rede).
  function resultado(status, tentativas, agora) {
    if (status >= 200 && status < 300) return { acao: "remover" };
    if (status === 409) return { acao: "conflito" };          // já existe com outro conteúdo: revisão humana
    if (status === 401 || status === 403) return { acao: "sessao" }; // precisa entrar de novo
    if (status === 400 || status === 404 || status === 413) return { acao: "rejeitada" };
    const n = tentativas + 1;
    return { acao: "reagendar", tentativas: n, proxima: agora + Math.min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (n - 1)) };
  }

  // ---- Configuração (sem senha guardada; somente URL, e-mail e token de sessão) ----
  const lerConfig = () => { try { return JSON.parse(localStorage.getItem(CONFIG)) || {}; } catch { return {}; } };
  const salvarConfig = c => localStorage.setItem(CONFIG, JSON.stringify(c));
  // Endereço sugerido quando o app é servido pelo servidor da família (config.js gerado no container).
  function urlPadrao() {
    const sugerida = limparUrl(typeof window !== "undefined" && window.ARGOS_CONFIG ? window.ARGOS_CONFIG.fiscalflowUrl : "");
    return urlValida(sugerida) ? sugerida : "";
  }

  async function entrar(url, email, senha, fetchImpl = fetch, agora = Date.now()) {
    url = limparUrl(url);
    if (!urlValida(url)) throw new Error("Informe o endereço HTTPS do FiscalFlow.");
    let r;
    try {
      r = await fetchImpl(url + "/api/collections/users/auth-with-password", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit",
        body: JSON.stringify({ identity: email, password: senha }),
      });
    } catch { throw new Error("Sem resposta do FiscalFlow. Confira a internet, a Tailscale ligada e o endereço."); }
    if (r.status === 400 || r.status === 401 || r.status === 403) throw new Error("E-mail ou senha não conferem no FiscalFlow.");
    if (!r.ok) throw new Error(`O FiscalFlow respondeu HTTP ${r.status}. Tente de novo.`);
    const dados = await r.json();
    const antes = lerConfig();
    // Mesmo servidor e mesma pessoa: mantém destino e categoria escolhidos.
    const mantem = antes.url === url && antes.email === texto(email, 200);
    salvarConfig({ ...(mantem ? antes : {}), url, email: texto(email, 200), token: dados.token, renovado: agora });
  }
  const sair = () => salvarConfig({ ...lerConfig(), token: "" });
  const configurado = () => !!lerConfig().url;
  const ativo = () => { const c = lerConfig(); return !!(c.url && c.token); };

  // Diagnóstico antes de entrar: separa endereço inválido, sem resposta (rede, Tailscale, certificado) e erro HTTP.
  async function testar(url, fetchImpl = fetch) {
    url = limparUrl(url);
    if (!urlValida(url)) return { ok: false, motivo: "endereco", msg: "Use o endereço HTTPS do FiscalFlow (ex.: https://servidor…ts.net:18443)." };
    try {
      const r = await fetchImpl(url + "/api/health", { credentials: "omit" });
      if (r.ok) return { ok: true, motivo: "ok", msg: "O FiscalFlow respondeu. Pode entrar." };
      return { ok: false, motivo: "http", msg: `O servidor respondeu HTTP ${r.status}. Confira o endereço.` };
    } catch {
      return { ok: false, motivo: "rede", msg: "Sem resposta. Confira a internet, se a Tailscale está ligada neste aparelho e o endereço." };
    }
  }

  // Renova o token uma vez por dia; 401/403 encerra a sessão (a fila continua guardada).
  async function renovar({ fetchImpl = fetch, agora = Date.now() } = {}) {
    const cfg = lerConfig();
    if (!cfg.url || !cfg.token || agora - (cfg.renovado || 0) < RENOVAR_MS) return "nada";
    let r;
    try { r = await fetchImpl(cfg.url + "/api/collections/users/auth-refresh", { method: "POST", headers: { Authorization: cfg.token }, credentials: "omit" }); }
    catch { return "sem_rede"; }
    if (r.status === 401 || r.status === 403) { sair(); return "expirada"; }
    if (!r.ok) return "falhou";
    const d = await r.json();
    if (d.token) salvarConfig({ ...lerConfig(), token: d.token, renovado: agora });
    return "renovada";
  }

  // ---- Banco IndexedDB "argos-fiscalflow": fila (a enviar) e enviadas (aceitas pelo servidor) ----
  let conexao;
  function banco() {
    if (!conexao) conexao = new Promise((resolve, reject) => {
      const req = indexedDB.open("argos-fiscalflow", 2);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("fila")) db.createObjectStore("fila", { keyPath: "chave" });
        if (!db.objectStoreNames.contains("enviadas")) db.createObjectStore("enviadas", { keyPath: "chave" });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }).catch(e => { conexao = null; throw e; });
    return conexao;
  }
  async function operar(stores, modo, fn) {
    const db = await banco();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(stores, modo);
      const r = fn(tx);
      tx.oncomplete = () => resolve(r?.result);
      tx.onabort = () => reject(tx.error);
    });
  }
  const obter = (store, chave) => operar([store], "readonly", tx => tx.objectStore(store).get(chave));
  const gravar = (store, valor) => operar([store], "readwrite", tx => tx.objectStore(store).put(valor));
  const apagar = (store, chave) => operar([store], "readwrite", tx => tx.objectStore(store).delete(chave));
  const listar = () => operar(["fila"], "readonly", tx => tx.objectStore("fila").getAll());
  const listarEnviadas = () => operar(["enviadas"], "readonly", tx => tx.objectStore("enviadas").getAll());

  // Enfileira a nota (uma nota já na fila ou já aceita não é duplicada). Vale também sem sessão: a nota espera o login.
  // O destino (pessoal ou workspace) é fixado na nota no momento em que entra na fila.
  async function enfileirar(nota, agora = Date.now()) {
    const corpo = payload(nota, 1, lerConfig().workspace || "");
    return operar(["fila", "enviadas"], "readwrite", tx => {
      const fila = tx.objectStore("fila");
      const g = fila.get(nota.chave);
      g.onsuccess = () => {
        if (g.result) return;
        const ja = tx.objectStore("enviadas").get(nota.chave);
        ja.onsuccess = () => { if (!ja.result) fila.put({ chave: nota.chave, payload: corpo, estado: "pendente", tentativas: 0, proxima: agora }); };
      };
      return g;
    });
  }

  // Cancela no FiscalFlow uma nota já aceita (nova revisão com status "cancelled"); se ainda estava só na fila, sai dela.
  async function cancelar(chave, agora = Date.now()) {
    const [naFila, enviada] = await Promise.all([obter("fila", chave), obter("enviadas", chave)]);
    if (naFila?.payload?.status === "cancelled") return "enfileirada";
    if (naFila && !enviada) { await apagar("fila", chave); return "removida"; }
    if (!enviada) throw new Error("Esta nota não foi enviada ao FiscalFlow.");
    if (enviada.estado === "cancelada") return "ja_cancelada";
    const corpo = { ...enviada.payload, revision: enviada.revisao + 1, status: "cancelled" };
    await gravar("fila", { chave, payload: corpo, estado: "pendente", tentativas: 0, proxima: agora });
    return "enfileirada";
  }
  // Conflito ou recusa: tentar de novo (depois de resolver no FiscalFlow) ou descartar o item da fila.
  async function reenviar(chave, agora = Date.now()) {
    const item = await obter("fila", chave);
    if (item) await gravar("fila", { ...item, estado: "pendente", tentativas: 0, proxima: agora });
  }
  const descartar = chave => apagar("fila", chave);

  // Situação de cada nota no FiscalFlow, para a tela:
  // { [chave]: "pendente" | "cancelando" | "conflito" | "rejeitada" | "enviada" | "cancelada" }.
  async function situacoes() {
    const out = {};
    for (const e of await listarEnviadas()) out[e.chave] = e.estado === "cancelada" ? "cancelada" : "enviada";
    for (const f of await listar()) out[f.chave] = f.estado === "pendente" && f.payload?.status === "cancelled" ? "cancelando" : f.estado;
    return out;
  }

  // Envia os itens vencidos (ou todos os pendentes, com forcar = envio manual). Nunca remove sem 2xx.
  async function processar({ fetchImpl = fetch, agora = Date.now(), forcar = false } = {}) {
    const cfg = lerConfig();
    const contagem = { enviadas: 0, pendentes: 0, conflitos: 0, rejeitadas: 0, sessao: false };
    const itens = await listar();
    if (!cfg.url || !cfg.token) {
      contagem.pendentes = itens.filter(i => i.estado === "pendente").length;
      contagem.semLogin = !!cfg.url && contagem.pendentes > 0;
      return contagem;
    }
    for (const item of itens) {
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
      if (d.acao === "remover") {
        const cancelada = item.payload.status === "cancelled";
        await operar(["fila", "enviadas"], "readwrite", tx => {
          tx.objectStore("fila").delete(item.chave);
          return tx.objectStore("enviadas").put({ chave: item.chave, revisao: item.payload.revision, estado: cancelada ? "cancelada" : "ativa", payload: item.payload, em: agora });
        });
        contagem.enviadas++;
        continue;
      }
      if (d.acao === "sessao") { contagem.sessao = true; contagem.pendentes++; continue; }
      const novo = d.acao === "reagendar" ? { ...item, tentativas: d.tentativas, proxima: d.proxima }
        : { ...item, estado: d.acao === "conflito" ? "conflito" : "rejeitada" };
      await gravar("fila", novo);
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
    const ws = cfg.workspace ? `&workspace=${encodeURIComponent(cfg.workspace)}` : "";
    const r = await fetchImpl(`${cfg.url}/api/integrations/argos/v1/budget?year=${data.getFullYear()}&month=${data.getMonth() + 1}${ws}`,
      { headers: { Authorization: cfg.token }, credentials: "omit" });
    if (r.status === 401 || r.status === 403) { sair(); return null; }
    if (!r.ok) throw new Error("Orçamento indisponível.");
    return linhaOrcamento(await r.json(), cfg.categoria || "Supermercado");
  }
  // Workspaces onde o usuário pode enviar notas (proprietário, admin ou editor).
  // null = não deu para saber agora (sem rede ou erro): quem chama mantém o destino escolhido.
  async function destinos({ fetchImpl = fetch } = {}) {
    const cfg = lerConfig();
    if (!cfg.url || !cfg.token) return null;
    let r;
    try { r = await fetchImpl(`${cfg.url}/api/fiscalflow/workspaces`, { headers: { Authorization: cfg.token }, credentials: "omit" }); }
    catch { return null; }
    if (!r.ok) return null;
    const { items = [] } = await r.json();
    return items.filter(w => ["owner", "admin", "editor"].includes(w.role)).map(w => ({ id: w.id, nome: texto(w.name, 120) }));
  }
  const definirDestino = (id, nome) => salvarConfig({ ...lerConfig(), workspace: /^[a-z0-9]{15}$/.test(id || "") ? id : "", workspaceNome: texto(nome, 120) });
  const definirCategoria = categoria => salvarConfig({ ...lerConfig(), categoria: texto(categoria, 100) || "Supermercado" });

  return { urlValida, urlPadrao, payload, resultado, entrar, sair, configurado, ativo, testar, renovar, lerConfig, enfileirar, cancelar,
    reenviar, descartar, situacoes, listar, processar, linhaOrcamento, orcamento, definirCategoria, destinos, definirDestino };
})();
if (typeof module !== "undefined") module.exports = FiscalFlow;
