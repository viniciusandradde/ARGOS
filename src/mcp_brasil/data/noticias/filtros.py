"""Filtros de notícias reutilizados pelas tools e pelos temas do painel."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .constants import FONTES
from .criticidade import peso
from .schemas import Noticia


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


@dataclass
class Filtro:
    """Critérios de seleção. Campos vazios não filtram nada.

    ``termos`` casa se QUALQUER termo aparecer no título/resumo;
    ``excluir`` descarta a notícia se QUALQUER termo aparecer.
    """

    termos: list[str] = field(default_factory=list)
    excluir: list[str] = field(default_factory=list)
    categorias: list[str] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    escopo: str = "todos"  # brasil | mundo | todos
    idioma: str = "todos"  # pt | en | todos
    nivel_minimo: str = "normal"

    def fontes_alvo(self) -> list[str]:
        """Feeds that need to be downloaded to satisfy this filter."""
        if self.fontes:
            return [f for f in self.fontes if f in FONTES]
        return [
            fid
            for fid, f in FONTES.items()
            if (not self.categorias or f.categoria in self.categorias)
            and (self.escopo in ("todos", "") or f.escopo == self.escopo)
            and (self.idioma in ("todos", "") or f.idioma == self.idioma)
        ]

    def aceita(self, n: Noticia) -> bool:
        if peso(n.nivel) < peso(self.nivel_minimo):
            return False
        texto = normalizar(f"{n.titulo} {n.resumo}")
        if self.termos and not any(normalizar(t) in texto for t in self.termos if t.strip()):
            return False
        return not any(normalizar(t) in texto for t in self.excluir if t.strip())


def aplicar(noticias: list[Noticia], filtro: Filtro) -> list[Noticia]:
    """Filter and de-duplicate (the same story is often syndicated by several feeds)."""
    vistos: set[str] = set()
    saida: list[Noticia] = []
    for n in noticias:
        if n.link in vistos or not filtro.aceita(n):
            continue
        vistos.add(n.link)
        saida.append(n)
    return saida
