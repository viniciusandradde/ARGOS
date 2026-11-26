"use strict";

function iniciarCompras({ $, el, toast }) {
  const C = Compras;
  const nomes = new Intl.Collator("pt-BR");
  const numero = n => n.toLocaleString("pt-BR", { maximumFractionDigits: 4 });
  const moeda = centavos => (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const precoUnitario = n => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 6 });
  const data = iso => iso ? iso.split("-").reverse().join("/") : "Data não informada";
  const vazio = msg => el("span", { class: "dim" }, msg);
  const linha = (a, b) => el("div", { class: "cp-linha" }, a, el("strong", {}, b));
  const status = msg => { $("cp-status").textContent = msg; };
  let cat = C.vazio(), notas = [], rascunho = null, escolhas = [], ffSituacoes = {}, ultimaSync = 0;
  let stream = null, timer = null, sessao = 0, leitura = 0, versaoTela = 0, salvando = false;

  function tabela(titulos, linhas) {
    return el("table", {}, el("thead", {}, el("tr", {}, ...titulos.map(t => el("th", { scope: "col" }, t)))),
      el("tbody", {}, ...linhas.map(cols => el("tr", {}, ...cols.map(col => el("td", {}, col))))));
  }
  function comparar(nota) {
    return el("ul", { class: "lst" }, ...nota.comparacao.map(p => {
      const dif = Number((p.comprado - p.previsto).toFixed(4));
      const resultado = dif < 0 ? "Falta " + numero(-dif) : dif > 0 ? "Extra " + numero(dif) : "Completo";
      return el("li", {}, linha(p.nome, resultado),
        el("div", { class: "meta" }, "Lista geral " + numero(p.avulso) + " · Previsto " + numero(p.previsto) +
          " · Comprado " + numero(p.comprado) + " (" + p.unidade + ")"));
    }));
  }

  // Situação da nota no FiscalFlow e as ações possíveis (enviar, cancelar). Recalculado a cada abertura.
  const SITUACAO = { pendente: "Na fila para o FiscalFlow", cancelando: "Cancelamento na fila do FiscalFlow",
    conflito: "Em conflito no FiscalFlow: veja a fila abaixo do login", rejeitada: "Recusada pelo FiscalFlow: veja a fila",
    enviada: "Enviada ao FiscalFlow", cancelada: "Cancelada no FiscalFlow" };
  async function acaoNota(fn, msg) {
    try { const r = await fn(); toast(r === "removida" ? "Nota retirada da fila do FiscalFlow." : msg); await sincronizar(true); render(); }
    catch (e) { toast(e.message); }
  }
  function acoesFiscalFlow(n) {
    if (!FiscalFlow.configurado()) return [];
    const s = ffSituacoes[n.chave];
    const out = [el("span", { class: "dim" }, SITUACAO[s] || "Ainda não enviada ao FiscalFlow")];
    if (!s) out.push(el("button", { type: "button", on: { click: () => acaoNota(() => FiscalFlow.enfileirar(n), "Nota na fila do FiscalFlow.") } }, "Enviar ao FiscalFlow"));
    if (s === "enviada" || s === "pendente") out.push(el("button", { type: "button", on: { click: () => {
      if (confirm("Cancelar esta nota no FiscalFlow? A compra continua registrada no ARGOS.")) acaoNota(() => FiscalFlow.cancelar(n.chave), "Cancelamento na fila do FiscalFlow.");
    } } }, "Cancelar no FiscalFlow"));
    return out;
  }

  function historico(n) {
    const titulo = n.mercado || "NFC-e";
    const detalhe = el("details", {}, el("summary", {}, data(n.data) + " · " + titulo + " · " + moeda(n.total)));
    const acoes = el("div", { class: "cp-ff" });
    detalhe.addEventListener("toggle", () => {
      if (!detalhe.open) return;
      acoes.replaceChildren(...acoesFiscalFlow(n));
      if (detalhe.children.length > 1) return;
      detalhe.append(acoes, tabela(["Produto da nota", "Quantidade", "Unitário", "Total do item"],
        n.produtos.map(p => [p.nome, numero(p.quantidade) + " " + p.unidade, precoUnitario(p.preco), moeda(p.total)])),
      el("h3", {}, "Comparação na hora da compra"), comparar(n),
      vazio("O previsto considera a lista geral e a reposição até o padrão mensal."));
    });
    return detalhe;
  }

  function render() {
    const produtos = Object.values(cat.produtos).sort((a, b) => nomes.compare(a.nome, b.nome));
    const faltas = produtos.filter(p => C.falta(p) > 0);
    $("cp-contagem").textContent = faltas.length === 1 ? "1 produto a comprar" : faltas.length + " produtos a comprar";
    $("cp-faltas").replaceChildren(...(faltas.length ? faltas.map(p => linha(p.nome, numero(C.falta(p)) + " " + p.unidade)) :
      [vazio(produtos.length ? "Tudo em dia com as suas listas." : "Cadastre sua lista ou importe a primeira nota.")]));
    $("cp-catalogo").replaceChildren(produtos.length ? tabela(["Produto", "Estoque", "Pendente"], produtos.map(p => {
      const editar = el("button", { type: "button", on: { click: () => {
        $("cp-nome").value = p.nome; $("cp-un").value = p.unidade; $("cp-qtd").focus();
      } } }, p.nome);
      return [editar, numero(p.saldo) + " " + p.unidade, numero(p.avulso) + " " + p.unidade];
    })) : vazio("Informe o que precisa comprar ou o que já tem em casa."));
    $("cp-nomes").replaceChildren(...produtos.map(p => el("option", { value: p.nome }, p.unidade)));
    const mensal = produtos.filter(p => p.meta > 0);
    $("cp-mensal").replaceChildren(...(mensal.length ? mensal.map(p => linha(p.nome, numero(p.meta) + " " + p.unidade)) :
      [vazio("Use a ação “Definir quantidade padrão do mês” para cadastrar os itens recorrentes.")]));
    $("cp-historico").replaceChildren(...(notas.length ? notas.map(historico) : [vazio("Nenhuma nota registrada.")]));
  }

  async function atualizar() {
    const v = ++versaoTela;
    const estado = await C.ler();
    if (v !== versaoTela) return;
    ({ cat, notas } = estado);
    render();
  }
  function entrada(habilitar) {
    for (const id of ["cp-scan", "cp-foto", "cp-link", "cp-xml"]) $(id).disabled = !habilitar;
    $("cp-link-form").querySelector("button").disabled = !habilitar;
  }
  function limpar() {
    rascunho = null; escolhas = [];
    $("cp-revisao").hidden = true; $("cp-previa").replaceChildren();
    $("cp-link").value = ""; $("cp-xml").value = ""; entrada(true);
  }
  function previa(nota) {
    if (notas.some(n => n.chave === nota.chave)) throw new Error("Esta NFC-e já foi registrada.");
    rascunho = nota; escolhas = [];
    const produtos = Object.values(cat.produtos);
    const campos = nota.produtos.map((item, i) => {
      const un = C.unidade(item.unidade);
      const id = C.idProduto(item.nome, un);
      const select = el("select", { "aria-label": "Vincular " + item.nome });
      if (!cat.produtos[id]) select.add(new Option("Cadastrar como " + item.nome, id));
      for (const p of produtos.filter(p => p.unidade === un)) select.add(new Option(p.nome, p.id));
      select.value = C.sugerirVinculo(cat, nota, item);
      escolhas[i] = select.value;
      select.addEventListener("change", () => { escolhas[i] = select.value; });
      return el("label", {}, item.nome + " · " + numero(item.quantidade) + " " + un + " · " + moeda(item.total), select);
    });
    $("cp-previa").replaceChildren(el("h3", {}, nota.mercado || "NFC-e"),
      el("p", {}, data(nota.data) + " · " + nota.produtos.length + (nota.produtos.length === 1 ? " item" : " itens") + " · Total da nota " + moeda(nota.total)),
      el("p", {}, "Confira os itens e escolha o produto correspondente da sua lista."), ...campos);
    $("cp-revisao").hidden = false;
    $("cp-alternativas").open = false;
    $("cp-revisao").scrollIntoView({ block: "start" });
    status("Nota pronta para conferência.");
  }

  async function importar(carregar, qrLido = false) {
    const tentativa = ++leitura;
    pararCamera(); entrada(false);
    status(qrLido ? "QR Code lido. Consultando a nota na SEFAZ…" : "Lendo os produtos da nota…");
    try {
      const nota = await carregar();
      await atualizar();
      if (leitura === tentativa) previa(nota);
    } catch (e) {
      if (leitura === tentativa) {
        status((qrLido ? "QR Code lido. " : "") + e.message);
        if (qrLido) $("cp-alternativas").open = true;
      }
    } finally {
      if (leitura === tentativa && !rascunho) entrada(true);
      $("cp-xml").value = "";
    }
  }

  function consultarQr(valor) {
    return importar(() => {
      const { url } = Nfce.consulta(valor);
      $("cp-link").value = url;
      return Nfce.buscar(url);
    }, true);
  }

  async function capturarQr(obterValor, mensagem) {
    const tentativa = ++leitura;
    pararCamera(); entrada(false); status(mensagem);
    try {
      const valor = await obterValor();
      if (tentativa !== leitura) return;
      if (valor) await consultarQr(valor);
      else status("Leitura cancelada.");
    } catch (e) {
      if (tentativa === leitura) { status(e.message); $("cp-alternativas").open = true; }
    } finally {
      if (tentativa === leitura && !rascunho) entrada(true);
    }
  }

  $("cp-foto").addEventListener("change", () => {
    const foto = $("cp-foto").files[0];
    $("cp-foto").value = "";
    if (!foto) return;
    capturarQr(async () => {
      let imagem;
      try { imagem = await createImageBitmap(foto); }
      catch { throw new Error("Não foi possível abrir a foto. Escolha uma imagem JPEG ou PNG."); }
      try {
        const canvas = document.createElement("canvas");
        const escala = Math.min(1, 2400 / Math.max(imagem.width, imagem.height));
        canvas.width = Math.max(1, Math.round(imagem.width * escala));
        canvas.height = Math.max(1, Math.round(imagem.height * escala));
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(imagem, 0, 0, canvas.width, canvas.height);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const qr = jsQR(pixels.data, pixels.width, pixels.height);
        if (qr) return qr.data;
        throw new Error("QR Code não encontrado. Escolha uma foto nítida com o código inteiro.");
      } finally { imagem.close(); }
    }, "Procurando o QR Code na foto…");
  });

  $("cp-link-form").addEventListener("submit", e => {
    e.preventDefault(); importar(() => Nfce.buscar($("cp-link").value));
  });
  $("cp-xml").addEventListener("change", () => {
    const arquivo = $("cp-xml").files[0];
    if (arquivo) importar(async () => Nfce.xml(await arquivo.text()));
  });
  $("cp-cancelar").addEventListener("click", () => { limpar(); status("Leitura descartada."); });
  $("cp-confirmar").addEventListener("click", async () => {
    if (salvando || !rascunho) return;
    salvando = true; $("cp-confirmar").disabled = true; $("cp-cancelar").disabled = true;
    try {
      const notaConfirmada = rascunho;
      await C.alterar(catAtual => C.registrar(catAtual, rascunho, escolhas));
      limpar(); status("Compra registrada. Estoque e lista atualizados."); toast("Compra registrada.");
      // Com o FiscalFlow configurado, a nota sempre entra na fila, mesmo sem sessão ou sem rede: espera o login ou a conexão.
      if (FiscalFlow.configurado()) FiscalFlow.enfileirar(notaConfirmada).then(() => sincronizar()).catch(() => estadoFiscalFlow("Nota não entrou na fila do FiscalFlow."));
      await atualizar();
    } catch (e) { status(e.message); toast(e.message); }
    finally { salvando = false; $("cp-confirmar").disabled = false; $("cp-cancelar").disabled = false; }
  });
  $("cp-ajuste").addEventListener("submit", async e => {
    e.preventDefault();
    const botao = e.currentTarget.querySelector("button");
    if (botao.disabled) return;
    botao.disabled = true;
    try {
      const args = ["cp-nome", "cp-un", "cp-acao", "cp-qtd"].map(id => $(id).value);
      await C.alterar(c => C.ajustar(c, ...args));
      $("cp-qtd").value = ""; toast("Quantidade salva."); await atualizar();
    } catch (erro) { toast(erro.message); }
    finally { botao.disabled = false; }
  });

  function pararCamera() {
    sessao++;
    clearTimeout(timer);
    stream?.getTracks().forEach(t => t.stop());
    stream = null; $("cp-video").srcObject = null; $("cp-camera").hidden = true;
  }
  $("cp-scan").addEventListener("click", async () => {
    const cap = window.Capacitor;
    if (cap?.getPlatform?.() === "android") {
      await capturarQr(async () => {
        const resultado = await cap.Plugins.LeitorQr.escanear();
        return resultado?.valor;
      }, "Abrindo o leitor de QR Code…");
      return;
    }
    pararCamera();
    const atual = sessao;
    status("Aponte a câmera para o QR Code da NFC-e.");
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error();
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (atual !== sessao) { s.getTracks().forEach(t => t.stop()); return; }
      stream = s;
      const video = $("cp-video"); video.srcObject = s; $("cp-camera").hidden = false;
      await video.play();
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      function quadro() {
        if (atual !== sessao) return;
        if (video.readyState >= 2 && video.videoWidth > 0) {
          canvas.width = Math.min(1024, video.videoWidth);
          canvas.height = Math.round(video.videoHeight * canvas.width / video.videoWidth);
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const qr = jsQR(pixels.data, pixels.width, pixels.height, { inversionAttempts: "dontInvert" });
          if (qr) { consultarQr(qr.data); return; }
        }
        timer = setTimeout(quadro, 140);
      }
      quadro();
    } catch {
      if (atual === sessao) { pararCamera(); status("Câmera indisponível. Autorize o acesso ou use o link ou XML."); }
    }
  });
  // ---- Integração opcional com o FiscalFlow: fila local, reenvio com backoff, sem senha guardada ----
  function estadoFiscalFlow(msg) { $("ff-estado").textContent = msg; }
  async function sincronizar(manual = false) {
    if (!FiscalFlow.configurado()) return;
    ultimaSync = Date.now();
    try {
      if (FiscalFlow.ativo()) await FiscalFlow.renovar();
      const r = await FiscalFlow.processar({ forcar: manual === true });
      const partes = [];
      if (r.enviadas) partes.push(`${r.enviadas} enviada(s)`);
      if (r.pendentes) partes.push(`${r.pendentes} aguardando reenvio`);
      if (r.conflitos) partes.push(`${r.conflitos} em conflito (revise no FiscalFlow)`);
      if (r.rejeitadas) partes.push(`${r.rejeitadas} recusada(s)`);
      if (r.sessao) partes.push("sessão expirada: conecte de novo");
      if (r.semLogin) partes.push("entre no FiscalFlow para enviar");
      estadoFiscalFlow(partes.length ? partes.join(" · ") : FiscalFlow.ativo() ? "Conectado. Nada pendente." : "Desconectado.");
    } catch { estadoFiscalFlow("Fila do FiscalFlow indisponível neste aparelho."); }
    telaFiscalFlow();
    await carregarDestinos();
    mostrarOrcamento();
    await mostrarFila();
  }

  // Fila visível: o que espera envio, o que está em conflito e o que foi recusado, com as ações de cada um.
  const ROTULO_FILA = { pendente: "aguardando envio", conflito: "já existe no FiscalFlow com outro conteúdo: confira lá",
    rejeitada: "recusada (destino sem permissão ou dados inválidos)" };
  async function mostrarFila() {
    let itens = [];
    try { itens = await FiscalFlow.listar(); ffSituacoes = await FiscalFlow.situacoes(); } catch { return; }
    const caixa = $("ff-fila");
    if (!itens.length) { caixa.replaceChildren(); return; }
    const botao = (rotulo, fn) => el("button", { type: "button", on: { click: async () => { await fn(); await sincronizar(true); } } }, rotulo);
    caixa.replaceChildren(el("h3", {}, "Fila do FiscalFlow"), el("ul", { class: "lst" }, ...itens.map(i => {
      const p = i.payload || {};
      const cancel = p.status === "cancelled";
      const rotulo = cancel && i.estado === "pendente" ? "cancelamento aguardando envio" : ROTULO_FILA[i.estado] || i.estado;
      const acoes = i.estado === "pendente"
        ? [botao("Descartar", async () => { if (confirm("Tirar esta nota da fila? Ela não será enviada; a compra continua no ARGOS.")) await FiscalFlow.descartar(i.chave); })]
        : [botao("Tentar de novo", () => FiscalFlow.reenviar(i.chave)), botao("Descartar", () => FiscalFlow.descartar(i.chave))];
      return el("li", {}, linha(`${data(p.purchase_date)} · ${p.merchant || "NFC-e"}`, moeda(p.total_cents || 0)),
        el("div", { class: "meta" }, rotulo + (i.tentativas ? ` · ${i.tentativas} tentativa(s)` : "")), el("div", { class: "cp-ff" }, ...acoes));
    })));
  }
  async function carregarDestinos() {
    if (!FiscalFlow.ativo()) return;
    const atual = FiscalFlow.lerConfig().workspace || "";
    const lista = await FiscalFlow.destinos().catch(() => null);
    const sel = $("ff-destino");
    if (lista === null) {
      // Sem resposta agora (fora da Tailscale, sem rede): mantém o destino escolhido; as notas continuam indo para ele.
      const nome = FiscalFlow.lerConfig().workspaceNome || "Workspace escolhido";
      sel.replaceChildren(el("option", { value: "" }, "Pessoal"), ...(atual ? [el("option", { value: atual }, nome)] : []));
      sel.value = atual;
      return;
    }
    sel.replaceChildren(el("option", { value: "" }, "Pessoal"), ...lista.map(w => el("option", { value: w.id }, w.nome)));
    // Destino que deixou de estar disponível (papel alterado ou acesso revogado) volta a pessoal.
    sel.value = lista.some(w => w.id === atual) ? atual : "";
    if (sel.value !== atual) FiscalFlow.definirDestino("", "");
  }
  async function mostrarOrcamento() {
    if (!FiscalFlow.ativo()) { $("ff-orcamento").textContent = ""; return; }
    const categoria = FiscalFlow.lerConfig().categoria || "Supermercado";
    try {
      const l = await FiscalFlow.orcamento();
      $("ff-orcamento").textContent = !l ? `Sem orçamento de "${categoria}" neste mês no FiscalFlow.`
        : `${l.category}: disponível ${moeda(l.available_cents)} de ${moeda(l.budget_cents)} (realizado ${moeda(l.realized_cents)}, pendente ${moeda(l.pending_cents)}).`;
    } catch { $("ff-orcamento").textContent = "Orçamento indisponível agora."; }
  }
  function telaFiscalFlow() {
    const on = FiscalFlow.ativo();
    $("ff-entrar").hidden = on; $("ff-enviar").hidden = !on; $("ff-sair").hidden = !on; $("ff-categoria-label").hidden = !on;
    $("ff-destino-label").hidden = !on;
    if (on) $("ff-categoria").value = FiscalFlow.lerConfig().categoria || "";
    if (!on) { $("ff-url").value = FiscalFlow.lerConfig().url || FiscalFlow.urlPadrao(); $("ff-email").value = FiscalFlow.lerConfig().email || ""; }
  }
  $("ff-entrar").addEventListener("submit", async e => {
    e.preventDefault();
    const botao = e.currentTarget.querySelector("button");
    botao.disabled = true;
    try {
      await FiscalFlow.entrar($("ff-url").value, $("ff-email").value, $("ff-senha").value);
      $("ff-senha").value = ""; toast("FiscalFlow conectado."); await sincronizar();
    } catch (erro) { estadoFiscalFlow(erro.message); }
    finally { botao.disabled = false; }
  });
  $("ff-enviar").addEventListener("click", () => sincronizar(true));
  $("ff-testar").addEventListener("click", async () => {
    const botao = $("ff-testar");
    botao.disabled = true;
    try { estadoFiscalFlow((await FiscalFlow.testar($("ff-url").value)).msg); } finally { botao.disabled = false; }
  });
  $("ff-destino").addEventListener("change", () => {
    const sel = $("ff-destino");
    FiscalFlow.definirDestino(sel.value, sel.selectedOptions[0]?.textContent || "");
    mostrarOrcamento();
  });
  $("ff-categoria").addEventListener("change", () => { FiscalFlow.definirCategoria($("ff-categoria").value); mostrarOrcamento(); });
  $("ff-sair").addEventListener("click", () => { FiscalFlow.sair(); estadoFiscalFlow("Desconectado. A fila continua guardada no aparelho."); telaFiscalFlow(); });
  window.addEventListener("online", () => sincronizar());
  // Ao voltar para o app (ou ligar a Tailscale e reabrir), tenta de novo sem esperar o próximo intervalo.
  document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - ultimaSync > 30000) sincronizar(); });
  telaFiscalFlow(); sincronizar(); mostrarFila();

  $("cp-parar").addEventListener("click", () => { pararCamera(); status(""); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pararCamera(); });
  window.addEventListener("pagehide", pararCamera);
  return {
    abrir: () => atualizar().catch(() => status("Não foi possível abrir as compras salvas neste aparelho.")),
    sair() { pararCamera(); leitura++; if (!rascunho) { entrada(true); status(""); } },
  };
}
