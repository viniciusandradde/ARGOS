"""Cliente mínimo da API do Mercado Pago (assinaturas, Checkout Pro e webhooks).

Docs:
    - Assinaturas sem plano associado: POST /preapproval
    - Checkout Pro: POST /checkout/preferences
    - Pagamentos: GET /v1/payments/{id}
    - Notificações: header ``x-signature`` (ts, v1) validado com HMAC-SHA256
      sobre o manifesto ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;``
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

import httpx

from mcp_brasil._shared.http_client import create_client
from mcp_brasil.exceptions import HttpClientError

API_BASE = "https://api.mercadopago.com"


class MercadoPagoError(HttpClientError):
    """Erro retornado pela API do Mercado Pago."""


class MercadoPagoClient:
    def __init__(self, access_token: str, base_url: str = API_BASE) -> None:
        self._token = access_token
        self._base_url = base_url

    @property
    def configurado(self) -> bool:
        return bool(self._token)

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._token:
            raise MercadoPagoError("MERCADOPAGO_ACCESS_TOKEN não configurado")
        headers = {"Authorization": f"Bearer {self._token}"}
        if method == "POST":
            # Safe to retry creation calls without duplicating charges
            headers["X-Idempotency-Key"] = str(uuid.uuid4())
        async with create_client(base_url=self._base_url, headers=headers) as client:
            try:
                resp = await client.request(method, path, json=json_body)
            except httpx.HTTPError as exc:
                raise MercadoPagoError(f"Falha de rede com o Mercado Pago: {exc}") from exc
        if resp.status_code >= 400:
            raise MercadoPagoError(
                f"Mercado Pago {method} {path} → HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data: dict[str, Any] = resp.json()
        return data

    async def criar_assinatura(
        self,
        *,
        motivo: str,
        email_pagador: str,
        valor: float,
        referencia: str,
        back_url: str,
        frequencia_meses: int = 1,
    ) -> dict[str, Any]:
        """Create a pending monthly subscription. The payer completes it at ``init_point``."""
        return await self._request(
            "POST",
            "/preapproval",
            {
                "reason": motivo,
                "external_reference": referencia,
                "payer_email": email_pagador,
                "back_url": back_url,
                "status": "pending",
                "auto_recurring": {
                    "frequency": frequencia_meses,
                    "frequency_type": "months",
                    "transaction_amount": round(valor, 2),
                    "currency_id": "BRL",
                },
            },
        )

    async def criar_preferencia(
        self,
        *,
        titulo: str,
        valor: float,
        email_pagador: str,
        referencia: str,
        url_retorno: str,
        url_notificacao: str,
    ) -> dict[str, Any]:
        """Create a Checkout Pro preference (Pix, boleto or card — one-off payment)."""
        return await self._request(
            "POST",
            "/checkout/preferences",
            {
                "items": [
                    {
                        "title": titulo,
                        "quantity": 1,
                        "unit_price": round(valor, 2),
                        "currency_id": "BRL",
                    }
                ],
                "payer": {"email": email_pagador},
                "external_reference": referencia,
                "back_urls": {
                    "success": url_retorno,
                    "pending": url_retorno,
                    "failure": url_retorno,
                },
                "auto_return": "approved",
                "notification_url": url_notificacao,
            },
        )

    async def obter_pagamento(self, pagamento_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/payments/{pagamento_id}")

    async def obter_assinatura(self, preapproval_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/preapproval/{preapproval_id}")

    async def obter_pagamento_autorizado(self, autorizado_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/authorized_payments/{autorizado_id}")

    async def cancelar_assinatura(self, preapproval_id: str) -> dict[str, Any]:
        return await self._request(
            "PUT", f"/preapproval/{preapproval_id}", {"status": "cancelled"}
        )


def validar_assinatura_webhook(
    x_signature: str | None, x_request_id: str | None, data_id: str | None, segredo: str
) -> bool:
    """Validate the ``x-signature`` header sent by Mercado Pago webhooks."""
    if not x_signature:
        return False
    partes: dict[str, str] = {}
    for parte in x_signature.split(","):
        chave, _, valor = parte.partition("=")
        partes[chave.strip()] = valor.strip()
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not ts or not v1:
        return False

    manifesto = ""
    if data_id:
        # MP signs alphanumeric ids in lowercase
        manifesto += f"id:{data_id.lower() if data_id.isalnum() else data_id};"
    if x_request_id:
        manifesto += f"request-id:{x_request_id};"
    manifesto += f"ts:{ts};"
    esperado = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)
