"""Catálogo de planos do Radar Brasil.

Os valores padrão podem ser sobrescritos pela variável de ambiente
``RADAR_PLANOS`` (JSON com a mesma estrutura de ``PLANOS_PADRAO``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Plano:
    id: str
    nome: str
    preco: float  # BRL por período
    consultas_dia: int
    dias: int = 30
    descricao: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


PLANOS_PADRAO: list[Plano] = [
    Plano(
        id="essencial",
        nome="Essencial",
        preco=49.90,
        consultas_dia=300,
        descricao="Para profissionais que acompanham poucos temas.",
    ),
    Plano(
        id="profissional",
        nome="Profissional",
        preco=149.90,
        consultas_dia=2000,
        descricao="Monitoramento diário de legislação, gastos, saúde e notícias.",
    ),
    Plano(
        id="empresarial",
        nome="Empresarial",
        preco=499.90,
        consultas_dia=20000,
        descricao="Equipes e integrações automatizadas em alto volume.",
    ),
]


def carregar_planos(raw: str | None) -> dict[str, Plano]:
    """Load plans from JSON (``RADAR_PLANOS``) or fall back to the defaults."""
    if raw:
        try:
            itens = json.loads(raw)
            planos = [Plano(**item) for item in itens]
            return {p.id: p for p in planos}
        except (ValueError, TypeError) as exc:
            logger.error("RADAR_PLANOS inválido (%s) — usando planos padrão", exc)
    return {p.id: p for p in PLANOS_PADRAO}
