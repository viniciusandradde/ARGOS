"""Classificação de criticidade de notícias por palavras-chave (PT e EN).

Simples e previsível de propósito: cada termo tem um nível, e a notícia recebe
o nível mais alto entre os termos encontrados no título ou no resumo.
"""

from __future__ import annotations

import re
import unicodedata

_CRITICO = [
    r"pandemi\w*",
    r"surtos?",
    r"outbreaks?",
    r"epidemi\w*",
    r"ebola",
    r"marburg",
    r"emergencia de saude",
    r"public health emergency",
    r"h5n1",
    r"gripe aviaria",
    r"bird flu",
    r"mpox",
    r"colera",
    r"cholera",
    r"terremotos?",
    r"earthquakes?",
    r"tsunami",
    r"enchentes?",
    r"inundac\w*",
    r"floods?",
    r"flooding",
    r"calamidade",
    r"catastrof\w*",
    r"desastres?",
    r"disasters?",
    r"evacua\w*",
    r"tragedia",
    r"colapso",
    r"collapse",
    r"guerra",
    r"war",
    r"ataque",
    r"attack",
    r"aviso de tempestade",
    r"grau: (?:grande )?perigo",
]
_ALTO = [
    r"alertas?",
    r"alerts?",
    r"avisos?",
    r"warnings?",
    r"dengue",
    r"chikungunya",
    r"zika",
    r"febre amarela",
    r"yellow fever",
    r"sarampo",
    r"measles",
    r"oropouche",
    r"virus",
    r"seca",
    r"drought",
    r"estiagem",
    r"incendios?",
    r"wildfires?",
    r"queimadas?",
    r"el nino",
    r"la nina",
    r"ciclones?",
    r"cyclones?",
    r"furac\w*",
    r"hurricanes?",
    r"tempestades?",
    r"storms?",
    r"inflac\w*",
    r"inflation",
    r"selic",
    r"juros",
    r"interest rates?",
    r"recess\w*",
    r"crises?",
    r"crisis",
    r"tarifas?",
    r"tariffs?",
    r"mortes",
    r"deaths",
    r"obitos?",
]


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def _compilar(termos: list[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(termos) + r")\b")


_RE_CRITICO = _compilar(_CRITICO)
_RE_ALTO = _compilar(_ALTO)


def classificar(texto: str) -> str:
    """Return ``critico``, ``alto`` or ``normal`` for a title/summary."""
    alvo = _norm(texto)
    if _RE_CRITICO.search(alvo):
        return "critico"
    if _RE_ALTO.search(alvo):
        return "alto"
    return "normal"


def peso(nivel: str) -> int:
    return {"normal": 0, "alto": 1, "critico": 2}.get(nivel, 0)
