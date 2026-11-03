#!/usr/bin/env bash
# ARGOS — backup consistente dos bancos SQLite (usuários/pagamentos e indicadores).
# Mantém 14 dias em /var/backups/argos. Agendado pelo instalar_vps.sh (cron 03:17).
set -euo pipefail
cd "$(dirname "$0")/.."
DESTINO=/var/backups/argos
mkdir -p "$DESTINO"
DATA=$(date +%F-%H%M)
docker compose exec -T argos python - <<'PY'
import sqlite3
for nome in ("radar", "indicadores"):
    origem = sqlite3.connect(f"/data/{nome}.db")
    copia = sqlite3.connect(f"/data/backup-{nome}.db")
    origem.backup(copia)  # online backup: safe while the app is running
    copia.close(); origem.close()
PY
for nome in radar indicadores; do
  docker compose cp "argos:/data/backup-$nome.db" "$DESTINO/$nome-$DATA.db"
  gzip -f "$DESTINO/$nome-$DATA.db"
done
chmod 600 "$DESTINO"/*.gz
find "$DESTINO" -name '*.db.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: $DESTINO/*-$DATA.db.gz"
