"""End-to-end tests of the Radar HTTP routes, API-key auth and quota middleware."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import AsyncIterator

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport

from mcp_brasil.radar import install
from mcp_brasil.radar.auth import RadarTokenVerifier
from mcp_brasil.radar.servico import RadarService, referencia

from .conftest import FakeMercadoPago


def _app(servico: RadarService) -> FastMCP:
    mcp = FastMCP("radar-test", auth=RadarTokenVerifier(servico))

    @mcp.tool
    def ping() -> str:
        return "pong"

    install(mcp, servico)
    return mcp


@pytest.fixture
async def http(servico: RadarService) -> AsyncIterator[httpx.AsyncClient]:
    app = _app(servico).http_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://radar.test"
    ) as client:
        yield client


async def _sessao(http: httpx.AsyncClient, email: str = "ana@b.com") -> dict[str, str]:
    r = await http.post("/api/cadastro", json={"email": email, "senha": "senha-forte-1"})
    assert r.status_code == 201, r.text
    return {"X-Radar-Sessao": r.json()["sessao"]}


class TestPortal:
    async def test_portal_e_planos(self, http: httpx.AsyncClient) -> None:
        r = await http.get("/conta")
        assert r.status_code == 200 and "Radar" in r.text
        planos = (await http.get("/api/planos")).json()
        assert {p["id"] for p in planos["planos"]} == {"essencial", "profissional", "empresarial"}

    async def test_fluxo_conta(self, http: httpx.AsyncClient) -> None:
        h = await _sessao(http)
        eu = (await http.get("/api/eu", headers=h)).json()
        assert eu["acesso_ativo"] is False and eu["mcp_url"] == "https://radar.test/mcp"

        chave = (await http.post("/api/chaves", json={"nome": "Claude"}, headers=h)).json()
        assert chave["chave"].startswith("rb_")
        r = await http.delete(f"/api/chaves/{chave['id']}", headers=h)
        assert r.status_code == 200
        assert (await http.delete(f"/api/chaves/{chave['id']}", headers=h)).status_code == 404

        login = await http.post("/api/login", json={"email": "ana@b.com", "senha": "errada"})
        assert login.status_code == 401
        assert (await http.get("/api/eu")).status_code == 401

    async def test_checkout(self, http: httpx.AsyncClient, mp: FakeMercadoPago) -> None:
        h = await _sessao(http)
        r = await http.post(
            "/api/cobranca/checkout", json={"plano": "essencial", "modo": "avulso"}, headers=h
        )
        assert r.json() == {"url": "https://mp.test/pagar"}
        r = await http.post("/api/cobranca/checkout", json={"plano": "x"}, headers=h)
        assert r.status_code == 400

    async def test_admin(self, http: httpx.AsyncClient, servico: RadarService) -> None:
        h_cliente = await _sessao(http, "cli@b.com")
        assert (await http.get("/api/admin/usuarios", headers=h_cliente)).status_code == 403

        servico.cadastrar("adm@b.com", "senha-forte-1", papel="admin")
        credenciais = {"email": "adm@b.com", "senha": "senha-forte-1"}
        login = await http.post("/api/login", json=credenciais)
        h = {"X-Radar-Sessao": login.json()["sessao"]}
        usuarios = (await http.get("/api/admin/usuarios", headers=h)).json()["usuarios"]
        cli = next(u for u in usuarios if u["email"] == "cli@b.com")
        r = await http.patch(
            f"/api/admin/usuarios/{cli['id']}",
            json={"conceder_plano": "profissional", "dias": 10},
            headers=h,
        )
        assert r.status_code == 200
        assert (await http.get("/api/eu", headers=h_cliente)).json()["acesso_ativo"] is True


class TestWebhook:
    async def test_webhook_credita(
        self, http: httpx.AsyncClient, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        mp.pagamentos["123"] = {
            "id": 123,
            "status": "approved",
            "transaction_amount": 49.9,
            "currency_id": "BRL",
            "external_reference": referencia(u.id, "essencial", "avulso"),
        }
        r = await http.post(
            "/webhooks/mercadopago?data.id=123&type=payment",
            json={"type": "payment", "data": {"id": "123"}},
        )
        assert r.status_code == 200 and r.json()["resultado"].startswith("creditado")
        assert servico.acesso_ativo(u)

    async def test_assinatura_invalida(
        self, http: httpx.AsyncClient, servico: RadarService
    ) -> None:
        servico.config.mp_webhook_secret = "segredo"
        r = await http.post(
            "/webhooks/mercadopago?data.id=1&type=payment",
            headers={"x-signature": "ts=1,v1=errado", "x-request-id": "r"},
            json={"type": "payment", "data": {"id": "1"}},
        )
        assert r.status_code == 401

    async def test_assinatura_valida(self, http: httpx.AsyncClient, servico: RadarService) -> None:
        servico.config.mp_webhook_secret = "segredo"
        manifesto = "id:abc;request-id:r1;ts:99;"
        v1 = hmac.new(b"segredo", manifesto.encode(), hashlib.sha256).hexdigest()
        r = await http.post(
            "/webhooks/mercadopago?data.id=abc&type=merchant_order",
            headers={"x-signature": f"ts=99,v1={v1}", "x-request-id": "r1"},
            json={},
        )
        assert r.status_code == 200


class TestMcpAuthEQuota:
    async def test_chave_e_limite(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        chave = servico.criar_chave(u)["chave"]
        mcp = _app(servico)

        def transport(token: str) -> StreamableHttpTransport:
            return StreamableHttpTransport(
                "https://radar.test/mcp",
                headers={"Authorization": f"Bearer {token}"},
                httpx_client_factory=lambda **kw: httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="https://radar.test", **kw
                ),
            )

        app = mcp.http_app()
        async with app.router.lifespan_context(app):
            # No plan yet → 401
            with pytest.raises(Exception, match=r"401|Unauthorized|invalid_token"):
                async with Client(transport(chave)) as c:
                    await c.call_tool("ping")

            servico.config.planos["essencial"] = servico.config.planos["essencial"].__class__(
                id="essencial", nome="Essencial", preco=49.9, consultas_dia=2
            )
            servico.conceder(u.id, "essencial", 30)
            async with Client(transport(chave)) as c:
                assert (await c.call_tool("ping")).data == "pong"
                assert (await c.call_tool("ping")).data == "pong"
                with pytest.raises(Exception, match="Limite diário"):
                    await c.call_tool("ping")
