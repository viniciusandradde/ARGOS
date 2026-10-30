"""Pydantic schemas for the LexML feature."""

from __future__ import annotations

from pydantic import BaseModel


class Norma(BaseModel):
    """A LexML record (Dublin Core + LexML extensions)."""

    urn: str = ""
    titulo: str = ""
    ementa: str = ""
    tipo: str = ""
    data: str = ""
    localidade: str = ""
    autoridade: str = ""

    @property
    def link(self) -> str:
        from .constants import URN_BASE_URL

        return f"{URN_BASE_URL}{self.urn}" if self.urn else ""


class ResultadoBusca(BaseModel):
    total: int = 0
    normas: list[Norma] = []
