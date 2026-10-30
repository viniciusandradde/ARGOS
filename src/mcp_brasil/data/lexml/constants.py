"""Constants for the LexML SRU API."""

SRU_URL = "https://www.lexml.gov.br/busca/SRU"
URN_BASE_URL = "https://www.lexml.gov.br/urn/"

# Valores usados no índice `tipoDocumento`
TIPOS_DOCUMENTO = [
    "Lei",
    "Lei Complementar",
    "Decreto",
    "Decreto-Lei",
    "Medida Provisória",
    "Emenda Constitucional",
    "Resolução",
    "Portaria",
    "Instrução Normativa",
    "Projeto de Lei",
    "Acórdão",
    "Súmula",
]

DEFAULT_MAX_REGISTROS = 20
MAX_REGISTROS = 100
