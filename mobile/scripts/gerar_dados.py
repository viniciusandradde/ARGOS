"""Gera ``www/js/dados.js`` a partir das constantes do servidor (fonte única da verdade).

Assim o app Android usa exatamente as mesmas fontes RSS, critérios de criticidade,
itens do IPCA e tabela de municípios do IBGE que a versão web.

    uv run python mobile/scripts/gerar_dados.py
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp_brasil.data.alimentos.constants import ITENS, LOCALIDADES
from mcp_brasil.data.clima.local import UF_NOMES
from mcp_brasil.data.noticias import criticidade
from mcp_brasil.data.noticias.constants import FONTES
from mcp_brasil.data.vigilancia.constants import DOENCAS, TERMOS_SURTO

RAIZ = Path(__file__).resolve().parents[1]
MUNICIPIOS_JSON = (
    RAIZ.parent / "src" / "mcp_brasil" / "data" / "saude" / "geocode_municipios.json"
)


def main() -> None:
    municipios: dict[str, list[list[str]]] = {}
    for m in json.loads(MUNICIPIOS_JSON.read_text(encoding="utf-8")):
        municipios.setdefault(m["uf"], []).append([str(m["geocodigo"]), m["nome"]])
    for lista in municipios.values():
        lista.sort(key=lambda x: x[1])

    dados = {
        "FONTES": {k: f._asdict() for k, f in FONTES.items()},
        "CRITICO": criticidade._CRITICO,
        "ALTO": criticidade._ALTO,
        "TERMOS_SURTO": TERMOS_SURTO,
        "DOENCAS": list(DOENCAS),
        "ITENS_IPCA": ITENS,
        "LOCALIDADES_IPCA": {k: {"codigo": v[0], "nome": v[1]} for k, v in LOCALIDADES.items()},
        "UF_NOMES": UF_NOMES,
        "MUNICIPIOS": municipios,
    }
    corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    destino = RAIZ / "www" / "js" / "dados.js"
    destino.write_text(
        "// Gerado por mobile/scripts/gerar_dados.py — não edite à mão.\n"
        f"window.ARGOS_DADOS = {corpo};\n",
        encoding="utf-8",
    )
    print(f"{destino} ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
