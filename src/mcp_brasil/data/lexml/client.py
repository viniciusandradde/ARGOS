"""HTTP client for the LexML SRU (Search/Retrieval via URL) API.

Base URL: https://www.lexml.gov.br/busca/SRU
Auth: None required
Query language: CQL (ex: dc.title any "dados pessoais" and tipoDocumento any "Lei")
Response: XML (srw:searchRetrieveResponse with srw_dc:dc records)

Note: the endpoint sits behind the Senado WAF, which may answer automated
traffic from some datacenter IPs with an HTML challenge page instead of XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from mcp_brasil._shared.http_client import http_get_text
from mcp_brasil.exceptions import HttpClientError

from .constants import SRU_URL
from .schemas import Norma, ResultadoBusca

_CAMPOS = {
    "urn": "urn",
    "title": "titulo",
    "description": "ementa",
    "tipoDocumento": "tipo",
    "date": "data",
    "localidade": "localidade",
    "autoridade": "autoridade",
}


class LexmlBloqueadoError(HttpClientError):
    """Raised when LexML returns its anti-bot HTML page instead of XML."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _escape(termo: str) -> str:
    return termo.replace("\\", " ").replace('"', " ").strip()


def montar_cql(termo: str, tipo: str | None = None, localidade: str | None = None) -> str:
    """Build a CQL query searching title and description (ementa)."""
    t = _escape(termo)
    partes = [f'(dc.title any "{t}" or dc.description any "{t}")']
    if tipo:
        partes.append(f'tipoDocumento any "{_escape(tipo)}"')
    if localidade:
        partes.append(f'localidade any "{_escape(localidade)}"')
    return " and ".join(partes)


def parse_resposta(xml_text: str) -> ResultadoBusca:
    """Parse an SRU searchRetrieveResponse document."""
    texto = xml_text.strip()
    erro = LexmlBloqueadoError(
        "O LexML não devolveu uma resposta SRU válida (provável página de verificação "
        "anti-robô). Tente novamente mais tarde ou a partir de outra rede."
    )
    if "searchRetrieveResponse" not in texto[:2000]:
        raise erro
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as exc:
        raise erro from exc
    total = 0
    normas: list[Norma] = []
    for el in root.iter():
        nome = _local(el.tag)
        if nome == "numberOfRecords" and el.text and el.text.strip().isdigit():
            total = int(el.text.strip())
        elif nome == "dc":
            dados: dict[str, str] = {}
            for child in el:
                campo = _CAMPOS.get(_local(child.tag))
                if campo and child.text and campo not in dados:
                    dados[campo] = " ".join(child.text.split())
            normas.append(Norma(**dados))
    return ResultadoBusca(total=total or len(normas), normas=normas)


async def buscar(cql: str, max_registros: int, inicio: int = 1) -> ResultadoBusca:
    """Run an SRU searchRetrieve request."""
    params = {
        "operation": "searchRetrieve",
        "version": "1.1",
        "query": cql,
        "maximumRecords": max_registros,
        "startRecord": inicio,
    }
    xml_text = await http_get_text(SRU_URL, params=params, timeout=40)
    return parse_resposta(xml_text)
