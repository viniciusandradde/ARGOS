"""Pydantic schemas for the Notícias feature."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Noticia(BaseModel):
    """A news item normalized from RSS 2.0, RSS 1.0 (RDF) or Atom."""

    fonte: str
    titulo: str
    link: str
    resumo: str = ""
    publicado_em: datetime | None = None
