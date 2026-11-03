"""Tests for Telegram/WhatsApp alerts: clients, event detection, dispatch and routes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import respx
from fastmcp import FastMCP

from mcp_brasil.radar import install
from mcp_brasil.radar.alertas import Alertas
from mcp_brasil.radar.auth import RadarTokenVerifier
from mcp_brasil.radar.indicadores import Indicadores
from mcp_brasil.radar.notificadores import (
    EvolutionClient,
    TelegramClient,
    WhatsAppClient,
    normalizar_whatsapp,
)
from mcp_brasil.radar.servico import RadarService


class FakeTelegram:
    configurado = True

    def __init__(self) -> None:
        self.enviadas: list[tuple[str, str]] = []
        self.updates: list[dict[str, Any]] = []

    async def enviar(self, chat_id: str, texto: str) -> None:
        self.enviadas.append((chat_id, texto))

    async def atualizacoes(self, offset: int) -> list[dict[str, Any]]:
        return [u for u in self.updates if u["update_id"] >= offset]

    async def nome_usuario(self) -> str:
        return "ArgosBot"


class FakeWhatsApp:
    configurado = True

    def __init__(self) -> None:
        self.enviadas: list[tuple[str, str, str]] = []

    async def enviar_alerta(self, numero: str, titulo: str, texto: str) -> None:
        self.enviadas.append((numero, titulo, texto))


def _agora(delta_min: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


@pytest.fixture
def ind() -> Indicadores:
    i = Indicadores(":memory:")
    for link, titulo, nivel, fonte, cat in [
        ("n1", "Ebola outbreak in Kenya", "critico", "ecdc", "epidemias"),
        ("n2", "Copom eleva a Selic", "alto", "agencia_brasil_economia", "economia"),
    ]:
        i.executar(
            "INSERT INTO noticias VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                link,
                fonte,
                fonte.upper(),
                cat,
                "mundo",
                "en",
                titulo,
                "",
                nivel,
                _agora(),
                _agora(),
            ),
        )
    i.executar(
        "INSERT INTO arboviroses VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("5003702", "Dourados/MS", "chikungunya", 202642, 4, 35, 10998, 28.4, 1.48, "x"),
    )
    i.executar("INSERT INTO enso_status VALUES (1, 'El Niño Advisory', 'El Niño forte', '', 'x')")
    i.executar(
        "INSERT INTO avisos_inmet VALUES (?,?,?,?,?,?,?)",
        ("inmet/1", "Tempestade", "Perigo", "2026-11-04", "2026-11-05",
         "Sudoeste de Mato Grosso do Sul", "Chuva forte"),
    )  # fmt: skip
    return i


@pytest.fixture
def tg() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def wa() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
def alertas(
    servico: RadarService, ind: Indicadores, tg: FakeTelegram, wa: FakeWhatsApp
) -> Alertas:
    return Alertas(servico, ind, tg, wa, intervalo_whatsapp=0)  # type: ignore[arg-type]


def _assinante(servico: RadarService, email: str = "a@b.com") -> int:
    u = servico.cadastrar(email, "senha-forte-1")
    servico.conceder(u.id, "essencial", 30)
    return u.id


class TestClientes:
    @pytest.mark.parametrize(
        ("entrada", "saida"),
        [("(67) 99999-1234", "5567999991234"), ("+55 67 99999 1234", "5567999991234"),
         ("123", None)],
    )  # fmt: skip
    def test_normalizar(self, entrada: str, saida: str | None) -> None:
        assert normalizar_whatsapp(entrada) == saida

    @respx.mock
    async def test_whatsapp_template_sem_quebras(self) -> None:
        rota = respx.post("https://graph.facebook.com/v21.0/123/messages").mock(
            return_value=httpx.Response(200, json={"messages": [{"id": "x"}]})
        )
        await WhatsAppClient("tok", "123").enviar_template("5567999991234", "Título", "a\nb\t c")
        corpo = json.loads(rota.calls[0].request.content)
        params = corpo["template"]["components"][0]["parameters"]
        assert corpo["template"]["name"] == "alerta_argos"
        assert [p["text"] for p in params] == ["Título", "a b c"]
        assert rota.calls[0].request.headers["authorization"] == "Bearer tok"

    @respx.mock
    async def test_meta_achata_linhas(self) -> None:
        rota = respx.post("https://graph.facebook.com/v21.0/123/messages").mock(
            return_value=httpx.Response(200, json={})
        )
        await WhatsAppClient("tok", "123").enviar_alerta("55", "T", "linha 1\n\nlinha 2")
        params = json.loads(rota.calls[0].request.content)["template"]["components"][0]
        assert params["parameters"][1]["text"] == "linha 1 | linha 2"

    @respx.mock
    async def test_evolution(self) -> None:
        base = "http://evo:8080"
        envio = respx.post(f"{base}/message/sendText/argos").mock(
            return_value=httpx.Response(201, json={"key": {"id": "x"}})
        )
        respx.post(f"{base}/chat/whatsappNumbers/argos").mock(
            return_value=httpx.Response(200, json=[{"exists": False, "number": "55"}])
        )
        respx.get(f"{base}/instance/connectionState/argos").mock(
            return_value=httpx.Response(200, json={"instance": {"state": "open"}})
        )
        respx.post(f"{base}/instance/create").mock(
            return_value=httpx.Response(403, json={"error": "already in use"})
        )
        respx.get(f"{base}/instance/connect/argos").mock(
            return_value=httpx.Response(200, json={"pairingCode": "WZYEH1YY", "code": "2@x"})
        )
        evo = EvolutionClient(base, "chave", "argos")
        await evo.enviar_alerta("5567999991234", "Título", "linha 1\nlinha 2")
        corpo = json.loads(envio.calls[0].request.content)
        assert corpo["number"] == "5567999991234"
        assert corpo["text"] == "*Título*\n\nlinha 1\nlinha 2"
        assert envio.calls[0].request.headers["apikey"] == "chave"
        assert await evo.numero_existe("55") is False
        assert await evo.estado() == "open"
        assert (await evo.conectar("5567999991234"))["pairingCode"] == "WZYEH1YY"
        assert not EvolutionClient("", "", "argos").configurado

    @respx.mock
    async def test_telegram_envio(self) -> None:
        rota = respx.post("https://api.telegram.org/botT/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        await TelegramClient("T").enviar("42", "<b>oi</b>")
        assert json.loads(rota.calls[0].request.content)["parse_mode"] == "HTML"


class TestEventos:
    def test_detecta_todos_os_tipos(self, alertas: Alertas, servico: RadarService) -> None:
        uid = _assinante(servico)
        servico.store.criar_tema(uid, "Juros", {"termos": ["selic"], "alertar": True})
        servico.store.criar_tema(uid, "Sem alerta", {"termos": ["copom"], "alertar": False})
        prefs = servico.store.preferencias_alerta(uid)
        usuario = servico.store.usuario_por_id(uid)
        assert usuario is not None
        chaves = {e.chave for e in alertas.eventos_para(usuario, prefs)}
        assert chaves == {
            "noticia:n2", "noticia:n1", "arbo:5003702:chikungunya:202642:4",
            "enso:El Niño Advisory", "inmet:inmet/1",
        }  # fmt: skip

    def test_respeita_tipos_e_janela(self, alertas: Alertas, servico: RadarService) -> None:
        uid = _assinante(servico)
        servico.store.salvar_preferencias(
            uid,
            tipos={"surtos": False, "arboviroses": False, "enso": False, "inmet": False},
            ativo_desde=_agora(+10),  # activated after the news were collected
        )
        usuario = servico.store.usuario_por_id(uid)
        assert usuario is not None
        assert alertas.eventos_para(usuario, servico.store.preferencias_alerta(uid)) == []


class TestDespacho:
    async def test_envia_resumo_uma_vez(
        self, alertas: Alertas, servico: RadarService, tg: FakeTelegram, wa: FakeWhatsApp
    ) -> None:
        uid = _assinante(servico)
        servico.store.salvar_preferencias(
            uid, telegram_chat_id="42", whatsapp_numero="5567999991234", whatsapp_verificado=True
        )
        assert await alertas.despachar() == {"usuarios": 1, "mensagens": 2}
        chat, texto = tg.enviadas[0]
        assert chat == "42" and "4 alerta(s)" in texto and "Chikungunya em Dourados/MS" in texto
        numero, titulo, texto = wa.enviadas[0]
        assert numero == "5567999991234" and titulo.endswith("4 alerta(s)")
        assert texto.splitlines()[0].startswith("🔴 Chikungunya em Dourados/MS")
        assert await alertas.despachar() == {"usuarios": 0, "mensagens": 0}

    async def test_ignora_sem_assinatura(
        self, alertas: Alertas, servico: RadarService, tg: FakeTelegram
    ) -> None:
        u = servico.cadastrar("sem@b.com", "senha-forte-1")
        servico.store.salvar_preferencias(u.id, telegram_chat_id="42")
        assert (await alertas.despachar())["usuarios"] == 0
        assert tg.enviadas == []

    async def test_vincula_telegram(
        self, alertas: Alertas, servico: RadarService, tg: FakeTelegram
    ) -> None:
        uid = _assinante(servico)
        servico.store.salvar_preferencias(uid, telegram_codigo="abc123")
        tg.updates = [
            {"update_id": 7, "message": {"text": "/start abc123", "chat": {"id": 99}}},
            {"update_id": 8, "message": {"text": "/start errado", "chat": {"id": 5}}},
        ]
        assert await alertas.processar_telegram() == 1
        prefs = servico.store.preferencias_alerta(uid)
        assert prefs["telegram_chat_id"] == "99" and prefs["telegram_codigo"] is None
        assert servico.store.estado("telegram_offset") == "9"
        assert [c for c, _ in tg.enviadas] == ["99", "5"]


@pytest.fixture
async def http(
    servico: RadarService, ind: Indicadores, alertas: Alertas
) -> AsyncIterator[httpx.AsyncClient]:
    mcp = FastMCP("t", auth=RadarTokenVerifier(servico))
    install(mcp, servico, ind, alertas)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp.http_app()), base_url="https://radar.test"
    ) as c:
        yield c


async def _sessao(http: httpx.AsyncClient, servico: RadarService) -> dict[str, str]:
    _assinante(servico, "cli@b.com")
    r = await http.post("/api/login", json={"email": "cli@b.com", "senha": "senha-forte-1"})
    return {"X-Radar-Sessao": r.json()["sessao"]}


class TestRotas:
    async def test_fluxo_telegram(
        self, http: httpx.AsyncClient, servico: RadarService, tg: FakeTelegram
    ) -> None:
        h = await _sessao(http, servico)
        r = await http.post("/api/alertas/telegram", headers=h)
        link = r.json()["link"]
        assert link.startswith("https://t.me/ArgosBot?start=")
        codigo = link.rsplit("=", 1)[1]
        tg.updates = [{"update_id": 1, "message": {"text": f"/start {codigo}", "chat": {"id": 7}}}]
        r = await http.post("/api/alertas/telegram/verificar", headers=h)
        assert r.json()["telegram"]["conectado"] is True
        assert (await http.post("/api/alertas/teste", headers=h)).json() == {
            "enviado_para": ["telegram"]
        }

    async def test_fluxo_whatsapp(
        self, http: httpx.AsyncClient, servico: RadarService, wa: FakeWhatsApp
    ) -> None:
        h = await _sessao(http, servico)
        r = await http.post("/api/alertas/whatsapp", headers=h, json={"numero": "123"})
        assert r.status_code == 400
        r = await http.post("/api/alertas/whatsapp", headers=h, json={"numero": "67 99999-1234"})
        assert r.json()["whatsapp"]["aguardando_codigo"] is True
        assert wa.enviadas[0][1] == "Código de verificação ARGOS"
        codigo = wa.enviadas[0][2].split("código é ")[1][:6]
        r = await http.post("/api/alertas/whatsapp", headers=h, json={"numero": "67 99999-1234"})
        assert r.status_code == 429  # one code per minute
        r = await http.post("/api/alertas/whatsapp/confirmar", headers=h, json={"codigo": "000"})
        assert r.status_code == 400
        r = await http.post("/api/alertas/whatsapp/confirmar", headers=h, json={"codigo": codigo})
        assert r.json()["whatsapp"]["verificado"] is True
        assert r.json()["whatsapp"]["numero"] == "+5567•••••1234"

    async def test_tipos(self, http: httpx.AsyncClient, servico: RadarService) -> None:
        h = await _sessao(http, servico)
        r = await http.put("/api/alertas", headers=h, json={"tipos": {"criticos": True, "x": 1}})
        ativos = {t["id"]: t["ativo"] for t in r.json()["tipos"]}
        assert ativos["criticos"] is True and "x" not in ativos

    async def test_sem_configuracao(self, servico: RadarService, ind: Indicadores) -> None:
        nada = Alertas(servico, ind, TelegramClient(""), WhatsAppClient("", ""))
        mcp = FastMCP("t", auth=RadarTokenVerifier(servico))
        install(mcp, servico, ind, nada)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp.http_app()), base_url="https://radar.test"
        ) as c:
            h = await _sessao(c, servico)
            assert (await c.post("/api/alertas/telegram", headers=h)).status_code == 503
            disponivel = (await c.get("/api/alertas", headers=h)).json()["telegram"]["disponivel"]
            assert disponivel is False


async def test_numero_sem_whatsapp(
    servico: RadarService, ind: Indicadores, tg: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    evo = EvolutionClient("http://evo:8080", "k", "argos")

    async def nao_existe(numero: str) -> bool:
        return False

    monkeypatch.setattr(evo, "numero_existe", nao_existe)
    al = Alertas(servico, ind, tg, evo)  # type: ignore[arg-type]
    mcp = FastMCP("t", auth=RadarTokenVerifier(servico))
    install(mcp, servico, ind, al)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp.http_app()), base_url="https://radar.test"
    ) as c:
        h = await _sessao(c, servico)
        r = await c.post("/api/alertas/whatsapp", headers=h, json={"numero": "67 99999-1234"})
        assert r.status_code == 400 and "não tem WhatsApp" in r.json()["erro"]
