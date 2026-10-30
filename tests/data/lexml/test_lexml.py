"""Tests for the LexML feature (client parser + tools)."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from mcp_brasil.data.lexml import client, tools
from mcp_brasil.data.lexml.constants import SRU_URL

SRU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/"
  xmlns:srw_dc="info:srw/schema/1/dc-schema" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <srw:numberOfRecords>42</srw:numberOfRecords>
  <srw:records><srw:record><srw:recordData><srw_dc:dc>
    <tipoDocumento>Lei</tipoDocumento>
    <dc:date>2018-08-14</dc:date>
    <urn>urn:lex:br:federal:lei:2018-08-14;13709</urn>
    <localidade>Brasil</localidade>
    <autoridade>Federal</autoridade>
    <dc:title>Lei nº 13.709, de 14 de Agosto de 2018</dc:title>
    <dc:description>Dispõe sobre a proteção de dados pessoais.</dc:description>
  </srw_dc:dc></srw:recordData></srw:record></srw:records>
</srw:searchRetrieveResponse>"""


class TestCql:
    def test_builds_filters_and_escapes(self) -> None:
        cql = client.montar_cql('dados "pessoais"', tipo="Lei", localidade="Brasil")
        assert cql == (
            '(dc.title any "dados  pessoais" or dc.description any "dados  pessoais") '
            'and tipoDocumento any "Lei" and localidade any "Brasil"'
        )


class TestParse:
    def test_parses_record(self) -> None:
        r = client.parse_resposta(SRU_XML)
        assert r.total == 42
        n = r.normas[0]
        assert n.tipo == "Lei"
        assert n.link.endswith("urn:lex:br:federal:lei:2018-08-14;13709")

    def test_detects_challenge_page(self) -> None:
        with pytest.raises(client.LexmlBloqueadoError):
            client.parse_resposta(
                "<!DOCTYPE html>\n<meta name=viewport><title>Verificação</title>"
            )


class TestTools:
    @respx.mock
    async def test_buscar_normas(self) -> None:
        route = respx.get(SRU_URL).mock(return_value=httpx.Response(200, text=SRU_XML))
        result = await tools.buscar_normas("dados pessoais", AsyncMock(), ano=2018)
        assert "Lei nº 13.709" in result
        assert route.calls[0].request.url.params["operation"] == "searchRetrieve"

    @respx.mock
    async def test_year_filter_excludes(self) -> None:
        respx.get(SRU_URL).mock(return_value=httpx.Response(200, text=SRU_XML))
        assert "Nenhuma" in await tools.buscar_normas("dados", AsyncMock(), ano=2020)

    @respx.mock
    async def test_blocked_returns_warning(self) -> None:
        respx.get(SRU_URL).mock(return_value=httpx.Response(200, text="<html>challenge</html>"))
        assert "anti-robô" in await tools.buscar_por_urn("urn:x", AsyncMock())
