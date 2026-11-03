"""Banco de indicadores do sistema (SQLite separado do banco de usuários).

Alimentado pelo coletor e lido pela sala de situação e pelo Metabase. Fica
separado de ``store.py`` de propósito: o Metabase recebe acesso só a dados
públicos, nunca a usuários, chaves ou pagamentos.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS noticias (
    link TEXT PRIMARY KEY,
    fonte TEXT NOT NULL,
    fonte_nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    escopo TEXT NOT NULL,
    idioma TEXT NOT NULL,
    titulo TEXT NOT NULL,
    resumo TEXT NOT NULL DEFAULT '',
    nivel TEXT NOT NULL,
    publicado_em TEXT,
    coletado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_noticias_pub ON noticias (publicado_em DESC);
CREATE TABLE IF NOT EXISTS arboviroses (
    geocodigo TEXT NOT NULL,
    municipio TEXT NOT NULL,
    doenca TEXT NOT NULL,
    semana INTEGER NOT NULL,
    nivel INTEGER,
    casos_semana INTEGER,
    casos_ano INTEGER,
    incidencia_100k REAL,
    rt REAL,
    coletado_em TEXT NOT NULL,
    PRIMARY KEY (geocodigo, doenca, semana)
);
CREATE TABLE IF NOT EXISTS alimentos_ipca (
    localidade TEXT NOT NULL,
    item_codigo TEXT NOT NULL,
    item TEXT NOT NULL,
    mes_codigo TEXT NOT NULL,
    mes TEXT NOT NULL,
    variacao_mes REAL,
    variacao_12m REAL,
    PRIMARY KEY (localidade, item_codigo, mes_codigo)
);
CREATE TABLE IF NOT EXISTS cambio (
    data TEXT NOT NULL,
    base TEXT NOT NULL,
    moeda TEXT NOT NULL,
    valor REAL NOT NULL,
    PRIMARY KEY (data, base, moeda)
);
CREATE TABLE IF NOT EXISTS enso_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    alerta TEXT,
    fase TEXT,
    sinopse TEXT,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS enso_oni (
    ano INTEGER NOT NULL,
    trimestre TEXT NOT NULL,
    oni REAL,
    roni REAL,
    PRIMARY KEY (ano, trimestre)
);
CREATE TABLE IF NOT EXISTS enso_semanal (
    semana TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    nino12 REAL, nino3 REAL, nino34 REAL, nino4 REAL
);
CREATE TABLE IF NOT EXISTS clima_atual (
    cidade TEXT PRIMARY KEY,
    temperatura REAL, umidade REAL, vento REAL, codigo INTEGER, aqi REAL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clima_previsao (
    cidade TEXT NOT NULL,
    data TEXT NOT NULL,
    tmin REAL, tmax REAL, chuva_mm REAL, prob_chuva REAL, codigo INTEGER,
    PRIMARY KEY (cidade, data)
);
CREATE TABLE IF NOT EXISTS avisos_inmet (
    link TEXT PRIMARY KEY,
    evento TEXT, severidade TEXT, inicio TEXT, fim TEXT, area TEXT, descricao TEXT
);
CREATE TABLE IF NOT EXISTS terremotos (
    link TEXT PRIMARY KEY,
    magnitude REAL, local TEXT, quando TEXT, tsunami INTEGER
);
CREATE TABLE IF NOT EXISTS precos_mercado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto TEXT NOT NULL,
    mercado TEXT NOT NULL,
    cidade TEXT NOT NULL,
    preco REAL NOT NULL,
    unidade TEXT NOT NULL DEFAULT 'un',
    data TEXT NOT NULL,
    usuario_id INTEGER,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etapa TEXT NOT NULL,
    ok INTEGER NOT NULL,
    mensagem TEXT NOT NULL DEFAULT '',
    quando TEXT NOT NULL
);
"""


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Indicadores:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Default rollback journal (not WAL) so Metabase can read the file from another container
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def executar_varios(self, sql: str, linhas: list[tuple[Any, ...]]) -> None:
        if not linhas:
            return
        with self._lock, self._conn:
            self._conn.executemany(sql, linhas)

    def executar(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def consultar(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def registrar_coleta(self, etapa: str, ok: bool, mensagem: str = "") -> None:
        self.executar(
            "INSERT INTO coletas (etapa, ok, mensagem, quando) VALUES (?,?,?,?)",
            (etapa, int(ok), mensagem[:500], agora_iso()),
        )
        # Keep the log small
        self.executar("DELETE FROM coletas WHERE id < (SELECT MAX(id) - 2000 FROM coletas)")

    # --- Pesquisa de preços (cadastro manual) --------------------------------

    def adicionar_preco(
        self,
        *,
        produto: str,
        mercado: str,
        cidade: str,
        preco: float,
        unidade: str,
        data: str,
        usuario_id: int | None,
    ) -> int:
        cur = self.executar(
            "INSERT INTO precos_mercado (produto, mercado, cidade, preco, unidade, data, "
            "usuario_id, criado_em) VALUES (?,?,?,?,?,?,?,?)",
            (produto, mercado, cidade, preco, unidade, data, usuario_id, agora_iso()),
        )
        return int(cur.lastrowid or 0)

    def remover_preco(self, preco_id: int, usuario_id: int | None = None) -> bool:
        if usuario_id is None:
            cur = self.executar("DELETE FROM precos_mercado WHERE id = ?", (preco_id,))
        else:
            cur = self.executar(
                "DELETE FROM precos_mercado WHERE id = ? AND usuario_id = ?",
                (preco_id, usuario_id),
            )
        return cur.rowcount > 0

    def medias_precos(self, cidade: str | None = None, dias: int = 30) -> list[dict[str, Any]]:
        """Average, min and max price per product/city over the last ``dias`` days."""
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).date().isoformat()
        sql = (
            "SELECT produto, cidade, unidade, ROUND(AVG(preco), 2) AS media, "
            "MIN(preco) AS minimo, MAX(preco) AS maximo, COUNT(*) AS amostras, "
            "COUNT(DISTINCT mercado) AS mercados, "
            "MAX(data) AS ultima FROM precos_mercado WHERE data >= ?"
        )
        params: list[Any] = [desde]
        if cidade:
            sql += " AND cidade = ?"
            params.append(cidade)
        sql += " GROUP BY produto, cidade, unidade ORDER BY cidade, produto"
        return self.consultar(sql, tuple(params))

    def listar_precos(self, cidade: str | None = None, limite: int = 100) -> list[dict[str, Any]]:
        if cidade:
            return self.consultar(
                "SELECT * FROM precos_mercado WHERE cidade = ? "
                "ORDER BY data DESC, id DESC LIMIT ?",
                (cidade, limite),
            )
        return self.consultar(
            "SELECT * FROM precos_mercado ORDER BY data DESC, id DESC LIMIT ?", (limite,)
        )
