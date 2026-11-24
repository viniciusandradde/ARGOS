const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/compras",
  use: {
    baseURL: "http://127.0.0.1:8341",
    viewport: { width: 412, height: 840 },
    launchOptions: { executablePath: process.env.CHROMIUM_PATH },
  },
  webServer: {
    command: "python3 -m http.server 8341 --bind 127.0.0.1 --directory www",
    url: "http://127.0.0.1:8341",
    reuseExistingServer: false,
  },
});
