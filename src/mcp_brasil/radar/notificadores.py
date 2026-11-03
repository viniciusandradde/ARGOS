"""Clientes de envio: Telegram Bot API e WhatsApp Cloud API (Meta, oficial).

- Telegram: gratuito. Crie o bot com o @BotFather e use o token.
- WhatsApp: mensagens proativas exigem um *template* aprovado pela Meta, com dois
  parâmetros no corpo ({{1}} = título, {{2}} = detalhes). Cobrança por conversa.
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from mcp_brasil._shared.http_client import create_client
from mcp_brasil.exceptions import HttpClientError

TELEGRAM_API = "https://api.telegram.org"
WHATSAPP_API = "https://graph.facebook.com"
# WhatsApp template parameters cannot contain newlines/tabs nor 4+ consecutive spaces
_ESPACOS = re.compile(r"\s+")


class NotificacaoError(HttpClientError):
    """Falha ao enviar uma notificação."""


async def _post(url: str, json_body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    async with create_client(headers=headers) as client:
        try:
            resp = await client.post(url, json=json_body)
        except httpx.HTTPError as exc:
            raise NotificacaoError(f"Falha de rede: {exc}") from exc
    if resp.status_code >= 400:
        raise NotificacaoError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


class TelegramClient:
    def __init__(self, token: str, base_url: str = TELEGRAM_API) -> None:
        self._token = token
        self._base = base_url

    @property
    def configurado(self) -> bool:
        return bool(self._token)

    def _url(self, metodo: str) -> str:
        return f"{self._base}/bot{self._token}/{metodo}"

    async def enviar(self, chat_id: str, texto_html: str) -> None:
        await _post(
            self._url("sendMessage"),
            {
                "chat_id": chat_id,
                "text": texto_html[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    async def atualizacoes(self, offset: int) -> list[dict[str, Any]]:
        data = await _post(
            self._url("getUpdates"),
            {"offset": offset, "timeout": 0, "allowed_updates": ["message"]},
        )
        resultado = data.get("result", []) if isinstance(data, dict) else []
        return resultado if isinstance(resultado, list) else []

    async def nome_usuario(self) -> str:
        data = await _post(self._url("getMe"), {})
        return str((data.get("result") or {}).get("username", ""))


class WhatsAppClient:
    def __init__(
        self,
        token: str,
        phone_number_id: str,
        template: str = "alerta_argos",
        idioma: str = "pt_BR",
        versao: str = "v21.0",
        base_url: str = WHATSAPP_API,
    ) -> None:
        self._token = token
        self._phone_id = phone_number_id
        self._template = template
        self._idioma = idioma
        self._url = f"{base_url}/{versao}/{phone_number_id}/messages"

    @property
    def configurado(self) -> bool:
        return bool(self._token and self._phone_id)

    @staticmethod
    def _param(texto: str, limite: int) -> str:
        return _ESPACOS.sub(" ", texto).strip()[:limite] or "-"

    async def enviar_template(self, numero: str, titulo: str, detalhes: str) -> None:
        await _post(
            self._url,
            {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "template",
                "template": {
                    "name": self._template,
                    "language": {"code": self._idioma},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": self._param(titulo, 200)},
                                {"type": "text", "text": self._param(detalhes, 900)},
                            ],
                        }
                    ],
                },
            },
            headers={"Authorization": f"Bearer {self._token}"},
        )


def normalizar_whatsapp(numero: str) -> str | None:
    """Return the number in international format (digits only), assuming Brazil (55)."""
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) in (10, 11):  # DDD + número
        digitos = "55" + digitos
    return digitos if 12 <= len(digitos) <= 15 else None


def escapar(texto: str) -> str:
    return html.escape(texto, quote=False)
