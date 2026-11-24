// Leitura local da NFC-e. O QR identifica a consulta, os produtos vêm do documento.
"use strict";

const Nfce = (() => {
  function chaveFiscal(valor) {
    const chave = (valor || "").replace(/\s/g, "");
    if (!/^\d{44}$/.test(chave) || chave.slice(20, 22) !== "65") {
      throw new Error("Confira a chave de 44 dígitos de uma NFC-e (modelo 65).");
    }
    let soma = 0;
    for (let i = 42; i >= 0; i--) soma += Number(chave[i]) * (2 + (42 - i) % 8);
    if ((11 - soma % 11) % 11 % 10 !== Number(chave[43])) {
      throw new Error("O dígito verificador da chave da NFC-e é inválido.");
    }
    return chave;
  }

  function consulta(valor) {
    let url;
    try { url = new URL(valor.trim()); } catch { throw new Error("Cole o link completo do QR Code da NFC-e."); }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port ||
        !["www.dfe.ms.gov.br", "dfe.ms.gov.br"].includes(url.hostname) ||
        !/^\/nfce\/qrcode\/?$/i.test(url.pathname)) {
      throw new Error("A leitura por link está disponível para NFC-e de MS. Para outra UF, importe o XML.");
    }
    const p = url.searchParams.get("p")?.split("|");
    const chave = chaveFiscal(p ? p[0] : url.searchParams.get("chNFe"));
    if (!chave.startsWith("50") || (p ? p[2] : url.searchParams.get("tpAmb")) !== "1") {
      throw new Error("Use um QR Code de NFC-e de produção emitida em MS.");
    }
    // The printed path without its final slash redirects to HTTP on the MS portal.
    // Keep the signed query intact, including plus signs and already escaped characters.
    const destino = "https://www.dfe.ms.gov.br/nfce/qrcode/" + url.search.replace(/\|/g, "%7C");
    return { url: destino, chave };
  }

  function texto(no, seletor) {
    return no.querySelector(seletor)?.textContent.trim() || "";
  }

  function decimal(valor, formatoBR = false) {
    let v = valor.trim();
    if (formatoBR) v = v.replace(/\./g, "").replace(",", ".");
    if (!/^\d+(\.\d+)?$/.test(v) || !Number.isFinite(Number(v))) {
      throw new Error("Há um valor incompleto ou inválido na nota.");
    }
    return Number(v);
  }

  function linha(nome, codigo, unidade, qtd, preco, total, br) {
    const quantidade = decimal(qtd, br);
    if (!nome || !unidade || quantidade <= 0 || quantidade !== Number(quantidade.toFixed(4))) {
      throw new Error("Há um produto sem descrição, unidade ou quantidade válida. Confira o XML da nota.");
    }
    return { nome, codigo, unidade: unidade.trim().toUpperCase(), quantidade,
      preco: decimal(preco, br), total: Math.round(decimal(total, br) * 100) };
  }

  function xml(conteudo) {
    const doc = new DOMParser().parseFromString(conteudo, "application/xml");
    const ns = "http://www.portalfiscal.inf.br/nfe";
    const infos = doc.getElementsByTagNameNS(ns, "infNFe");
    if (doc.querySelector("parsererror") || infos.length !== 1) throw new Error("Escolha o XML de uma NFC-e.");
    const info = infos[0];
    // localName also works with explicitly prefixed official XML.
    const filho = (no, nome) => Array.from(no?.children || []).find(e => e.localName === nome && e.namespaceURI === ns);
    const campo = (no, nome) => filho(no, nome)?.textContent.trim() || "";
    const ide = filho(info, "ide");
    const chave = chaveFiscal((info.getAttribute("Id") || "").replace(/^NFe/, ""));
    if (campo(ide, "mod") !== "65" || campo(ide, "tpAmb") !== "1") throw new Error("Importe uma NFC-e de produção.");
    const protocolo = doc.getElementsByTagNameNS(ns, "infProt")[0];
    if (protocolo && (!["100", "150"].includes(campo(protocolo, "cStat")) || campo(protocolo, "chNFe") !== chave)) {
      throw new Error("O protocolo não confirma a autorização desta NFC-e.");
    }
    const produtos = Array.from(info.children).filter(e => e.localName === "det" && e.namespaceURI === ns).map(det => {
      const p = filho(det, "prod");
      return linha(campo(p, "xProd"), campo(p, "cProd"), campo(p, "uCom"), campo(p, "qCom"),
        campo(p, "vUnCom"), campo(p, "vProd"), false);
    });
    if (!produtos.length) throw new Error("O XML não contém produtos.");
    const emit = filho(info, "emit");
    const data = campo(ide, "dhEmi") || campo(ide, "dEmi");
    return { chave, mercado: campo(emit, "xFant") || campo(emit, "xNome"), data: data.slice(0, 10),
      total: Math.round(decimal(campo(filho(filho(info, "total"), "ICMSTot"), "vNF")) * 100), produtos };
  }

  function html(conteudo, esperada) {
    const template = document.createElement("template");
    template.innerHTML = conteudo;
    const doc = template.content;
    const linhas = Array.from(doc.querySelectorAll("#tabResult tr")).filter(tr => tr.querySelector("td"));
    if (!linhas.length) throw new Error("A SEFAZ não retornou os itens. Tente novamente ou importe o XML da NFC-e.");
    const chave = chaveFiscal(texto(doc, ".chave"));
    if (chave !== esperada) throw new Error("A chave da consulta é diferente da chave do QR Code.");
    const campo = (tr, sel) => texto(tr, sel).replace(/^[^:]*:/, "").trim();
    const produtos = linhas.map(tr => linha(texto(tr, ".txtTit"), campo(tr, ".RCod").replace(/\)\s*$/, "").trim(),
      campo(tr, ".RUN"), campo(tr, ".Rqtd"), campo(tr, ".RvlUnit"), texto(tr, ".valor"), true));
    const contagem = Array.from(doc.querySelectorAll("#totalNota label")).find(e => /total de itens/i.test(e.textContent));
    if (Number(contagem?.nextElementSibling?.textContent.trim()) !== produtos.length) {
      throw new Error("A quantidade de itens da consulta não confere. Importe o XML da nota.");
    }
    const data = /Emissão:\s*(\d{2})\/(\d{2})\/(\d{4})/i.exec(doc.textContent);
    const total = texto(doc, "#totalNota .txtMax");
    return { chave, mercado: texto(doc, "#u20"), data: data ? [data[3], data[2], data[1]].join("-") : "",
      total: Math.round(decimal(total, true) * 100), produtos };
  }

  async function buscar(valor) {
    const { url, chave } = consulta(valor);
    let corpo, status;
    const cap = window.Capacitor;
    try {
      if (cap?.isNativePlatform()) {
        const r = await cap.Plugins.CapacitorHttp.get({ url, responseType: "text", connectTimeout: 12000, readTimeout: 18000 });
        status = r.status;
        corpo = r.data;
      } else {
        const r = await fetch(url, { credentials: "omit", referrerPolicy: "no-referrer", signal: AbortSignal.timeout(20000) });
        status = r.status;
        corpo = await r.text();
      }
    } catch {
      throw new Error(cap?.isNativePlatform()
        ? "Não foi possível conectar à SEFAZ-MS. Confira sua conexão e toque em Consultar nota para tentar novamente."
        : "A consulta à SEFAZ-MS falhou no navegador. Tente no app Android ou importe o XML.");
    }
    if (status !== 200) {
      throw new Error("A SEFAZ-MS respondeu com HTTP " + status + ". Tente consultar a nota novamente ou importe o XML.");
    }
    return html(corpo, chave);
  }
  return { chaveFiscal, consulta, xml, html, buscar };
})();
if (typeof module !== "undefined") module.exports = Nfce;
