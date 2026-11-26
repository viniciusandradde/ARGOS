// Backup das compras: baixar, apagar os dados do aparelho e restaurar. Nota fictícia; nada sai da máquina.
const { test, expect } = require("@playwright/test");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const xml = readFileSync(join(__dirname, "fixtures", "nota.xml"), "utf8");

test("baixar backup, apagar e restaurar devolve estoque e histórico", async ({ page, context }) => {
  await context.route("**/*", route => (new URL(route.request().url()).hostname === "127.0.0.1" ? route.continue() : route.abort()));
  await page.goto("/#compras");
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-xml").setInputFiles({ name: "nota.xml", mimeType: "text/xml", buffer: Buffer.from(xml) });
  await page.getByRole("button", { name: "Registrar compra e atualizar estoque" }).click();
  await expect(page.locator("#cp-historico")).toContainText("R$ 57,00");

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Baixar backup" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^argos-compras-\d{4}-\d{2}-\d{2}\.json$/);
  const conteudo = readFileSync(await download.path(), "utf8");
  const backup = JSON.parse(conteudo);
  expect(backup).toMatchObject({ formato: "argos-compras", versao: 1 });
  expect(backup.notas).toHaveLength(1);

  await page.evaluate(() => new Promise(resolve => { const r = indexedDB.deleteDatabase("argos-compras"); r.onsuccess = r.onerror = r.onblocked = resolve; }));
  await page.reload();
  await expect(page.locator("#cp-historico")).toContainText("Nenhuma nota registrada");

  page.once("dialog", d => d.accept());
  await page.locator("#cp-importar").setInputFiles({ name: "backup.json", mimeType: "application/json", buffer: Buffer.from(conteudo) });
  await expect(page.locator("#cp-backup-estado")).toContainText("Backup restaurado: 1 nota(s)");
  await expect(page.locator("#cp-historico")).toContainText("R$ 57,00");

  await page.locator("#cp-importar").setInputFiles({ name: "x.json", mimeType: "application/json", buffer: Buffer.from('{"formato":"outro"}') });
  await expect(page.locator("#cp-backup-estado")).toContainText("não é um backup de compras");
});
