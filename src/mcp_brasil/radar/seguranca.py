"""Senhas, chaves de API e tokens de sessão (somente stdlib)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1

PREFIXO_CHAVE = "rb_"


def hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        senha.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        _, n, r, p, salt_hex, hash_hex = armazenado.split("$")
        digest = hashlib.scrypt(
            senha.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(hash_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def gerar_chave_api() -> str:
    """Return a new API key. Only its SHA-256 is stored."""
    return PREFIXO_CHAVE + secrets.token_urlsafe(32)


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def criar_sessao(usuario_id: int, segredo: str, horas: int) -> str:
    """Create a signed session token: ``<uid>.<expira>.<assinatura>``."""
    expira = int(time.time()) + horas * 3600
    corpo = f"{usuario_id}.{expira}"
    assinatura = hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).digest()
    return f"{corpo}.{_b64(assinatura)}"


def validar_sessao(token: str, segredo: str) -> int | None:
    """Return the user id for a valid, unexpired session token."""
    try:
        uid, expira, assinatura = token.split(".")
        corpo = f"{uid}.{expira}"
        esperado = _b64(hmac.new(segredo.encode(), corpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(esperado, assinatura) or int(expira) < time.time():
            return None
        return int(uid)
    except ValueError:
        return None
