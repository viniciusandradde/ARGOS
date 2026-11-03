"""Persistência do Radar Brasil em SQLite.

Tabelas: usuarios, chaves (API keys), assinaturas, pagamentos e uso diário.
SQLite atende bem uma instância única; para múltiplas réplicas, troque
esta classe por uma implementação em PostgreSQL com a mesma interface.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL DEFAULT '',
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'cliente',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    nome TEXT NOT NULL DEFAULT '',
    prefixo TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    criado_em TEXT NOT NULL,
    ultimo_uso TEXT,
    revogada_em TEXT
);
CREATE TABLE IF NOT EXISTS assinaturas (
    usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id),
    plano TEXT NOT NULL,
    status TEXT NOT NULL,
    origem TEXT NOT NULL,
    periodo_fim TEXT,
    mp_preapproval_id TEXT,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pagamentos (
    mp_payment_id TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    plano TEXT NOT NULL,
    status TEXT NOT NULL,
    valor REAL NOT NULL,
    creditado INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS temas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    nome TEXT NOT NULL,
    config TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferencias_alerta (
    usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id),
    telegram_chat_id TEXT,
    telegram_codigo TEXT,
    whatsapp_numero TEXT,
    whatsapp_verificado INTEGER NOT NULL DEFAULT 0,
    whatsapp_codigo TEXT,
    tipos TEXT NOT NULL DEFAULT '{}',
    ativo_desde TEXT,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas_enviados (
    usuario_id INTEGER NOT NULL,
    chave TEXT NOT NULL,
    enviado_em TEXT NOT NULL,
    PRIMARY KEY (usuario_id, chave)
);
CREATE TABLE IF NOT EXISTS estado (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uso (
    usuario_id INTEGER NOT NULL,
    dia TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (usuario_id, dia)
);
"""


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


@dataclass
class Usuario:
    id: int
    email: str
    nome: str
    senha_hash: str
    papel: str
    ativo: bool
    criado_em: str

    @property
    def admin(self) -> bool:
        return self.papel == "admin"

    def publico(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "nome": self.nome,
            "papel": self.papel,
            "ativo": self.ativo,
            "criado_em": self.criado_em,
        }


@dataclass
class Assinatura:
    usuario_id: int
    plano: str
    status: str
    origem: str
    periodo_fim: datetime | None
    mp_preapproval_id: str | None

    def publico(self) -> dict[str, Any]:
        return {
            "plano": self.plano,
            "status": self.status,
            "origem": self.origem,
            "periodo_fim": _iso(self.periodo_fim),
            "mp_preapproval_id": self.mp_preapproval_id,
        }


class EmailJaCadastrado(ValueError):
    pass


class Store:
    """Thread-safe SQLite repository."""

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(_SCHEMA)

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
            return row

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    # --- Usuários ---------------------------------------------------------

    def criar_usuario(
        self, email: str, senha_hash: str, nome: str = "", papel: str = "cliente"
    ) -> Usuario:
        try:
            cur = self._exec(
                "INSERT INTO usuarios (email, nome, senha_hash, papel, criado_em) "
                "VALUES (?, ?, ?, ?, ?)",
                (email.strip().lower(), nome.strip(), senha_hash, papel, _iso(agora())),
            )
        except sqlite3.IntegrityError as exc:
            raise EmailJaCadastrado(email) from exc
        usuario = self.usuario_por_id(int(cur.lastrowid or 0))
        assert usuario is not None
        return usuario

    @staticmethod
    def _usuario(row: sqlite3.Row | None) -> Usuario | None:
        if row is None:
            return None
        return Usuario(
            id=row["id"],
            email=row["email"],
            nome=row["nome"],
            senha_hash=row["senha_hash"],
            papel=row["papel"],
            ativo=bool(row["ativo"]),
            criado_em=row["criado_em"],
        )

    def usuario_por_id(self, usuario_id: int) -> Usuario | None:
        return self._usuario(self._one("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)))

    def usuario_por_email(self, email: str) -> Usuario | None:
        return self._usuario(
            self._one("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),))
        )

    def listar_usuarios(self) -> list[Usuario]:
        rows = self._all("SELECT * FROM usuarios ORDER BY id")
        return [u for u in (self._usuario(r) for r in rows) if u]

    def atualizar_usuario(
        self,
        usuario_id: int,
        *,
        ativo: bool | None = None,
        papel: str | None = None,
        senha_hash: str | None = None,
    ) -> None:
        if ativo is not None:
            self._exec("UPDATE usuarios SET ativo = ? WHERE id = ?", (int(ativo), usuario_id))
        if papel is not None:
            self._exec("UPDATE usuarios SET papel = ? WHERE id = ?", (papel, usuario_id))
        if senha_hash is not None:
            self._exec("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (senha_hash, usuario_id))

    # --- Chaves de API ----------------------------------------------------

    def criar_chave(self, usuario_id: int, chave_hash: str, prefixo: str, nome: str) -> int:
        cur = self._exec(
            "INSERT INTO chaves (usuario_id, nome, prefixo, hash, criado_em) VALUES (?,?,?,?,?)",
            (usuario_id, nome, prefixo, chave_hash, _iso(agora())),
        )
        return int(cur.lastrowid or 0)

    def listar_chaves(self, usuario_id: int) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, nome, prefixo, criado_em, ultimo_uso FROM chaves "
            "WHERE usuario_id = ? AND revogada_em IS NULL ORDER BY id",
            (usuario_id,),
        )
        return [dict(r) for r in rows]

    def revogar_chave(self, usuario_id: int, chave_id: int) -> bool:
        cur = self._exec(
            "UPDATE chaves SET revogada_em = ? WHERE id = ? AND usuario_id = ? "
            "AND revogada_em IS NULL",
            (_iso(agora()), chave_id, usuario_id),
        )
        return cur.rowcount > 0

    def usuario_por_chave(self, chave_hash: str) -> Usuario | None:
        row = self._one(
            "SELECT u.* FROM chaves c JOIN usuarios u ON u.id = c.usuario_id "
            "WHERE c.hash = ? AND c.revogada_em IS NULL",
            (chave_hash,),
        )
        if row is not None:
            self._exec(
                "UPDATE chaves SET ultimo_uso = ? WHERE hash = ?", (_iso(agora()), chave_hash)
            )
        return self._usuario(row)

    # --- Assinaturas ------------------------------------------------------

    def assinatura(self, usuario_id: int) -> Assinatura | None:
        row = self._one("SELECT * FROM assinaturas WHERE usuario_id = ?", (usuario_id,))
        if row is None:
            return None
        return Assinatura(
            usuario_id=row["usuario_id"],
            plano=row["plano"],
            status=row["status"],
            origem=row["origem"],
            periodo_fim=_dt(row["periodo_fim"]),
            mp_preapproval_id=row["mp_preapproval_id"],
        )

    def salvar_assinatura(
        self,
        usuario_id: int,
        *,
        plano: str,
        status: str,
        origem: str,
        periodo_fim: datetime | None = None,
        mp_preapproval_id: str | None = None,
    ) -> None:
        atual = self.assinatura(usuario_id)
        fim = periodo_fim if periodo_fim is not None else (atual.periodo_fim if atual else None)
        pre = mp_preapproval_id or (atual.mp_preapproval_id if atual else None)
        self._exec(
            "INSERT INTO assinaturas (usuario_id, plano, status, origem, periodo_fim, "
            "mp_preapproval_id, atualizado_em) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(usuario_id) DO UPDATE SET plano=excluded.plano, "
            "status=excluded.status, origem=excluded.origem, periodo_fim=excluded.periodo_fim, "
            "mp_preapproval_id=excluded.mp_preapproval_id, atualizado_em=excluded.atualizado_em",
            (usuario_id, plano, status, origem, _iso(fim), pre, _iso(agora())),
        )

    def estender_periodo(self, usuario_id: int, plano: str, dias: int, origem: str) -> datetime:
        """Add ``dias`` to the access period, starting from now if it already expired."""
        atual = self.assinatura(usuario_id)
        base = agora()
        if atual and atual.periodo_fim and atual.periodo_fim > base:
            base = atual.periodo_fim
        fim = base + timedelta(days=dias)
        self.salvar_assinatura(
            usuario_id, plano=plano, status="ativa", origem=origem, periodo_fim=fim
        )
        return fim

    def reduzir_periodo(self, usuario_id: int, dias: int) -> None:
        """Remove ``dias`` from the access period (refunds/chargebacks)."""
        atual = self.assinatura(usuario_id)
        if atual is None or atual.periodo_fim is None:
            return
        fim = atual.periodo_fim - timedelta(days=dias)
        self.salvar_assinatura(
            usuario_id,
            plano=atual.plano,
            status="ativa" if fim > agora() else "expirada",
            origem=atual.origem,
            periodo_fim=fim,
        )

    def assinatura_por_preapproval(self, preapproval_id: str) -> Assinatura | None:
        row = self._one(
            "SELECT usuario_id FROM assinaturas WHERE mp_preapproval_id = ?", (preapproval_id,)
        )
        return self.assinatura(int(row["usuario_id"])) if row else None

    # --- Pagamentos -------------------------------------------------------

    def pagamento(self, mp_payment_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM pagamentos WHERE mp_payment_id = ?", (mp_payment_id,))
        return dict(row) if row else None

    def registrar_pagamento(
        self, mp_payment_id: str, usuario_id: int, plano: str, status: str, valor: float
    ) -> None:
        ts = _iso(agora())
        self._exec(
            "INSERT INTO pagamentos (mp_payment_id, usuario_id, plano, status, valor, "
            "criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(mp_payment_id) DO UPDATE SET status=excluded.status, "
            "atualizado_em=excluded.atualizado_em",
            (mp_payment_id, usuario_id, plano, status, valor, ts, ts),
        )

    def marcar_creditado(self, mp_payment_id: str, creditado: bool) -> bool:
        """Atomically flip the credited flag. Returns False if it was already in that state."""
        cur = self._exec(
            "UPDATE pagamentos SET creditado = ? WHERE mp_payment_id = ? AND creditado = ?",
            (int(creditado), mp_payment_id, int(not creditado)),
        )
        return cur.rowcount > 0

    def listar_pagamentos(self, usuario_id: int | None = None) -> list[dict[str, Any]]:
        if usuario_id is None:
            rows = self._all("SELECT * FROM pagamentos ORDER BY criado_em DESC LIMIT 500")
        else:
            rows = self._all(
                "SELECT * FROM pagamentos WHERE usuario_id = ? ORDER BY criado_em DESC",
                (usuario_id,),
            )
        return [dict(r) for r in rows]

    # --- Temas (filtros de notícias configurados pelo usuário) -------------

    def criar_tema(self, usuario_id: int, nome: str, config: dict[str, Any]) -> int:
        cur = self._exec(
            "INSERT INTO temas (usuario_id, nome, config, criado_em) VALUES (?,?,?,?)",
            (usuario_id, nome, json.dumps(config, ensure_ascii=False), _iso(agora())),
        )
        return int(cur.lastrowid or 0)

    def listar_temas(self, usuario_id: int) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, nome, config FROM temas WHERE usuario_id = ? ORDER BY id", (usuario_id,)
        )
        return [{"id": r["id"], "nome": r["nome"], **json.loads(r["config"])} for r in rows]

    def remover_tema(self, usuario_id: int, tema_id: int) -> bool:
        cur = self._exec(
            "DELETE FROM temas WHERE id = ? AND usuario_id = ?", (tema_id, usuario_id)
        )
        return cur.rowcount > 0

    # --- Alertas (Telegram / WhatsApp) -----------------------------------

    _CAMPOS_PREFS = (
        "telegram_chat_id",
        "telegram_codigo",
        "whatsapp_numero",
        "whatsapp_verificado",
        "whatsapp_codigo",
        "tipos",
        "ativo_desde",
    )

    @staticmethod
    def _prefs(row: sqlite3.Row | None, usuario_id: int) -> dict[str, Any]:
        if row is None:
            return {"usuario_id": usuario_id, "tipos": {}, "whatsapp_verificado": False}
        dados = dict(row)
        dados["tipos"] = json.loads(dados.get("tipos") or "{}")
        dados["whatsapp_verificado"] = bool(dados.get("whatsapp_verificado"))
        return dados

    def preferencias_alerta(self, usuario_id: int) -> dict[str, Any]:
        row = self._one("SELECT * FROM preferencias_alerta WHERE usuario_id = ?", (usuario_id,))
        return self._prefs(row, usuario_id)

    def salvar_preferencias(self, usuario_id: int, **campos: Any) -> None:
        invalidos = set(campos) - set(self._CAMPOS_PREFS)
        if invalidos:
            raise ValueError(f"Campos inválidos: {invalidos}")
        if "tipos" in campos:
            campos["tipos"] = json.dumps(campos["tipos"])
        if "whatsapp_verificado" in campos:
            campos["whatsapp_verificado"] = int(bool(campos["whatsapp_verificado"]))
        self._exec(
            "INSERT OR IGNORE INTO preferencias_alerta (usuario_id, atualizado_em) VALUES (?, ?)",
            (usuario_id, _iso(agora())),
        )
        if campos:
            sets = ", ".join(f"{k} = ?" for k in campos)
            self._exec(
                f"UPDATE preferencias_alerta SET {sets}, atualizado_em = ? WHERE usuario_id = ?",
                (*campos.values(), _iso(agora()), usuario_id),
            )

    def listar_preferencias_alerta(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM preferencias_alerta")
        return [self._prefs(r, int(r["usuario_id"])) for r in rows]

    def vincular_telegram(self, codigo: str, chat_id: str) -> int | None:
        row = self._one(
            "SELECT usuario_id FROM preferencias_alerta WHERE telegram_codigo = ?", (codigo,)
        )
        if row is None:
            return None
        usuario_id = int(row["usuario_id"])
        self.salvar_preferencias(
            usuario_id, telegram_chat_id=chat_id, telegram_codigo=None, ativo_desde=_iso(agora())
        )
        return usuario_id

    def alerta_enviado(self, usuario_id: int, chave: str) -> bool:
        row = self._one(
            "SELECT 1 FROM alertas_enviados WHERE usuario_id = ? AND chave = ?",
            (usuario_id, chave),
        )
        return row is not None

    def marcar_alertas(self, usuario_id: int, chaves: list[str]) -> None:
        ts = _iso(agora())
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO alertas_enviados (usuario_id, chave, enviado_em) "
                "VALUES (?, ?, ?)",
                [(usuario_id, c, ts) for c in chaves],
            )
            limite = _iso(agora() - timedelta(days=60))
            self._conn.execute("DELETE FROM alertas_enviados WHERE enviado_em < ?", (limite,))

    def estado(self, chave: str) -> str | None:
        row = self._one("SELECT valor FROM estado WHERE chave = ?", (chave,))
        return str(row["valor"]) if row else None

    def salvar_estado(self, chave: str, valor: str) -> None:
        self._exec(
            "INSERT INTO estado (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )

    # --- Uso diário -------------------------------------------------------

    def registrar_uso(self, usuario_id: int, limite: int) -> int | None:
        """Increment today's counter if under ``limite``. Returns the new total or None."""
        dia = agora().date().isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO uso (usuario_id, dia, total) VALUES (?, ?, 0)",
                (usuario_id, dia),
            )
            cur = self._conn.execute(
                "UPDATE uso SET total = total + 1 WHERE usuario_id = ? AND dia = ? AND total < ?",
                (usuario_id, dia, limite),
            )
            if cur.rowcount == 0:
                return None
            row = self._conn.execute(
                "SELECT total FROM uso WHERE usuario_id = ? AND dia = ?", (usuario_id, dia)
            ).fetchone()
            return int(row["total"])

    def uso_hoje(self, usuario_id: int) -> int:
        row = self._one(
            "SELECT total FROM uso WHERE usuario_id = ? AND dia = ?",
            (usuario_id, agora().date().isoformat()),
        )
        return int(row["total"]) if row else 0
