"""Constants for the SICONFI API (Tesouro Nacional)."""

API_BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"

ENTES_URL = f"{API_BASE}/entes"
RREO_URL = f"{API_BASE}/rreo"
RGF_URL = f"{API_BASE}/rgf"
DCA_URL = f"{API_BASE}/dca"
EXTRATO_URL = f"{API_BASE}/extrato_entregas"

# Código IBGE da União no SICONFI
ID_UNIAO = 1

# Anexos mais usados (lista completa no Manual de Demonstrativos Fiscais)
ANEXOS_RREO = {
    "RREO-Anexo 01": "Balanço orçamentário (receitas e despesas)",
    "RREO-Anexo 02": "Despesas por função/subfunção",
    "RREO-Anexo 03": "Receita corrente líquida (RCL)",
    "RREO-Anexo 06": "Resultado primário e nominal",
    "RREO-Anexo 12": "Despesas com ações e serviços públicos de saúde",
    "RREO-Anexo 14": "Demonstrativo simplificado",
}
ANEXOS_RGF = {
    "RGF-Anexo 01": "Despesa com pessoal",
    "RGF-Anexo 02": "Dívida consolidada líquida",
    "RGF-Anexo 06": "Demonstrativo simplificado",
}

PODERES = {"E": "Executivo", "L": "Legislativo", "J": "Judiciário", "M": "Ministério Público"}

# Linhas exibidas por padrão nas respostas (a API devolve até 5000)
DEFAULT_MAX_LINHAS = 40
