// Renders the premium ARGOS icon (marca/*.svg) into every Android density,
// the splash screens and the web/app favicons. Usage: node mobile/scripts/gerar_icones.js
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const RAIZ = path.resolve(__dirname, "..");
const RES = path.join(RAIZ, "android/app/src/main/res");
const FONTE = path.join(RAIZ, "www/vendor/fonts/jetbrains-mono-latin-800-normal.woff2");
const icone = fs.readFileSync(path.join(RAIZ, "marca/argos-icone.svg"), "utf8");
const frente = fs.readFileSync(path.join(RAIZ, "marca/argos-icone-foreground.svg"), "utf8");
const fonte64 = fs.readFileSync(FONTE).toString("base64");

const DENS = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const SPLASH = { mdpi: [320, 480], hdpi: [480, 800], xhdpi: [720, 1280], xxhdpi: [960, 1600], xxxhdpi: [1280, 1920] };

function pagina(corpo, w, h, fundo = "transparent") {
  return `<!doctype html><html><head><style>
    @font-face { font-family: "JetBrains Mono"; font-weight: 800; src: url(data:font/woff2;base64,${fonte64}) format("woff2"); }
    html, body { margin: 0; width: ${w}px; height: ${h}px; background: ${fundo}; overflow: hidden; }
    body { display: grid; place-items: center; font-family: "JetBrains Mono", monospace; }
    svg { display: block; }
  </style></head><body>${corpo}</body></html>`;
}
const dim = (svg, w, h) => svg.replace(/width="512" height="512"/, `width="${w}" height="${h}"`);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  async function render(html, w, h, destino, { omitBackground = true, redondo = false } = {}) {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(redondo ? html.replace("</style>", "svg { clip-path: circle(50%); }</style>") : html);
    await page.evaluate(() => document.fonts.ready);
    fs.mkdirSync(path.dirname(destino), { recursive: true });
    await page.screenshot({ path: destino, omitBackground });
    console.log(path.relative(RAIZ, destino), `${w}x${h}`);
  }

  // Brand masters
  for (const s of [192, 512, 1024]) await render(pagina(dim(icone, s, s), s, s), s, s, path.join(RAIZ, `marca/argos-icone-${s}.png`));
  await render(pagina(dim(icone, 192, 192), 192, 192), 192, 192, path.join(RAIZ, "www/img/icone-192.png"));
  await render(pagina(dim(icone, 64, 64), 64, 64), 64, 64, path.join(RAIZ, "www/img/favicon.png"));

  // Launcher icons (legacy + round + adaptive layers)
  const fundoSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108" width="W" height="W">
    <defs><radialGradient id="f" cx="50%" cy="42%" r="70%"><stop offset="0" stop-color="#0d2a17"/>
    <stop offset=".55" stop-color="#05120a"/><stop offset="1" stop-color="#010402"/></radialGradient></defs>
    <rect width="108" height="108" fill="url(#f)"/>
    <g stroke="#33ff77" stroke-opacity=".08" stroke-width=".5"><path d="M0 27H108M0 40.5H108M0 67.5H108M0 81H108M27 0V108M40.5 0V108M67.5 0V108M81 0V108"/></g>
    <circle cx="54" cy="54" r="50" fill="none" stroke="#e6bf55" stroke-opacity=".55" stroke-width="1.2"/></svg>`;
  for (const [d, k] of Object.entries(DENS)) {
    const s = Math.round(48 * k), a = Math.round(108 * k);
    await render(pagina(dim(icone, s, s), s, s), s, s, path.join(RES, `mipmap-${d}/ic_launcher.png`));
    await render(pagina(dim(icone, s, s), s, s), s, s, path.join(RES, `mipmap-${d}/ic_launcher_round.png`), { redondo: true });
    await render(pagina(dim(frente, a, a), a, a), a, a, path.join(RES, `mipmap-${d}/ic_launcher_foreground.png`));
    await render(pagina(fundoSvg.replace(/W/g, a), a, a), a, a, path.join(RES, `mipmap-${d}/ic_launcher_background.png`));
  }

  // Splash screens
  const splash = (w, h) => {
    const s = Math.round(Math.min(w, h) * 0.42);
    return pagina(`<div style="display:grid;justify-items:center;gap:${Math.round(s * 0.08)}px">
      ${dim(icone, s, s)}
      <div style="color:#4f8f63;font-size:${Math.max(10, Math.round(s * 0.075))}px;letter-spacing:.2em">MONITORAMENTO ATIVO</div>
      <div style="color:#a87a1c;font-size:${Math.max(9, Math.round(s * 0.06))}px;letter-spacing:.08em;margin-top:${Math.round(s * 0.25)}px">VSA SOLUÇÕES EM TECNOLOGIA</div>
    </div>`, w, h, "#030805");
  };
  for (const [d, [w, h]] of Object.entries(SPLASH)) {
    await render(splash(w, h), w, h, path.join(RES, `drawable-port-${d}/splash.png`), { omitBackground: false });
    await render(splash(h, w), h, w, path.join(RES, `drawable-land-${d}/splash.png`), { omitBackground: false });
  }
  await render(splash(480, 320), 480, 320, path.join(RES, "drawable/splash.png"), { omitBackground: false });
  await browser.close();
})();
