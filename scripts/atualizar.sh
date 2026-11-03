#!/usr/bin/env bash
# ARGOS — atualiza para a versão mais recente do branch atual e reinicia.
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/backup.sh || echo "Aviso: backup falhou, continuando."
git pull --ff-only
PERFIS=()
docker compose ps --services 2>/dev/null | grep -q evolution-api && PERFIS=(--profile whatsapp)
docker compose "${PERFIS[@]}" up -d --build
docker image prune -f >/dev/null
sleep 10
bash scripts/verificar.sh
