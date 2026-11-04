#!/usr/bin/env bash
# ARGOS — instalação em VPS Ubuntu/Debian (idempotente: pode rodar de novo sem estragar nada).
#
# Uso (na pasta do repositório, como root):
#   bash scripts/instalar_vps.sh --dominio argos.seudominio.com.br --email voce@seudominio.com.br
#   bash scripts/instalar_vps.sh --email voce@exemplo.com          # sem domínio: HTTP pelo IP
#   bash scripts/instalar_vps.sh --tailscale --email voce@exemplo.com  # servidor compartilhado
# Opções: --whatsapp (sobe a Evolution API)  --sem-firewall  --sem-swap
#         --tailscale: publica só no IP da VPN, sem mexer no firewall (porta padrão 8062)
#         --porta N:   porta HTTP usada com --tailscale
set -euo pipefail

DOMINIO=""; EMAIL=""; WHATSAPP=0; FIREWALL=1; SWAP=1; TAILSCALE=0; PORTA=8062; PORTA_HTTPS=8443
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dominio) DOMINIO="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --whatsapp) WHATSAPP=1; shift ;;
    --sem-firewall) FIREWALL=0; shift ;;
    --sem-swap) SWAP=0; shift ;;
    --tailscale) TAILSCALE=1; FIREWALL=0; shift ;;
    --porta) PORTA="$2"; shift 2 ;;
    *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "Rode como root (sudo -i)." >&2; exit 1; }
[[ -f docker-compose.yml ]] || { echo "Rode dentro da pasta do repositório." >&2; exit 1; }

# Stop before touching the host: a busy port used to abort the install halfway through.
conferir_porta() {
  local porta="$1"
  ss -tlnH "sport = :${porta}" | grep -q . || return 0
  echo "Porta ${porta} já está em uso nesta máquina:" >&2
  ss -tlnH "sport = :${porta}" >&2
  echo "Use --tailscale (e --porta N) ou libere a porta. Nada foi alterado." >&2
  exit 1
}

if [[ -n "$DOMINIO" && $TAILSCALE -eq 1 ]]; then
  echo "--dominio e --tailscale não combinam: o certificado exige as portas 80/443 públicas." >&2
  exit 2
fi

BIND_IP=""
if [[ $TAILSCALE -eq 1 ]]; then
  BIND_IP=$(tailscale ip -4 2>/dev/null | head -n 1 || true)
  [[ -n "$BIND_IP" ]] || { echo "Tailscale sem IP. Rode: tailscale up" >&2; exit 1; }
fi

# A running caddy from a previous install legitimately holds its own ports.
if [[ -z "$(docker compose ps -q --status running caddy 2>/dev/null)" ]]; then
  if [[ $TAILSCALE -eq 1 ]]; then
    conferir_porta "$PORTA"
    conferir_porta "$PORTA_HTTPS"
  else
    conferir_porta 80
    conferir_porta 443
  fi
fi

aleatorio() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-40}"; }

# Define KEY=VALUE no .env sem sobrescrever um valor já preenchido.
definir_env() {
  local chave="$1" valor="$2"
  if grep -qE "^${chave}=.+" .env; then return 0; fi
  if grep -qE "^#? ?${chave}=" .env; then
    # only the first commented occurrence (the example file may mention a key twice)
    sed -i -E "0,/^#? ?${chave}=.*/s||${chave}=${valor}|" .env
  else
    printf '%s=%s\n' "$chave" "$valor" >> .env
  fi
}

# Same as definir_env, but replaces a value that is already filled in.
trocar_env() {
  sed -i -E "/^$1=/d" .env
  definir_env "$1" "$2"
}

log "Pacotes básicos"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  log "Instalando Docker"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null

if [[ $SWAP -eq 1 ]] && ! swapon --show | grep -q . && [[ $(free -m | awk '/Mem:/{print $2}') -lt 2048 ]]; then
  log "Criando swap de 1 GB (ajuda no build em VPS de 1 GB)"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if [[ $FIREWALL -eq 1 ]]; then
  log "Firewall: liberando só SSH, 80 e 443"
  ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
fi

log "Configurando .env"
[[ -f .env ]] || cp .env.example .env
chmod 600 .env
IP=$(curl -fsS -4 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
definir_env MCP_BRASIL_AUTH_MODE radar
if [[ $TAILSCALE -eq 1 ]]; then
  trocar_env ARGOS_DOMINIO ":80"
  trocar_env MCP_BRASIL_BASE_URL "http://$BIND_IP:$PORTA"
  trocar_env ARGOS_BIND_IP "$BIND_IP"
  trocar_env ARGOS_PORTA_HTTP "$PORTA"
  trocar_env ARGOS_PORTA_HTTPS "$PORTA_HTTPS"
  definir_env EVOLUTION_PORTA 18081
  definir_env METABASE_PORTA 13000
elif [[ -n "$DOMINIO" ]]; then
  definir_env ARGOS_DOMINIO "$DOMINIO"
  definir_env MCP_BRASIL_BASE_URL "https://$DOMINIO"
else
  definir_env ARGOS_DOMINIO ":80"
  definir_env MCP_BRASIL_BASE_URL "http://$IP"
fi
definir_env RADAR_SECRET_KEY "$(aleatorio 48)"
definir_env EVOLUTION_API_KEY "$(aleatorio 40)"
definir_env EVOLUTION_DB_SENHA "$(aleatorio 32)"
definir_env EVOLUTION_API_URL "http://evolution-api:8080"

log "Subindo containers (o primeiro build leva alguns minutos)"
PERFIS=()
[[ $WHATSAPP -eq 1 ]] && PERFIS=(--profile whatsapp)
docker compose "${PERFIS[@]}" up -d --build

log "Aguardando o ARGOS ficar saudável"
for _ in $(seq 1 60); do
  if docker compose exec -T argos python -c "import urllib.request; urllib.request.urlopen('http://localhost:8061/health')" 2>/dev/null; then
    ok=1; break
  fi
  sleep 3
done
[[ "${ok:-0}" -eq 1 ]] || { echo "ARGOS não respondeu. Veja: docker compose logs argos" >&2; exit 1; }

if [[ -n "$EMAIL" ]]; then
  log "Criando administrador $EMAIL"
  SENHA="$(aleatorio 20)"
  if docker compose exec -T argos python -m mcp_brasil.radar criar-admin --email "$EMAIL" --senha "$SENHA" 2>/dev/null; then
    umask 077
    printf 'ARGOS — administrador\nURL: %s/conta\nE-mail: %s\nSenha: %s\n' \
      "$(grep -E '^MCP_BRASIL_BASE_URL=' .env | cut -d= -f2-)" "$EMAIL" "$SENHA" > /root/argos-credenciais.txt
    echo "Credenciais salvas em /root/argos-credenciais.txt (troque a senha no primeiro acesso)."
  else
    echo "Administrador já existe (mantido)."
  fi
fi

log "Backup diário (03:17) em /var/backups/argos"
cat > /etc/cron.d/argos-backup <<CRON
17 3 * * * root cd $(pwd) && bash scripts/backup.sh >> /var/log/argos-backup.log 2>&1
CRON

log "Verificação final"
bash scripts/verificar.sh || true

echo
echo "Pronto. Portal: $(grep -E '^MCP_BRASIL_BASE_URL=' .env | cut -d= -f2-)/conta"
