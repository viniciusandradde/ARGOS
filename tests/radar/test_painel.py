"""Tests for the indicators DB, collector, situation room API, topics and price survey."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import httpx
import pytest
from fastmcp import FastMCP

from mcp_brasil.data.clima import client as clima_client
from mcp_brasil.data.clima import local as clima_local
from mcp_brasil.data.clima.schemas import LeituraEstacao
from mcp_brasil.radar import coletor, install
from mcp_brasil.radar.auth import RadarTokenVerifier
from mcp_brasil.radar.coletor import ConfigColeta, coletar_clima
from mcp_brasil.radar.indicadores import Indicadores
from mcp_brasil.radar.painel import montar, validar_tema
from mcp_brasil.radar.servico import RadarService


def _noticia(ind: Indicadores, link: str, titulo: str, nivel: str, fonte: str = "ecdc",
             categoria: str = "epidemias", escopo: str = "mundo") -> None:  # fmt: skip
    agora = datetime.now(timezone.utc).isoformat()
    ind.executar(
        "INSERT INTO noticias VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (link, fonte, fonte.upper(), categoria, escopo, "en", titulo, "", nivel, agora, agora),
    )


@pytest.fixture
def ind() -> Indicadores:
    i = Indicadores(":memory:")
    _noticia(i, "a", "Ebola outbreak in Kenya", "critico")
    _noticia(i, "b", "Copom mantém Selic", "alto", "agencia_brasil_economia", "economia", "brasil")
    _noticia(i, "c", "Museu reabre", "normal", "agencia_brasil", "geral", "brasil")
    i.executar(
        "INSERT INTO arboviroses VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("5003702", "Dourados/MS", "chikungunya", 202642, 4, 35, 10998, 28.4, 1.48, "x"),
    )
    i.executar(
        "INSERT INTO enso_status VALUES (1, 'El Niño Advisory', 'El Niño muito forte', 's', 'x')"
    )
    i.executar("INSERT INTO enso_oni VALUES (2026, 'JAS', 2.16, 1.69)")
    i.executar("INSERT INTO enso_oni VALUES (2026, 'JJA', 1.80, 1.36)")
    return i


class TestIndicadores:
    def test_precos_medias(self, ind: Indicadores) -> None:
        hoje = date.today().isoformat()
        for mercado, preco in (("A", 30.0), ("B", 34.0)):
            ind.adicionar_preco(produto="Arroz 5kg", mercado=mercado, cidade="Dourados/MS",
                                preco=preco, unidade="pct", data=hoje, usuario_id=1)  # fmt: skip
        [m] = ind.medias_precos("Dourados/MS")
        assert (m["media"], m["minimo"], m["maximo"], m["mercados"]) == (32.0, 30.0, 34.0, 2)
        pid = ind.listar_precos()[0]["id"]
        assert not ind.remover_preco(pid, usuario_id=99)
        assert ind.remover_preco(pid, usuario_id=1)

    def test_montar(self, ind: Indicadores) -> None:
        temas = [{"id": 1, "nome": "Juros", **validar_tema({"nome": "Juros", "termos": "selic"})}]
        dados = montar(ind, temas=temas, area_inmet="Mato Grosso do Sul", cidade_precos="")
        assert dados["enso"]["status"]["alerta"] == "El Niño Advisory"
        assert [o["trimestre"] for o in dados["enso"]["oni"]] == ["JJA", "JAS"]
        assert [n["link"] for n in dados["criticos"]] == ["a"]
        assert [n["link"] for n in dados["surtos"]] == ["a"]
        assert [n["link"] for n in dados["temas"][0]["noticias"]] == ["b"]
        assert dados["arboviroses"][0]["nivel"] == 4
        assert dados["contagem"] == {"critico": 1, "alto": 1, "normal": 1}


class TestTema:
    def test_validacao(self) -> None:
        with pytest.raises(ValueError):
            validar_tema({"nome": ""})
        with pytest.raises(ValueError):
            validar_tema({"nome": "x"})
        t = validar_tema(
            {"nome": "H5N1", "termos": "h5n1, bird flu", "categorias": ["saude", "xyz"],
             "escopo": "lua", "nivel_minimo": "critico"}
        )  # fmt: skip
        assert t["termos"] == ["h5n1", "bird flu"] and t["categorias"] == ["saude"]
        assert t["escopo"] == "todos" and t["nivel_minimo"] == "critico"


class TestColetor:
    async def test_etapas_isoladas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def ok(ind: Indicadores, cfg: coletor.ConfigColeta) -> str:
            return "ok"

        async def falha(ind: Indicadores, cfg: coletor.ConfigColeta) -> str:
            raise RuntimeError("fonte fora do ar")

        monkeypatch.setattr(coletor, "ETAPAS", {"a": ok, "b": falha})
        ind = Indicadores(":memory:")
        r = await coletor.coletar_tudo(ind, coletor.ConfigColeta())
        assert r == {"a": "ok", "b": "ERRO: fonte fora do ar"}
        log = {x["etapa"]: x["ok"] for x in ind.consultar("SELECT etapa, ok FROM coletas")}
        assert log == {"a": 1, "b": 0}

    async def test_coletar_noticias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_brasil.data.noticias.schemas import Noticia

        n = Noticia(fonte="oms", titulo="WHO alert", link="https://who/1", nivel="alto",
                    publicado_em=datetime.now(timezone.utc))  # fmt: skip

        async def fake(ids: list[str]) -> tuple[list[Noticia], list[str]]:
            return [n, n], ["ecdc"]

        monkeypatch.setattr("mcp_brasil.data.noticias.client.buscar_varios", fake)
        ind = Indicadores(":memory:")
        assert await coletor.coletar_noticias(ind, coletor.ConfigColeta()) == (
            "2 notícias, 1 fontes com falha"
        )
        assert ind.consultar("SELECT fonte_nome, escopo FROM noticias") == [
            {"fonte_nome": "OMS — WHO News", "escopo": "mundo"}
        ]


@pytest.fixture
async def http(servico: RadarService, ind: Indicadores) -> AsyncIterator[httpx.AsyncClient]:
    mcp = FastMCP("t", auth=RadarTokenVerifier(servico))
    install(mcp, servico, ind)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mcp.http_app()), base_url="https://radar.test"
    ) as c:
        yield c


async def _login(
    http: httpx.AsyncClient, servico: RadarService, admin: bool = False
) -> dict[str, str]:
    email = "adm@b.com" if admin else "cli@b.com"
    servico.cadastrar(email, "senha-forte-1", papel="admin" if admin else "cliente")
    r = await http.post("/api/login", json={"email": email, "senha": "senha-forte-1"})
    return {"X-Radar-Sessao": r.json()["sessao"]}


class TestRotasPainel:
    async def test_painel_exige_assinatura(
        self, http: httpx.AsyncClient, servico: RadarService
    ) -> None:
        h = await _login(http, servico)
        assert (await http.get("/api/painel", headers=h)).status_code == 402
        page = await http.get("/painel")
        assert page.status_code == 200 and "ARGOS" in page.text and "{{NOME}}" not in page.text

    async def test_fluxo_completo(self, http: httpx.AsyncClient, servico: RadarService) -> None:
        h = await _login(http, servico)
        servico.conceder(servico.store.usuario_por_email("cli@b.com").id, "essencial", 30)  # type: ignore[union-attr]

        r = await http.post("/api/temas", headers=h, json={"nome": "Surtos", "termos": "ebola"})
        assert r.status_code == 201
        tema_id = r.json()["id"]
        assert (await http.post("/api/temas", headers=h, json={"nome": "x"})).status_code == 400

        preco = {
            "produto": "Arroz 5kg",
            "mercado": "Mercado A",
            "preco": "29,90",
            "unidade": "pct",
        }
        r = await http.post("/api/precos", headers=h, json=preco)
        assert r.status_code == 201
        assert (
            await http.post("/api/precos", headers=h, json={"produto": "x"})
        ).status_code == 400

        dados = (await http.get("/api/painel?escopo=brasil", headers=h)).json()
        assert dados["nome"] == "ARGOS" and dados["admin"] is False
        assert [n["link"] for n in dados["temas"][0]["noticias"]] == ["a"]
        assert {n["link"] for n in dados["feed"]} == {"b", "c"}
        assert dados["precos"]["medias"][0]["media"] == 29.9

        assert (await http.delete(f"/api/temas/{tema_id}", headers=h)).status_code == 200
        assert (await http.delete(f"/api/temas/{tema_id}", headers=h)).status_code == 404

    async def test_coletar_so_admin(
        self, http: httpx.AsyncClient, servico: RadarService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def ok(ind: Indicadores, cfg: coletor.ConfigColeta) -> str:
            return "ok"

        monkeypatch.setattr(coletor, "ETAPAS", {"enso": ok})
        h = await _login(http, servico)
        assert (await http.post("/api/admin/coletar", headers=h)).status_code == 403
        ha = await _login(http, servico, admin=True)
        r = await http.post("/api/admin/coletar", headers=ha)
        assert r.json() == {"resultados": {"enso": "ok"}}


class TestRotasClima:
    async def test_clima_local(
        self, http: httpx.AsyncClient, servico: RadarService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mcp_brasil.data.clima import local as clima_local

        async def fake(alvo: clima_local.Local) -> dict[str, object]:
            return {"local": alvo.model_dump(), "riscos": []}

        monkeypatch.setattr(clima_local, "relatorio", fake)
        h = await _login(http, servico)
        assert (
            await http.get("/api/clima/local?uf=MS&cidade=Dourados", headers=h)
        ).status_code == 402
        servico.conceder(servico.store.usuario_por_email("cli@b.com").id, "essencial", 30)  # type: ignore[union-attr]
        r = await http.get("/api/clima/local?lat=-22.2&lon=-54.8&cidade=Dourados&uf=MS", headers=h)
        assert (
            r.json()["local"]["precisao"] == "ponto"
            and r.json()["local"]["geocodigo"] == "5003702"
        )
        assert (await http.get("/api/clima/local?lat=40&lon=10", headers=h)).status_code == 400
        assert (await http.get("/api/clima/local?uf=MS", headers=h)).status_code == 400
        municipios = (await http.get("/api/clima/municipios?uf=MS", headers=h)).json()[
            "municipios"
        ]
        assert "Dourados" in municipios and len(municipios) == 79
        page = await http.get("/clima")
        assert page.status_code == 200 and "RADAR CLIMÁTICO LOCAL" in page.text


class TestClimaMedido:
    PREVISAO: ClassVar[dict[str, dict[str, Any]]] = {
        "current": {
            "temperature_2m": 28.9,
            "relative_humidity_2m": 70,
            "wind_speed_10m": 10,
            "weather_code": 2,
        },
        "daily": {
            "time": ["2026-11-04"],
            "temperature_2m_min": [21.0],
            "temperature_2m_max": [33.3],
            "precipitation_sum": [3.7],
            "precipitation_probability_max": [69],
            "weather_code": [95],
        },
    }
    LEITURA = LeituraEstacao(
        rotulo="Embrapa Guia Clima · Dourados Embrapa",
        codigo="1",
        nome="Dourados Embrapa",
        distancia_km=6,
        quando="2026-11-04T22:00:00+00:00",
        temperatura=31.9,
        umidade=52,
        vento_kmh=15.5,
        hoje_max=35.4,
        hoje_min=24.5,
    )

    def _preparar(
        self,
        monkeypatch: pytest.MonkeyPatch,
        medicao: AsyncMock,
        oficial: AsyncMock | None = None,
    ) -> None:
        local = [{"latitude": -22.2, "longitude": -54.8, "admin1": "Mato Grosso do Sul"}]
        monkeypatch.setattr(clima_client, "geocodificar", AsyncMock(return_value=local))
        monkeypatch.setattr(clima_client, "previsao", AsyncMock(return_value=self.PREVISAO))
        monkeypatch.setattr(clima_client, "qualidade_ar", AsyncMock(return_value={}))
        monkeypatch.setattr(clima_client, "medicao_local", medicao)
        monkeypatch.setattr(
            clima_client,
            "previsao_inmet",
            oficial or AsyncMock(return_value={"2026-11-04": (23.0, 36.0)}),
        )
        monkeypatch.setattr(
            clima_client,
            "faixa_modelos",
            AsyncMock(return_value={"2026-11-04": (33.2, 36.7)}),
        )
        monkeypatch.setattr(clima_local, "geocodigo_ibge", lambda cidade, uf: "5003702")

    @pytest.mark.asyncio
    async def test_prefere_a_estacao(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._preparar(monkeypatch, AsyncMock(return_value=self.LEITURA))
        ind = Indicadores(":memory:")
        await coletar_clima(ind, ConfigColeta(cidades=["Dourados/MS"]))
        atual = ind.consultar("SELECT * FROM clima_atual")[0]
        assert (atual["temperatura"], atual["umidade"], atual["vento"]) == (31.9, 52, 15.5)
        assert atual["estacao"] == "Embrapa Guia Clima · Dourados Embrapa"
        assert (atual["hoje_max"], atual["hoje_min"]) == (35.4, 24.5)
        assert atual["codigo"] == 2  # the sky condition still comes from the model
        dia = ind.consultar("SELECT * FROM clima_previsao")[0]
        assert (dia["tmin"], dia["tmax"], dia["fonte"]) == (23.0, 36.0, "INMET")
        assert (dia["tmax_baixa"], dia["tmax_alta"]) == (33.2, 36.7)

    @pytest.mark.asyncio
    async def test_usa_o_modelo_se_a_estacao_falhar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        falha = AsyncMock(side_effect=RuntimeError("fora do ar"))
        self._preparar(monkeypatch, falha, falha)
        ind = Indicadores(":memory:")
        await coletar_clima(ind, ConfigColeta(cidades=["Dourados/MS"]))
        atual = ind.consultar("SELECT * FROM clima_atual")[0]
        assert atual["temperatura"] == 28.9
        assert atual["estacao"] is None
        dia = ind.consultar("SELECT * FROM clima_previsao")[0]
        assert (dia["tmax"], dia["fonte"]) == (33.3, "Open-Meteo")

    def test_migra_banco_existente(self, tmp_path: Path) -> None:
        caminho = tmp_path / "indicadores.db"
        antigo = sqlite3.connect(caminho)
        antigo.executescript(
            "CREATE TABLE clima_atual (cidade TEXT PRIMARY KEY, temperatura REAL, umidade REAL, "
            "vento REAL, codigo INTEGER, aqi REAL, atualizado_em TEXT NOT NULL);"
            "CREATE TABLE clima_previsao (cidade TEXT NOT NULL, data TEXT NOT NULL, tmin REAL, "
            "tmax REAL, chuva_mm REAL, prob_chuva REAL, codigo INTEGER, "
            "PRIMARY KEY (cidade, data));"
            "INSERT INTO clima_atual (cidade, atualizado_em) VALUES ('Dourados/MS', 'x');"
        )
        antigo.close()
        ind = Indicadores(str(caminho))
        linha = ind.consultar("SELECT * FROM clima_atual")[0]
        assert linha["cidade"] == "Dourados/MS"
        assert linha["estacao"] is None
        assert ind.consultar("SELECT tmax_alta FROM clima_previsao") == []
