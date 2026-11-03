"""Tests for the Notícias feed parser and client."""

import httpx
import pytest
import respx

from mcp_brasil.data.noticias import client
from mcp_brasil.data.noticias.constants import FONTES


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    client.buscar_feed.cache.clear()  # type: ignore[attr-defined]


RSS2 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>AB</title>
<item><title>Receita libera &amp; lote do IR</title>
<link>https://agenciabrasil.ebc.com.br/economia/noticia/1</link>
<description>&lt;p&gt;Texto &lt;b&gt;com&lt;/b&gt; HTML&lt;/p&gt;</description>
<pubDate>Fri, 30 Oct 2026 08:00:00 -0300</pubDate></item>
</channel></rss>"""

RDF = """<?xml version="1.0" encoding="utf-8" ?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://purl.org/rss/1.0/">
<item rdf:about="https://www.gov.br/x/2024"><title>2024</title>
<link>https://www.gov.br/x/2024</link><dc:date>2024-01-01T00:00:00Z</dc:date></item>
<item rdf:about="https://www.gov.br/x/foto.jpg/view"><title>foto</title>
<link>https://www.gov.br/x/foto.jpg/view</link></item>
<item rdf:about="https://www.gov.br/x/noticia"><title>ANS anuncia reajuste</title>
<link>https://www.gov.br/x/noticia</link><description>Resumo</description>
<dc:date>2026-07-08T21:14:23Z</dc:date></item>
</rdf:RDF>"""

ATOM = """﻿<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>BC</title>
<entry><title>Copom mantém Selic</title><link href="https://www.bcb.gov.br/n/1"/>
<updated>2026-10-29T16:32:39-03:00</updated><summary>Decisão unânime</summary></entry>
</feed>"""


class TestParseFeed:
    def test_rss2(self) -> None:
        [n] = client.parse_feed(RSS2, "agencia_brasil")
        assert n.titulo == "Receita libera & lote do IR"
        assert n.resumo == "Texto com HTML"
        assert n.publicado_em is not None and n.publicado_em.utcoffset() is not None

    def test_rdf_skips_folders_and_images(self) -> None:
        noticias = client.parse_feed(RDF, "ans")
        assert [n.titulo for n in noticias] == ["ANS anuncia reajuste"]

    def test_atom_with_bom(self) -> None:
        [n] = client.parse_feed(ATOM, "banco_central")
        assert n.link == "https://www.bcb.gov.br/n/1"
        assert n.resumo == "Decisão unânime"

    def test_invalid_xml(self) -> None:
        assert client.parse_feed("<html>challenge", "senado") == []


class TestParseData:
    @pytest.mark.parametrize(
        "valor", ["Thu, 29 Oct 2026 20:59:00 GMT", "2026-10-29T23:53:08Z", "2026-10-29T16:32:39"]
    )
    def test_formats(self, valor: str) -> None:
        dt = client.parse_data(valor)
        assert dt is not None and dt.tzinfo is not None

    def test_invalid(self) -> None:
        assert client.parse_data("ontem") is None


class TestBuscarVarios:
    @respx.mock
    async def test_sorts_and_reports_failures(self) -> None:
        respx.get(FONTES["agencia_brasil"].url).mock(return_value=httpx.Response(200, text=RSS2))
        respx.get(FONTES["banco_central"].url).mock(return_value=httpx.Response(200, text=ATOM))
        respx.get(FONTES["senado"].url).mock(return_value=httpx.Response(404))
        noticias, falhas = await client.buscar_varios(
            ["agencia_brasil", "banco_central", "senado"]
        )
        assert [n.fonte for n in noticias] == ["agencia_brasil", "banco_central"]
        assert falhas == ["senado"]
