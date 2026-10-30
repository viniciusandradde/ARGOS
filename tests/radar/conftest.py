"""Fixtures for Radar Brasil tests."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_brasil.radar.planos import carregar_planos
from mcp_brasil.radar.servico import RadarConfig, RadarService
from mcp_brasil.radar.store import Store


class FakeMercadoPago:
    """In-memory stand-in for MercadoPagoClient."""

    def __init__(self) -> None:
        self.configurado = True
        self.pagamentos: dict[str, dict[str, Any]] = {}
        self.assinaturas: dict[str, dict[str, Any]] = {}
        self.autorizados: dict[str, dict[str, Any]] = {}
        self.criadas: list[dict[str, Any]] = []
        self.canceladas: list[str] = []

    async def criar_assinatura(self, **kwargs: Any) -> dict[str, Any]:
        self.criadas.append({"tipo": "assinatura", **kwargs})
        return {"id": "pre123", "init_point": "https://mp.test/assinar"}

    async def criar_preferencia(self, **kwargs: Any) -> dict[str, Any]:
        self.criadas.append({"tipo": "preferencia", **kwargs})
        return {"id": "pref1", "init_point": "https://mp.test/pagar"}

    async def obter_pagamento(self, pagamento_id: str) -> dict[str, Any]:
        return self.pagamentos[pagamento_id]

    async def obter_assinatura(self, preapproval_id: str) -> dict[str, Any]:
        return self.assinaturas[preapproval_id]

    async def obter_pagamento_autorizado(self, autorizado_id: str) -> dict[str, Any]:
        return self.autorizados[autorizado_id]

    async def cancelar_assinatura(self, preapproval_id: str) -> dict[str, Any]:
        self.canceladas.append(preapproval_id)
        return {"id": preapproval_id, "status": "cancelled"}


@pytest.fixture
def mp() -> FakeMercadoPago:
    return FakeMercadoPago()


@pytest.fixture
def servico(mp: FakeMercadoPago) -> RadarService:
    config = RadarConfig(
        db_path=":memory:",
        segredo="segredo-de-teste",
        base_url="https://radar.test",
        planos=carregar_planos(None),
    )
    return RadarService(config, Store(":memory:"), mp=mp)  # type: ignore[arg-type]
