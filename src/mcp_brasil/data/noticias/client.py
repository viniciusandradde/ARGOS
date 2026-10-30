"""HTTP client + feed parser for official RSS/Atom feeds.

Supports the three formats used by Brazilian government sites:
RSS 2.0 (Agência Brasil, Câmara), RSS 1.0/RDF (gov.br Plone portals)
and Atom (Senado, Banco Central).
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from mcp_brasil._shared.http_client import http_get_text

from .constants import FONTES
from .schemas import Noticia

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_NAO_NOTICIA = re.compile(r"(/view$|\.(jpe?g|png|gif|pdf)$)", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _limpar(texto: str | None) -> str:
    if not texto:
        return ""
    return " ".join(html.unescape(_TAG_RE.sub(" ", texto)).split())


def parse_data(valor: str | None) -> datetime | None:
    """Parse RFC 822 (RSS 2.0) or ISO 8601 (RDF/Atom) dates into aware datetimes."""
    if not valor:
        return None
    valor = valor.strip()
    try:
        dt = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _eh_noticia(titulo: str, link: str) -> bool:
    # gov.br feeds also list folders ("2024") and images — skip those.
    return bool(titulo) and bool(link) and not titulo.isdigit() and not _NAO_NOTICIA.search(link)


def parse_feed(xml_text: str, fonte: str) -> list[Noticia]:
    """Parse an RSS/RDF/Atom document into normalized news items."""
    try:
        root = ET.fromstring(xml_text.lstrip("﻿").strip())
    except ET.ParseError:
        logger.warning("Feed %s retornou conteúdo que não é XML válido", fonte)
        return []

    noticias: list[Noticia] = []
    for item in root.iter():
        if _local(item.tag) not in ("item", "entry"):
            continue
        campos: dict[str, str] = {}
        for child in item:
            nome = _local(child.tag)
            if nome == "link" and child.get("href"):
                campos.setdefault("link", child.get("href", ""))
            elif child.text and nome not in campos:
                campos[nome] = child.text
        titulo = _limpar(campos.get("title"))
        link = (campos.get("link") or "").strip()
        if not _eh_noticia(titulo, link):
            continue
        data = (
            campos.get("pubDate")
            or campos.get("date")
            or campos.get("published")
            or campos.get("updated")
        )
        noticias.append(
            Noticia(
                fonte=fonte,
                titulo=titulo,
                link=link,
                resumo=_limpar(campos.get("description") or campos.get("summary"))[:400],
                publicado_em=parse_data(data),
            )
        )
    return noticias


async def buscar_feed(fonte_id: str) -> list[Noticia]:
    """Download and parse one feed by its id (see constants.FONTES)."""
    fonte = FONTES[fonte_id]
    texto = await http_get_text(fonte.url, timeout=20, max_retries=1)
    return parse_feed(texto, fonte_id)


async def buscar_varios(fonte_ids: list[str]) -> tuple[list[Noticia], list[str]]:
    """Fetch several feeds concurrently. Returns (items sorted newest first, failed ids)."""
    resultados = await asyncio.gather(*(buscar_feed(f) for f in fonte_ids), return_exceptions=True)
    noticias: list[Noticia] = []
    falhas: list[str] = []
    for fonte_id, res in zip(fonte_ids, resultados, strict=True):
        if isinstance(res, BaseException):
            logger.warning("Falha no feed %s: %s", fonte_id, res)
            falhas.append(fonte_id)
        else:
            noticias.extend(res)
    minimo = datetime.min.replace(tzinfo=timezone.utc)
    noticias.sort(key=lambda n: n.publicado_em or minimo, reverse=True)
    return noticias, falhas
