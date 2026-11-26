#!/bin/sh
# Gera js/config.js a partir do ambiente do container (executado pelo entrypoint do nginx antes de subir).
# FISCALFLOW_URL: endereço HTTPS do FiscalFlow sugerido no login. APK_URL: link de download do app.
set -eu
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/</\\u003c/g'; }
cat > /usr/share/nginx/html/js/config.js <<CFG
// Gerado pelo container ao iniciar (mobile/web/40-argos-config.sh). Público: nunca coloque segredo aqui.
window.ARGOS_CONFIG = { fiscalflowUrl: "$(esc "${FISCALFLOW_URL:-}")", sefazProxy: "/sefaz-ms", apkUrl: "$(esc "${APK_URL:-/downloads/argos-ultima.apk}")" };
CFG
