#!/usr/bin/env bash
# ARGOS — verificação de saúde da instalação. Sai com código != 0 se algo essencial falhar.
set -uo pipefail
cd "$(dirname "$0")/.."
falhas=0
ok() { printf '  \033[32m[OK]\033[0m  %s\n' "$*"; }
ruim() { printf '  \033[31m[FALHA]\033[0m %s\n' "$*"; falhas=$((falhas + 1)); }
aviso() { printf '  \033[33m[AVISO]\033[0m %s\n' "$*"; }

echo "Containers:"
docker compose ps --format '  {{.Service}}: {{.State}} {{.Health}}' 2>/dev/null || ruim "docker compose indisponível"

echo "Serviço:"
if docker compose exec -T argos python -c "import urllib.request; urllib.request.urlopen('http://localhost:8061/health')" 2>/dev/null; then
  ok "/health respondendo"
else
  ruim "/health não responde (docker compose logs argos)"
fi

BASE=$(grep -E '^MCP_BRASIL_BASE_URL=' .env 2>/dev/null | cut -d= -f2-)
if [[ -n "$BASE" ]]; then
  codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/conta")
  [[ "$codigo" == "200" ]] && ok "Portal público $BASE/conta (HTTP 200)" || ruim "Portal $BASE/conta retornou HTTP $codigo (DNS/HTTPS/Caddy?)"
  planos=$(curl -s --max-time 15 "$BASE/api/planos")
  [[ "$planos" == *'"planos"'* ]] && ok "API de planos" || ruim "API de planos sem resposta"
  [[ "$planos" == *'"pagamentos_ativos":true'* ]] && ok "Mercado Pago configurado" || aviso "Mercado Pago ainda não configurado (MERCADOPAGO_ACCESS_TOKEN)"
fi

echo "Coletor (última execução de cada etapa):"
docker compose exec -T argos python - <<'PY' 2>/dev/null || aviso "Coletor ainda sem dados (aguarde ~1 min após subir)"
import os, sqlite3
db = sqlite3.connect(os.environ.get("RADAR_INDICADORES_DB", "/data/indicadores.db"))
linhas = db.execute(
    "SELECT etapa, ok, quando, mensagem FROM coletas WHERE id IN "
    "(SELECT MAX(id) FROM coletas GROUP BY etapa) ORDER BY etapa"
).fetchall()
if not linhas:
    raise SystemExit(1)
for etapa, sucesso, quando, msg in linhas:
    print(f"  {'[OK]   ' if sucesso else '[FALHA]'} {etapa:<13} {quando[:19]}  {msg[:60]}")
PY

echo "Memória:"
docker stats --no-stream --format '  {{.Name}}: {{.MemUsage}}' 2>/dev/null

[[ $falhas -eq 0 ]] && echo "Tudo certo." || echo "$falhas verificação(ões) falharam."
exit $falhas
