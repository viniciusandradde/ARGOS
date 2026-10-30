"""Tests for passwords, API keys, sessions and webhook signatures."""

import hashlib
import hmac
import time

import pytest

from mcp_brasil.radar import seguranca
from mcp_brasil.radar.mercadopago import validar_assinatura_webhook
from mcp_brasil.radar.planos import carregar_planos


def test_senha_roundtrip() -> None:
    h = seguranca.hash_senha("senha-forte-123")
    assert seguranca.verificar_senha("senha-forte-123", h)
    assert not seguranca.verificar_senha("errada", h)
    assert not seguranca.verificar_senha("x", "lixo")


def test_chave_api() -> None:
    chave = seguranca.gerar_chave_api()
    assert chave.startswith("rb_") and len(chave) > 40
    assert seguranca.hash_chave(chave) != chave


def test_sessao_valida_e_adulterada() -> None:
    token = seguranca.criar_sessao(7, "s3gredo", horas=1)
    assert seguranca.validar_sessao(token, "s3gredo") == 7
    assert seguranca.validar_sessao(token, "outro") is None
    _uid, exp, sig = token.split(".")
    assert seguranca.validar_sessao(f"8.{exp}.{sig}", "s3gredo") is None
    assert seguranca.validar_sessao("lixo", "s3gredo") is None


def test_sessao_expirada() -> None:
    token = seguranca.criar_sessao(7, "s", horas=0)
    corpo = f"7.{int(time.time()) - 10}"
    sig = seguranca._b64(hmac.new(b"s", corpo.encode(), hashlib.sha256).digest())
    assert seguranca.validar_sessao(f"{corpo}.{sig}", "s") is None
    assert token  # created fine


def test_webhook_signature() -> None:
    segredo = "webhook-secret"
    manifesto = "id:abc123;request-id:req-1;ts:1700000000;"
    v1 = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    header = f"ts=1700000000,v1={v1}"
    assert validar_assinatura_webhook(header, "req-1", "ABC123", segredo)
    assert not validar_assinatura_webhook(header, "req-2", "ABC123", segredo)
    assert not validar_assinatura_webhook(None, "req-1", "abc123", segredo)
    assert not validar_assinatura_webhook("ts=1", "req-1", "abc123", segredo)


def test_planos_override_e_fallback() -> None:
    planos = carregar_planos('[{"id": "pro", "nome": "Pro", "preco": 10, "consultas_dia": 5}]')
    assert list(planos) == ["pro"] and planos["pro"].dias == 30
    assert "essencial" in carregar_planos("json inválido")


def test_cli_fluxo_admin(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_brasil.radar import __main__ as cli
    from mcp_brasil.radar import get_servico

    monkeypatch.setattr("mcp_brasil.settings.RADAR_DB_PATH", f"{tmp_path}/radar.db")
    monkeypatch.setattr("mcp_brasil.settings.RADAR_SECRET_KEY", "x")
    get_servico.cache_clear()
    try:
        assert cli.main(["criar-admin", "--email", "adm@b.com", "--senha", "senha-forte-1"]) == 0
        redefinir = ["redefinir-senha", "--email", "adm@b.com", "--senha"]
        assert cli.main([*redefinir, "outra-senha-9"]) == 0
        assert cli.main([*redefinir, "curta"]) == 1
        assert cli.main(["conceder", "--email", "nao@existe.com", "--plano", "essencial"]) == 1
        assert cli.main(["usuarios"]) == 0
        servico = get_servico()
        servico.autenticar("adm@b.com", "outra-senha-9")
    finally:
        get_servico.cache_clear()
