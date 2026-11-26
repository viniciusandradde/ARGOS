// Fila opcional do FiscalFlow no navegador, com o servidor simulado por page.route.
// Nenhuma chamada sai da máquina; nota e conta são fictícias.
const { test, expect } = require("@playwright/test");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const BASE = "https://fiscalflow.exemplo.invalid";
const xml = readFileSync(join(__dirname, "fixtures", "nota.xml"), "utf8");
const comPagamento = xml.replace("</infNFe>", "<pag><detPag><tPag>17</tPag><vPag>57.00</vPag></detPag></pag></infNFe>");

// Servidor simulado: responde conforme `estado.resposta` e guarda os corpos recebidos.
async function servidor(context, estado) {
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1") return route.continue();
    if (url.origin !== BASE || estado.offline) return route.abort();
    if (url.pathname === "/api/health") return route.fulfill({ json: { code: 200 } });
    if (url.pathname === "/api/collections/users/auth-refresh") return route.fulfill({ json: { token: "token-renovado" } });
    if (url.pathname === "/api/collections/users/auth-with-password") {
      return route.fulfill({ json: { token: "token-ficticio", record: { id: "u1" } } });
    }
    if (url.pathname === "/api/fiscalflow/workspaces") {
      return route.fulfill({ json: { items: [
        { id: "wsfamilia000001", name: "Família Fictícia", kind: "family", role: "editor" },
        { id: "wsleitura000001", name: "Só leitura", kind: "family", role: "viewer" },
      ] } });
    }
    if (url.pathname === "/api/integrations/argos/v1/budget") {
      (estado.orcamentos ||= []).push(url.search);
      return route.fulfill({ json: { categories: [{ category: "Supermercado", budget_cents: 100000, realized_cents: 0, pending_cents: 0, available_cents: 100000 }] } });
    }
    if (url.pathname === "/api/integrations/argos/v1/purchases") {
      estado.recebidos.push({ auth: route.request().headers().authorization, corpo: route.request().postDataJSON() });
      return route.fulfill({ status: estado.resposta, json: {} });
    }
    return route.fulfill({ status: 404, json: {} });
  });
}

async function conectarEImportar(page, conteudo) {
  await page.goto("/#compras");
  await page.locator("#ff-url").fill(BASE);
  await page.locator("#ff-email").fill("pessoa@exemplo.invalid");
  await page.locator("#ff-senha").fill("senha-ficticia");
  await page.locator("#ff-entrar button[type=submit]").click();
  await expect(page.locator("#ff-estado")).toContainText("Conectado");
  await expect(page.locator("#ff-orcamento")).toContainText("disponível R$ 1.000,00");
  expect(await page.evaluate(() => localStorage.getItem("argos-fiscalflow"))).not.toContain("senha-ficticia");
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-xml").setInputFiles({ name: "nota.xml", mimeType: "text/xml", buffer: Buffer.from(conteudo) });
  await page.getByRole("button", { name: "Registrar compra e atualizar estoque" }).click();
}

const fila = page => page.evaluate(() => new Promise((resolve, reject) => {
  const req = indexedDB.open("argos-fiscalflow");
  req.onsuccess = () => { const g = req.result.transaction("fila").objectStore("fila").getAll(); g.onsuccess = () => resolve(g.result); g.onerror = () => reject(g.error); };
  req.onerror = () => reject(req.error);
}));

test("envia a nota com payload mínimo e forma de pagamento; a fila esvazia após 2xx", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, comPagamento);
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  expect(estado.recebidos).toHaveLength(1);
  const { auth, corpo } = estado.recebidos[0];
  expect(auth).toBe("token-ficticio");
  expect(corpo).toMatchObject({ schema_version: 1, fiscal_key: "50261100000000000100650010000000011000000000", total_cents: 5700,
    currency: "BRL", revision: 1, payment_methods: [{ type: "pix", amount_cents: 5700 }] });
  for (const campo of ["cpf", "xml", "qr_url", "pan"]) expect(corpo).not.toHaveProperty(campo);
  expect(await fila(page)).toEqual([]);
});

test("falha temporária mantém a nota na fila; envio manual reenvia sem esperar o backoff", async ({ page, context }) => {
  const estado = { resposta: 503, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, xml);
  await expect(page.locator("#ff-estado")).toContainText("1 aguardando reenvio");
  const [item] = await fila(page);
  expect(item).toMatchObject({ estado: "pendente", tentativas: 1 });
  estado.resposta = 200;
  await page.getByRole("button", { name: "Enviar pendentes agora" }).click();
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  expect(estado.recebidos).toHaveLength(2);
  expect(await fila(page)).toEqual([]);
});

test("conflito fica na fila para revisão; sessão expirada desconecta sem perder a fila", async ({ page, context }) => {
  const estado = { resposta: 409, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, xml);
  await expect(page.locator("#ff-estado")).toContainText("1 em conflito");
  expect((await fila(page))[0].estado).toBe("conflito");

  // Nova nota pendente + sessão expirada: a fila é preservada e o app pede nova conexão.
  await page.evaluate(() => new Promise(resolve => {
    const req = indexedDB.open("argos-fiscalflow");
    req.onsuccess = () => {
      const tx = req.result.transaction("fila", "readwrite");
      tx.objectStore("fila").put({ chave: "x".repeat(44), payload: { schema_version: 1 }, estado: "pendente", tentativas: 0, proxima: 0 });
      tx.oncomplete = resolve;
    };
  }));
  estado.resposta = 401;
  await page.getByRole("button", { name: "Enviar pendentes agora" }).click();
  await expect(page.locator("#ff-estado")).toContainText("sessão expirada");
  await expect(page.locator("#ff-entrar")).toBeVisible();
  expect((await fila(page)).map(i => i.estado).sort()).toEqual(["conflito", "pendente"]);
});

test("destino da nota: só workspaces com escrita; nota e orçamento seguem o destino escolhido", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await page.goto("/#compras");
  await page.locator("#ff-url").fill(BASE);
  await page.locator("#ff-email").fill("pessoa@exemplo.invalid");
  await page.locator("#ff-senha").fill("senha-ficticia");
  await page.locator("#ff-entrar button[type=submit]").click();
  await expect(page.locator("#ff-destino option")).toHaveText(["Pessoal", "Família Fictícia"]);
  await page.locator("#ff-destino").selectOption("wsfamilia000001");
  await expect.poll(() => estado.orcamentos.at(-1)).toContain("workspace=wsfamilia000001");
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-xml").setInputFiles({ name: "nota.xml", mimeType: "text/xml", buffer: Buffer.from(xml) });
  await page.getByRole("button", { name: "Registrar compra e atualizar estoque" }).click();
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  expect(estado.recebidos[0].corpo.workspace_id).toBe("wsfamilia000001");
  await page.reload();
  await expect(page.locator("#ff-destino")).toHaveValue("wsfamilia000001");
});

async function entrar(page) {
  await page.locator("#ff-senha").fill("senha-ficticia");
  await page.locator("#ff-entrar button[type=submit]").click();
}
async function importar(page, conteudo = xml) {
  await page.locator("#cp-alternativas summary").click();
  await page.locator("#cp-xml").setInputFiles({ name: "nota.xml", mimeType: "text/xml", buffer: Buffer.from(conteudo) });
  await page.getByRole("button", { name: "Registrar compra e atualizar estoque" }).click();
}

test("nota confirmada sem sessão espera na fila e sai depois do login", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, xml);
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  await page.getByRole("button", { name: "Desconectar" }).click();
  // Segunda nota (outra chave) registrada desconectada: entra na fila mesmo assim.
  const outra = xml.split("50261100000000000100650010000000011000000000").join("50261100000000000100650010000000021000000007");
  await importar(page, outra);
  await expect(page.locator("#ff-estado")).toContainText("entre no FiscalFlow para enviar");
  await expect(page.locator("#ff-fila")).toContainText("aguardando envio");
  expect((await fila(page)).map(i => i.estado)).toEqual(["pendente"]);
  await entrar(page);
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  expect(estado.recebidos).toHaveLength(2);
  expect(await fila(page)).toEqual([]);
});

test("destino mantido quando o FiscalFlow não responde (fora da Tailscale)", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await page.goto("/#compras");
  await page.locator("#ff-url").fill(BASE);
  await page.locator("#ff-email").fill("pessoa@exemplo.invalid");
  await entrar(page);
  await page.locator("#ff-destino").selectOption("wsfamilia000001");
  estado.offline = true;
  await page.reload();
  await expect(page.locator("#ff-destino")).toHaveValue("wsfamilia000001");
  await expect(page.locator("#ff-destino option:checked")).toHaveText("Família Fictícia");
  await importar(page);
  await expect(page.locator("#ff-estado")).toContainText("1 aguardando reenvio");
  expect((await fila(page))[0].payload.workspace_id).toBe("wsfamilia000001");
});

test("fila visível: conflito com Tentar de novo e Descartar", async ({ page, context }) => {
  const estado = { resposta: 409, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, xml);
  await expect(page.locator("#ff-fila")).toContainText("já existe no FiscalFlow");
  estado.resposta = 200;
  await page.locator("#ff-fila").getByRole("button", { name: "Tentar de novo" }).click();
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  await expect(page.locator("#ff-fila")).toBeEmpty();
});

test("cancelar no FiscalFlow pelo histórico envia nova revisão com status cancelled", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await conectarEImportar(page, xml);
  await expect(page.locator("#ff-estado")).toContainText("1 enviada(s)");
  await page.locator("#cp-historico details summary").first().click();
  await expect(page.locator("#cp-historico")).toContainText("Enviada ao FiscalFlow");
  page.once("dialog", d => d.accept());
  await page.locator("#cp-historico").getByRole("button", { name: "Cancelar no FiscalFlow" }).click();
  await expect.poll(() => estado.recebidos.length).toBe(2);
  expect(estado.recebidos[1].corpo).toMatchObject({ fiscal_key: "50261100000000000100650010000000011000000000", revision: 2, status: "cancelled" });
  await page.locator("#cp-historico details summary").first().click();
  await expect(page.locator("#cp-historico")).toContainText("Cancelada no FiscalFlow");
});

test("testar conexão antes de entrar", async ({ page, context }) => {
  const estado = { resposta: 201, recebidos: [] };
  await servidor(context, estado);
  await page.goto("/#compras");
  await page.locator("#ff-url").fill(BASE);
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.locator("#ff-estado")).toContainText("O FiscalFlow respondeu");
  estado.offline = true;
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.locator("#ff-estado")).toContainText("Tailscale");
});
