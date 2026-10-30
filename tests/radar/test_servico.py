"""Tests for Radar business rules: accounts, access, billing, webhooks."""

from datetime import timedelta

import pytest

from mcp_brasil.radar.servico import ErroRadar, RadarService, ler_referencia, referencia
from mcp_brasil.radar.store import agora

from .conftest import FakeMercadoPago


def _pagamento(pid: str, uid: int, plano: str = "essencial", **extra: object) -> dict[str, object]:
    return {
        "id": pid,
        "status": "approved",
        "transaction_amount": 49.90,
        "currency_id": "BRL",
        "external_reference": referencia(uid, plano, "avulso"),
        **extra,
    }


class TestContas:
    def test_cadastro_e_login(self, servico: RadarService) -> None:
        u = servico.cadastrar("Ana@Exemplo.com", "senha-forte-1", "Ana")
        assert u.email == "ana@exemplo.com"
        usuario, sessao = servico.autenticar("ana@exemplo.com", "senha-forte-1")
        assert servico.usuario_da_sessao(sessao) == usuario

    @pytest.mark.parametrize(
        ("email", "senha"), [("invalido", "senha-forte-1"), ("a@b.com", "curta")]
    )
    def test_validacao(self, servico: RadarService, email: str, senha: str) -> None:
        with pytest.raises(ErroRadar):
            servico.cadastrar(email, senha)

    def test_email_duplicado(self, servico: RadarService) -> None:
        servico.cadastrar("a@b.com", "senha-forte-1")
        with pytest.raises(ErroRadar) as exc:
            servico.cadastrar("A@B.com", "senha-forte-1")
        assert exc.value.status == 409

    def test_bloqueio_por_tentativas(self, servico: RadarService) -> None:
        servico.cadastrar("a@b.com", "senha-forte-1")
        for _ in range(8):
            with pytest.raises(ErroRadar):
                servico.autenticar("a@b.com", "errada")
        with pytest.raises(ErroRadar) as exc:
            servico.autenticar("a@b.com", "senha-forte-1")
        assert exc.value.status == 429

    def test_conta_desativada_nao_loga(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        servico.store.atualizar_usuario(u.id, ativo=False)
        with pytest.raises(ErroRadar) as exc:
            servico.autenticar("a@b.com", "senha-forte-1")
        assert exc.value.status == 403

    def test_trial(self, servico: RadarService) -> None:
        servico.config.teste_dias = 7
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        assert servico.acesso_ativo(u)


class TestAcesso:
    def test_sem_plano_sem_acesso(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        chave = servico.criar_chave(u)["chave"]
        assert servico.usuario_por_chave(chave) is None

    def test_admin_sempre_tem_acesso(self, servico: RadarService) -> None:
        u = servico.cadastrar("adm@b.com", "senha-forte-1", papel="admin")
        chave = servico.criar_chave(u)["chave"]
        assert servico.usuario_por_chave(chave) == u
        assert servico.limite_diario(u) is None

    def test_carencia(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        servico.store.salvar_assinatura(
            u.id,
            plano="essencial",
            status="ativa",
            origem="avulso",
            periodo_fim=agora() - timedelta(days=2),
        )
        assert servico.acesso_ativo(u)  # within 3-day grace period
        servico.config.carencia_dias = 1
        assert not servico.acesso_ativo(u)

    def test_chave_revogada(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        servico.conceder(u.id, "essencial", 30)
        info = servico.criar_chave(u, "teste")
        assert servico.usuario_por_chave(info["chave"]) is not None
        assert servico.store.revogar_chave(u.id, info["id"])
        assert servico.usuario_por_chave(info["chave"]) is None

    def test_quota_diaria(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        assert servico.store.registrar_uso(u.id, 2) == 1
        assert servico.store.registrar_uso(u.id, 2) == 2
        assert servico.store.registrar_uso(u.id, 2) is None
        assert servico.store.uso_hoje(u.id) == 2


class TestCheckout:
    async def test_avulso(self, servico: RadarService, mp: FakeMercadoPago) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        url = await servico.iniciar_checkout(u, "profissional", "avulso")
        assert url == "https://mp.test/pagar"
        criada = mp.criadas[0]
        assert criada["valor"] == 149.90
        assert criada["referencia"] == f"radar:{u.id}:profissional:avulso"
        assert criada["url_notificacao"].startswith("https://radar.test/webhooks/mercadopago")

    async def test_assinatura_salva_preapproval(
        self, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        await servico.iniciar_checkout(u, "essencial", "assinatura")
        a = servico.store.assinatura(u.id)
        assert a is not None and a.mp_preapproval_id == "pre123" and a.status == "pendente"
        assert mp.criadas[0]["email_pagador"] == "a@b.com"

    async def test_plano_ou_modo_invalido(self, servico: RadarService) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        with pytest.raises(ErroRadar):
            await servico.iniciar_checkout(u, "inexistente", "avulso")
        with pytest.raises(ErroRadar):
            await servico.iniciar_checkout(u, "essencial", "pix")

    async def test_pagamentos_desativados(
        self, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        mp.configurado = False
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        with pytest.raises(ErroRadar) as exc:
            await servico.iniciar_checkout(u, "essencial", "avulso")
        assert exc.value.status == 503

    async def test_cancelar(self, servico: RadarService, mp: FakeMercadoPago) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        with pytest.raises(ErroRadar):
            await servico.cancelar_assinatura(u)
        await servico.iniciar_checkout(u, "essencial", "assinatura")
        servico.conceder(u.id, "essencial", 30)
        await servico.cancelar_assinatura(u)
        assert mp.canceladas == ["pre123"]
        assert servico.acesso_ativo(u)  # keeps paid period


class TestWebhooks:
    async def test_pagamento_aprovado_credita_uma_vez(
        self, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        mp.pagamentos["p1"] = _pagamento("p1", u.id)
        r1 = await servico.processar_notificacao("payment", "p1")
        r2 = await servico.processar_notificacao("payment", "p1")
        assert r1.startswith("creditado") and r2 == "já creditado"
        a = servico.store.assinatura(u.id)
        assert a is not None and a.periodo_fim is not None
        assert timedelta(days=29) < a.periodo_fim - agora() <= timedelta(days=30)

    async def test_pagamentos_acumulam(self, servico: RadarService, mp: FakeMercadoPago) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        mp.pagamentos["p1"] = _pagamento("p1", u.id)
        mp.pagamentos["p2"] = _pagamento("p2", u.id)
        await servico.processar_notificacao("payment", "p1")
        await servico.processar_notificacao("payment", "p2")
        a = servico.store.assinatura(u.id)
        assert a is not None and a.periodo_fim is not None
        assert a.periodo_fim - agora() > timedelta(days=59)

    async def test_valor_divergente_nao_credita(
        self, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        mp.pagamentos["p1"] = _pagamento("p1", u.id, transaction_amount=1.0)
        assert await servico.processar_notificacao("payment", "p1") == "valor divergente"
        assert not servico.acesso_ativo(u)

    async def test_pendente_e_estorno(self, servico: RadarService, mp: FakeMercadoPago) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        mp.pagamentos["p1"] = _pagamento("p1", u.id, status="pending")
        assert await servico.processar_notificacao("payment", "p1") == "status pending"
        mp.pagamentos["p1"]["status"] = "approved"
        await servico.processar_notificacao("payment", "p1")
        assert servico.acesso_ativo(u)
        mp.pagamentos["p1"]["status"] = "refunded"
        assert await servico.processar_notificacao("payment", "p1") == "estornado"
        servico.config.carencia_dias = 0
        assert not servico.acesso_ativo(u)
        assert servico.store.pagamento("p1")["status"] == "refunded"  # type: ignore[index]

    async def test_pagamento_alheio_ignorado(
        self, servico: RadarService, mp: FakeMercadoPago
    ) -> None:
        mp.pagamentos["x"] = {"id": "x", "status": "approved", "external_reference": "loja-123"}
        assert "sem referência" in await servico.processar_notificacao("payment", "x")

    async def test_assinatura_recorrente(self, servico: RadarService, mp: FakeMercadoPago) -> None:
        u = servico.cadastrar("a@b.com", "senha-forte-1")
        await servico.iniciar_checkout(u, "profissional", "assinatura")
        ref = referencia(u.id, "profissional", "assinatura")
        mp.assinaturas["pre123"] = {
            "id": "pre123",
            "status": "authorized",
            "external_reference": ref,
        }
        assert await servico.processar_notificacao("subscription_preapproval", "pre123") == (
            "assinatura ativa"
        )
        # Recurring charge: payment without external_reference, linked via preapproval
        mp.autorizados["ap1"] = {"id": "ap1", "preapproval_id": "pre123", "payment": {"id": "p9"}}
        mp.pagamentos["p9"] = {
            "id": "p9",
            "status": "approved",
            "transaction_amount": 149.90,
            "currency_id": "BRL",
        }
        resultado = await servico.processar_notificacao("subscription_authorized_payment", "ap1")
        assert resultado.startswith("creditado")
        a = servico.store.assinatura(u.id)
        assert a is not None and a.plano == "profissional" and a.status == "ativa"
        assert servico.limite_diario(u) == 2000

    async def test_tipo_desconhecido(self, servico: RadarService) -> None:
        assert (await servico.processar_notificacao("merchant_order", "1")).startswith("ignorado")


def test_referencia_roundtrip() -> None:
    assert ler_referencia(referencia(5, "essencial", "avulso")) == (5, "essencial", "avulso")
    assert ler_referencia("radar:x:y:z") is None
    assert ler_referencia(None) is None
