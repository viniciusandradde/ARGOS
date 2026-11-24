const { test, expect } = require("@playwright/test");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const arquivo = nome => join(__dirname, "fixtures", nome);
const xml = readFileSync(arquivo("nota.xml"), "utf8");
const html = readFileSync(arquivo("nota.html"), "utf8");
const qr = readFileSync(arquivo("qr-ms.png")).toString("base64");
const chave = "50261100000000000100650010000000011000000000";
const link = "https://www.dfe.ms.gov.br/nfce/qrcode?p=" + chave + "|3|1";

test.beforeEach(async ({ context, page }) => {
  await context.route("**/*", route => {
    if (new URL(route.request().url()).hostname === "127.0.0.1") return route.continue();
    return route.abort();
  });
  await page.goto("/#compras");
  await expect(page.locator("#cp-faltas")).toContainText("Cadastre");
});

async function ajustar(page, nome, un, acao, qtd) {
  await page.locator("#cp-nome").fill(nome);
  await page.locator("#cp-un").fill(un);
  await page.locator("#cp-acao").selectOption(acao);
  await page.locator("#cp-qtd").fill(qtd);
  await page.getByRole("button", { name: "Salvar quantidade" }).click();
  await expect(page.locator("#cp-qtd")).toHaveValue("");
}

test("QR pela câmera, conferência, registro, consumo e histórico após reabrir", async ({ page, context }) => {
  await context.route("https://www.dfe.ms.gov.br/**", r => r.fulfill({ contentType: "text/html", body: html }));
  await ajustar(page, "Arroz 5 kg", "UN", "meta", "3");
  await ajustar(page, "Arroz 5 kg", "UN", "avulso", "2");
  await ajustar(page, "Feijão", "KG", "avulso", "1");
  await page.evaluate(base64 => {
    navigator.mediaDevices.getUserMedia = async () => {
      const img = new Image();
      img.src = "data:image/png;base64," + base64;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = img.width; canvas.height = img.height;
      const stream = canvas.captureStream(10);
      canvas.getContext("2d").drawImage(img, 0, 0);
      return stream;
    };
  }, qr);
  await page.getByRole("button", { name: "Escanear QR Code da nota" }).click();
  const previa = page.locator("#cp-revisao");
  await expect(previa).toContainText("Mercado de demonstração");
  await expect(previa).toContainText("2 itens");
  await expect(previa).toContainText("57,00");
  await previa.getByLabel("Vincular ARROZ T1 5KG").selectOption({ label: "Arroz 5 kg" });
  await expect(page.locator("#cp-historico")).toContainText("Nenhuma nota");
  await page.getByRole("button", { name: "Registrar compra e atualizar estoque" }).click();
  await expect(page.locator("#cp-faltas")).toContainText("Arroz 5 kg1 UN");
  await expect(page.locator("#cp-catalogo")).toContainText("Banana prata1,25 KG");
  await page.reload();
  await page.locator("#cp-historico summary").click();
  await expect(page.locator("#cp-historico")).toContainText("Extra 1,25");
  await expect(page.locator("#cp-historico")).toContainText("Falta 1");
  await ajustar(page, "Arroz 5 kg", "UN", "consumo", "0,5");
  await expect(page.locator("#cp-faltas")).toContainText("Arroz 5 kg1,5 UN");
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-xml").setInputFiles(arquivo("nota.xml"));
  await expect(page.locator("#cp-status")).toContainText("já foi registrada");
  await expect(page.locator("#cp-historico summary")).toHaveCount(1);
});

test("uma nota inválida ou parcial não modifica o estoque", async ({ page, context }) => {
  await context.route("https://www.dfe.ms.gov.br/**", r => r.fulfill({
    contentType: "text/html", body: html.replace("itens:</label><span>2", "itens:</label><span>3"),
  }));
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-link").fill(link);
  await page.getByRole("button", { name: "Consultar nota" }).click();
  await expect(page.locator("#cp-status")).toContainText("quantidade de itens");
  await page.locator("#cp-xml").setInputFiles({ name: "sem-itens.xml", mimeType: "text/xml", buffer: Buffer.from("<doc/>") });
  await expect(page.locator("#cp-status")).toContainText("XML de uma NFC-e");
  await page.locator("#cp-xml").setInputFiles(arquivo("nota.xml"));
  await expect(page.locator("#cp-previa")).toContainText("2 itens");
  await page.getByRole("button", { name: "Descartar leitura" }).click();
  await expect(page.locator("#cp-historico")).toContainText("Nenhuma nota");
});

test("duas confirmações simultâneas geram somente uma entrada de estoque", async ({ page, context }) => {
  const outra = await context.newPage();
  await outra.goto("/#compras");
  await Promise.all([page, outra].map(p => p.evaluate(async x => {
    const n = Nfce.xml(x);
    try { await Compras.alterar(c => Compras.registrar(c, n, [])); }
    catch (e) { if (!e.message.includes("já foi registrada")) throw e; }
  }, xml)));
  const estado = await page.evaluate(() => Compras.ler());
  expect(estado.notas).toHaveLength(1);
  expect(Object.values(estado.cat.produtos).map(p => p.saldo).sort()).toEqual([1.25, 2]);
});
