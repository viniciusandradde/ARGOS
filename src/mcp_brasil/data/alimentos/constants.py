"""Constants for the Alimentos feature (IPCA table 7060 at SIDRA/IBGE)."""

SIDRA_URL = (
    "https://apisidra.ibge.gov.br/values/t/7060/{local}/v/63,2265/p/last%20{meses}/c315/{itens}"
)

VAR_MENSAL = "63"
VAR_12_MESES = "2265"

# Subitens/grupos do IPCA (classificação 315) — principais itens da mesa
ITENS: dict[str, str] = {
    "7170": "Alimentação e bebidas",
    "7171": "Alimentação no domicílio",
    "7173": "Arroz",
    "7176": "Feijão preto",
    "7202": "Batata-inglesa",
    "7212": "Tomate",
    "7215": "Cebola",
    "7260": "Banana-prata",
    "7283": "Carnes",
    "7291": "Contrafilé",
    "7300": "Acém",
    "7349": "Aves e ovos",
    "7355": "Ovo de galinha",
    "7356": "Leites e derivados",
    "7375": "Pão francês",
    "7385": "Óleo de soja",
    "7392": "Café moído",
    "7220": "Açúcar refinado",
    "7195": "Farinha de mandioca",
}

# Localidades pesquisadas pelo IPCA (n1 = Brasil, n6 = município)
LOCALIDADES: dict[str, tuple[str, str]] = {
    "brasil": ("n1/all", "Brasil"),
    "campo_grande": ("n6/5002704", "Campo Grande (MS)"),
    "sao_paulo": ("n6/3550308", "São Paulo (SP)"),
    "rio_de_janeiro": ("n6/3304557", "Rio de Janeiro (RJ)"),
    "belo_horizonte": ("n6/3106200", "Belo Horizonte (MG)"),
    "curitiba": ("n6/4106902", "Curitiba (PR)"),
    "porto_alegre": ("n6/4314902", "Porto Alegre (RS)"),
    "goiania": ("n6/5208707", "Goiânia (GO)"),
    "brasilia": ("n6/5300108", "Brasília (DF)"),
    "salvador": ("n6/2927408", "Salvador (BA)"),
    "recife": ("n6/2611606", "Recife (PE)"),
    "fortaleza": ("n6/2304400", "Fortaleza (CE)"),
    "belem": ("n6/1501402", "Belém (PA)"),
    "vitoria": ("n6/3205309", "Vitória (ES)"),
    "sao_luis": ("n6/2111300", "São Luís (MA)"),
    "aracaju": ("n6/2800308", "Aracaju (SE)"),
    "rio_branco": ("n6/1200401", "Rio Branco (AC)"),
}
