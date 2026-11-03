"""Clientes de envio: Telegram Bot API e WhatsApp.

- Telegram: gratuito. Crie o bot com o @BotFather e use o token.
- WhatsApp (padrão): Evolution API, auto-hospedada, conectada a um chip comum.
  Envia texto livre, sem templates nem custo por mensagem.
- WhatsApp (próxima versão): Cloud API oficial da Meta, com *template* aprovado
  ({{1}} = título, {{2}} = detalhes) e cobrança por conversa. Já implementado e
  testado, mas fora do fluxo padrão (``WHATSAPP_PROVEDOR=meta``).

Os dois clientes de WhatsApp expõem a mesma interface: ``configurado`` e
``enviar_alerta(numero, titulo, texto)``.
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


async def _request(
    metodo: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    async with create_client(headers=headers) as client:
        try:
            resp = await client.request(metodo, url, json=json_body)
        except httpx.HTTPError as exc:
            raise NotificacaoError(f"Falha de rede: {exc}") from exc
    if resp.status_code >= 400:
        raise NotificacaoError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def _post(url: str, json_body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    return await _request("POST", url, json_body, headers)


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


class EvolutionClient:
    """WhatsApp via Evolution API v2 (https://doc.evolution-api.com)."""

    def __init__(self, base_url: str, api_key: str, instancia: str = "argos") -> None:
        self._base = base_url.rstrip("/")
        self._instancia = instancia
        self._headers = {"apikey": api_key}

    @property
    def configurado(self) -> bool:
        return bool(self._base and self._headers["apikey"] and self._instancia)

    async def enviar_alerta(self, numero: str, titulo: str, texto: str) -> None:
        await _post(
            f"{self._base}/message/sendText/{self._instancia}",
            {
                "number": numero,
                "text": f"*{titulo}*\n\n{texto}"[:4000],
                "delay": 1200,  # "digitando..." before sending looks less like a bot
                "linkPreview": False,
            },
            self._headers,
        )

    async def numero_existe(self, numero: str) -> bool:
        data = await _post(
            f"{self._base}/chat/whatsappNumbers/{self._instancia}",
            {"numbers": [numero]},
            self._headers,
        )
        return bool(isinstance(data, list) and data and data[0].get("exists"))

    async def estado(self) -> str:
        """Connection state of the instance: ``open`` means ready to send."""
        data = await _request(
            "GET", f"{self._base}/instance/connectionState/{self._instancia}", None, self._headers
        )
        return str(((data or {}).get("instance") or {}).get("state", "desconhecido"))

    async def conectar(self, numero: str | None = None) -> dict[str, Any]:
        """Create the instance if needed and return the pairing code / QR payload."""
        try:
            await _post(
                f"{self._base}/instance/create",
                {"instanceName": self._instancia, "integration": "WHATSAPP-BAILEYS",
                 "qrcode": True},
                self._headers,
            )  # fmt: skip
        except NotificacaoError as exc:
            if "already" not in str(exc).lower() and "403" not in str(exc):
                raise
        url = f"{self._base}/instance/connect/{self._instancia}"
        if numero:
            url += f"?number={numero}"
        data: dict[str, Any] = await _request("GET", url, None, self._headers)
        return data


class WhatsAppClient:
    """WhatsApp Cloud API (Meta, oficial) — reservado para a próxima versão."""

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

    async def enviar_alerta(self, numero: str, titulo: str, texto: str) -> None:
        # Template parameters cannot contain line breaks: turn lines into " | "
        linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        await self.enviar_template(numero, titulo, " | ".join(linhas))

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
