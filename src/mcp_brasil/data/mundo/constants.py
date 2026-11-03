"""Constants for the Mundo feature."""

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{pais}/indicator/{indicador}"

INDICADORES: dict[str, tuple[str, str]] = {
    "pib": ("NY.GDP.MKTP.CD", "PIB (US$ correntes)"),
    "pib_crescimento": ("NY.GDP.MKTP.KD.ZG", "Crescimento do PIB (% ao ano)"),
    "pib_per_capita": ("NY.GDP.PCAP.CD", "PIB per capita (US$)"),
    "inflacao": ("FP.CPI.TOTL.ZG", "Inflação, preços ao consumidor (% ao ano)"),
    "desemprego": ("SL.UEM.TOTL.ZS", "Desemprego (% da força de trabalho)"),
    "gasto_saude": ("SH.XPD.CHEX.GD.ZS", "Gasto corrente em saúde (% do PIB)"),
    "expectativa_vida": ("SP.DYN.LE00.IN", "Expectativa de vida ao nascer (anos)"),
    "populacao": ("SP.POP.TOTL", "População total"),
    "divida_publica": ("GC.DOD.TOTL.GD.ZS", "Dívida do governo central (% do PIB)"),
}
