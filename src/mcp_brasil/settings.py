"""Configuração global do mcp-brasil.

Valores podem ser sobrescritos via variáveis de ambiente.
Carrega automaticamente o arquivo .env na raiz do projeto.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- HTTP Client ---
HTTP_TIMEOUT: float = float(os.environ.get("MCP_BRASIL_HTTP_TIMEOUT", "30.0"))
HTTP_MAX_RETRIES: int = int(os.environ.get("MCP_BRASIL_HTTP_MAX_RETRIES", "3"))
HTTP_BACKOFF_BASE: float = float(os.environ.get("MCP_BRASIL_HTTP_BACKOFF_BASE", "1.0"))
USER_AGENT: str = os.environ.get("MCP_BRASIL_USER_AGENT", "mcp-brasil/0.1.0")

# --- Tool Discovery ---
# "bm25" (default): BM25 search transform — replaces list_tools with search_tools + call_tool
# "code_mode": Experimental CodeMode transform — search + get_tags + execute
# "none": No transform — all 154+ tools visible at once
TOOL_SEARCH: str = os.environ.get("MCP_BRASIL_TOOL_SEARCH", "bm25")

# --- Authentication ---
# When set, requires Authorization: Bearer <token> for HTTP transport.
# Leave empty/unset for local/stdio usage without auth.
MCP_BRASIL_API_TOKEN: str | None = os.environ.get("MCP_BRASIL_API_TOKEN") or None

# --- Authentication Strategy ---
# Modes: "none" | "static" | "oauth" | "multi" | "radar"
# "radar" = Radar Brasil commercial mode (users, API keys, plans, Mercado Pago)
# Auto-detect (backward compat): if unset, defaults to "static" when
# MCP_BRASIL_API_TOKEN is set, else "none".
_AUTH_MODE_RAW: str = os.environ.get("MCP_BRASIL_AUTH_MODE", "").strip().lower()
AUTH_MODE: str = _AUTH_MODE_RAW or ("static" if MCP_BRASIL_API_TOKEN else "none")

# OAuth — common
OAUTH_PROVIDER: str = os.environ.get("MCP_BRASIL_OAUTH_PROVIDER", "").strip().lower()
MCP_BRASIL_BASE_URL: str = os.environ.get("MCP_BRASIL_BASE_URL", "").strip()


def _parse_scopes(raw: str, default: list[str] | None = None) -> list[str]:
    """Parse a comma-separated list of scopes into a list[str].

    Returns ``default`` (or an empty list) when ``raw`` contains no entries.
    """
    items = [s.strip() for s in raw.split(",") if s.strip()]
    return items if items else (default or [])


# Azure (Entra ID)
AZURE_CLIENT_ID: str = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET: str = os.environ.get("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID: str = os.environ.get("AZURE_TENANT_ID", "")
AZURE_REQUIRED_SCOPES: list[str] = _parse_scopes(
    os.environ.get("AZURE_REQUIRED_SCOPES", ""), ["read"]
)

# Google
GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REQUIRED_SCOPES: list[str] = _parse_scopes(
    os.environ.get("GOOGLE_REQUIRED_SCOPES", ""), ["openid", "email"]
)

# GitHub
GITHUB_CLIENT_ID: str = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET: str = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REQUIRED_SCOPES: list[str] = _parse_scopes(os.environ.get("GITHUB_REQUIRED_SCOPES", ""))

# WorkOS (AuthKit)
AUTHKIT_DOMAIN: str = os.environ.get("AUTHKIT_DOMAIN", "").strip()
AUTHKIT_REQUIRED_SCOPES: list[str] = _parse_scopes(os.environ.get("AUTHKIT_REQUIRED_SCOPES", ""))

# --- Radar Brasil (MCP_BRASIL_AUTH_MODE=radar) ---
# Display name of the product (portal, situation room, MCP server name)
RADAR_NOME: str = os.environ.get("RADAR_NOME", "ARGOS")
# Public indicators database fed by the collector (read by the situation room and Metabase)
RADAR_INDICADORES_DB: str = os.environ.get("RADAR_INDICADORES_DB", "data/indicadores.db")
# Municipalities monitored by the collector ("Nome/UF", comma separated)
RADAR_CIDADES: list[str] = [
    c.strip()
    for c in os.environ.get("RADAR_CIDADES", "Dourados/MS,Campo Grande/MS").split(",")
    if c.strip()
]
# IPCA localities for the food panel (see data/alimentos/constants.py)
RADAR_ALIMENTOS_LOCALIDADES: list[str] = [
    c.strip()
    for c in os.environ.get("RADAR_ALIMENTOS_LOCALIDADES", "brasil,campo_grande").split(",")
    if c.strip()
]
# INMET warnings mentioning this text are highlighted in the situation room
RADAR_AREA_INMET: str = os.environ.get("RADAR_AREA_INMET", "Mato Grosso do Sul")
RADAR_COLETA_MINUTOS: int = int(os.environ.get("RADAR_COLETA_MINUTOS", "15"))
# Run the collector inside the web server process (set 0 when a separate collector runs)
RADAR_COLETOR_EMBUTIDO: bool = os.environ.get("RADAR_COLETOR_EMBUTIDO", "1") not in ("0", "false")
RADAR_DB_PATH: str = os.environ.get("RADAR_DB_PATH", "data/radar.db")
# Signs portal sessions. Generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
RADAR_SECRET_KEY: str = os.environ.get("RADAR_SECRET_KEY", "")
# JSON list overriding the default plans (see mcp_brasil/radar/planos.py)
RADAR_PLANOS: str = os.environ.get("RADAR_PLANOS", "")
# Days of access kept after the paid period ends (covers late renewals)
RADAR_CARENCIA_DIAS: int = int(os.environ.get("RADAR_CARENCIA_DIAS", "3"))
RADAR_SESSAO_HORAS: int = int(os.environ.get("RADAR_SESSAO_HORAS", "72"))
# Free trial granted on sign-up (0 = no trial)
RADAR_TESTE_DIAS: int = int(os.environ.get("RADAR_TESTE_DIAS", "0"))
RADAR_PLANO_TESTE: str = os.environ.get("RADAR_PLANO_TESTE", "essencial")

# Alerts — Telegram (free, create the bot with @BotFather)
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME: str = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
# Alerts — WhatsApp provider: "evolution" (default, self-hosted Evolution API) or
# "meta" (official Cloud API, planned for the next version).
WHATSAPP_PROVEDOR: str = os.environ.get("WHATSAPP_PROVEDOR", "evolution").strip().lower()
EVOLUTION_API_URL: str = os.environ.get("EVOLUTION_API_URL", "").strip()
EVOLUTION_API_KEY: str = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCIA: str = os.environ.get("EVOLUTION_INSTANCIA", "argos")
# Seconds between WhatsApp recipients in each alert round
WHATSAPP_INTERVALO_SEG: float = float(os.environ.get("WHATSAPP_INTERVALO_SEG", "3"))
# Meta Cloud API (next version): approved template with {{1}} title and {{2}} details.
WHATSAPP_TOKEN: str = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID: str = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TEMPLATE: str = os.environ.get("WHATSAPP_TEMPLATE", "alerta_argos")
WHATSAPP_TEMPLATE_IDIOMA: str = os.environ.get("WHATSAPP_TEMPLATE_IDIOMA", "pt_BR")
WHATSAPP_API_VERSAO: str = os.environ.get("WHATSAPP_API_VERSAO", "v21.0")
# Max items listed in each alert digest message
RADAR_ALERTAS_MAX_ITENS: int = int(os.environ.get("RADAR_ALERTAS_MAX_ITENS", "8"))

# Mercado Pago — https://www.mercadopago.com.br/developers/panel/app
MERCADOPAGO_ACCESS_TOKEN: str = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADOPAGO_WEBHOOK_SECRET: str = os.environ.get("MERCADOPAGO_WEBHOOK_SECRET", "")

# --- LLM Discovery (recomendar_tools) ---
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
