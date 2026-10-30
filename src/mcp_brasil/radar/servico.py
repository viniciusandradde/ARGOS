"""Regras de negócio do Radar Brasil: contas, acesso, cobrança e webhooks."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from . import seguranca
from .mercadopago import MercadoPagoClient
from .planos import Plano
from .store import Assinatura, Store, Usuario, agora

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_STATUS_PREAPPROVAL = {
    "authorized": "ativa",
    "paused": "pausada",
    "cancelled": "cancelada",
    "pending": "pendente",
}
_STATUS_ESTORNO = {"refunded", "charged_back", "cancelled"}

MAX_FALHAS_LOGIN = 8
BLOQUEIO_LOGIN_SEG = 15 * 60


class ErroRadar(ValueError):
    """Erro de regra de negócio, com mensagem exibível ao usuário."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.status = status


@dataclass
class RadarConfig:
    db_path: str
    segredo: str
    base_url: str = ""
    mp_access_token: str = ""
    mp_webhook_secret: str = ""
    planos: dict[str, Plano] = field(default_factory=dict)
    carencia_dias: int = 3
    sessao_horas: int = 72
    teste_dias: int = 0
    plano_teste: str = "essencial"


def referencia(usuario_id: int, plano_id: str, modo: str) -> str:
    return f"radar:{usuario_id}:{plano_id}:{modo}"


def ler_referencia(ref: str | None) -> tuple[int, str, str] | None:
    if not ref:
        return None
    partes = ref.split(":")
    if len(partes) != 4 or partes[0] != "radar" or not partes[1].isdigit():
        return None
    return int(partes[1]), partes[2], partes[3]


class RadarService:
    def __init__(
        self, config: RadarConfig, store: Store, mp: MercadoPagoClient | None = None
    ) -> None:
        self.config = config
        self.store = store
        self.mp = mp or MercadoPagoClient(config.mp_access_token)
        self._falhas_login: dict[str, tuple[int, float]] = {}

    # --- Contas -----------------------------------------------------------

    def cadastrar(self, email: str, senha: str, nome: str = "", papel: str = "cliente") -> Usuario:
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ErroRadar("E-mail inválido.")
        if len(senha) < 8:
            raise ErroRadar("A senha precisa ter pelo menos 8 caracteres.")
        if self.store.usuario_por_email(email):
            raise ErroRadar("Este e-mail já está cadastrado.", 409)
        usuario = self.store.criar_usuario(email, seguranca.hash_senha(senha), nome, papel)
        if self.config.teste_dias > 0 and self.config.plano_teste in self.config.planos:
            self.store.estender_periodo(
                usuario.id, self.config.plano_teste, self.config.teste_dias, "teste"
            )
        return usuario

    def autenticar(self, email: str, senha: str) -> tuple[Usuario, str]:
        email = email.strip().lower()
        falhas, bloqueado_ate = self._falhas_login.get(email, (0, 0.0))
        if bloqueado_ate > time.time():
            raise ErroRadar("Muitas tentativas. Tente novamente em alguns minutos.", 429)
        usuario = self.store.usuario_por_email(email)
        if not usuario or not seguranca.verificar_senha(senha, usuario.senha_hash):
            falhas += 1
            bloqueio = time.time() + BLOQUEIO_LOGIN_SEG if falhas >= MAX_FALHAS_LOGIN else 0.0
            self._falhas_login[email] = (0 if bloqueio else falhas, bloqueio)
            raise ErroRadar("E-mail ou senha incorretos.", 401)
        if not usuario.ativo:
            raise ErroRadar("Conta desativada. Fale com o suporte.", 403)
        self._falhas_login.pop(email, None)
        sessao = seguranca.criar_sessao(usuario.id, self.config.segredo, self.config.sessao_horas)
        return usuario, sessao

    def usuario_da_sessao(self, token: str | None) -> Usuario | None:
        if not token:
            return None
        uid = seguranca.validar_sessao(token, self.config.segredo)
        usuario = self.store.usuario_por_id(uid) if uid is not None else None
        return usuario if usuario and usuario.ativo else None

    def trocar_senha(self, usuario: Usuario, atual: str, nova: str) -> None:
        if not seguranca.verificar_senha(atual, usuario.senha_hash):
            raise ErroRadar("Senha atual incorreta.", 401)
        if len(nova) < 8:
            raise ErroRadar("A nova senha precisa ter pelo menos 8 caracteres.")
        self.store.atualizar_usuario(usuario.id, senha_hash=seguranca.hash_senha(nova))

    def criar_chave(self, usuario: Usuario, nome: str = "") -> dict[str, Any]:
        chave = seguranca.gerar_chave_api()
        prefixo = chave[:10]
        chave_id = self.store.criar_chave(usuario.id, seguranca.hash_chave(chave), prefixo, nome)
        return {"id": chave_id, "nome": nome, "prefixo": prefixo, "chave": chave}

    # --- Acesso -----------------------------------------------------------

    def plano(self, plano_id: str) -> Plano:
        plano = self.config.planos.get(plano_id)
        if plano is None:
            raise ErroRadar(f"Plano '{plano_id}' não existe.")
        return plano

    def acesso_ativo(self, usuario: Usuario, assinatura: Assinatura | None = None) -> bool:
        if not usuario.ativo:
            return False
        if usuario.admin:
            return True
        assinatura = assinatura or self.store.assinatura(usuario.id)
        if assinatura is None or assinatura.periodo_fim is None:
            return False
        limite = assinatura.periodo_fim + timedelta(days=self.config.carencia_dias)
        return limite > agora()

    def limite_diario(self, usuario: Usuario) -> int | None:
        """Daily call quota for the user (None = unlimited)."""
        if usuario.admin:
            return None
        assinatura = self.store.assinatura(usuario.id)
        plano = self.config.planos.get(assinatura.plano) if assinatura else None
        return plano.consultas_dia if plano else 0

    def usuario_por_chave(self, chave: str) -> Usuario | None:
        usuario = self.store.usuario_por_chave(seguranca.hash_chave(chave))
        if usuario is None or not self.acesso_ativo(usuario):
            return None
        return usuario

    def resumo(self, usuario: Usuario) -> dict[str, Any]:
        assinatura = self.store.assinatura(usuario.id)
        return {
            "usuario": usuario.publico(),
            "assinatura": assinatura.publico() if assinatura else None,
            "acesso_ativo": self.acesso_ativo(usuario, assinatura),
            "uso_hoje": self.store.uso_hoje(usuario.id),
            "limite_diario": self.limite_diario(usuario),
            "chaves": self.store.listar_chaves(usuario.id),
            "pagamentos": self.store.listar_pagamentos(usuario.id)[:20],
            "mcp_url": f"{self.config.base_url.rstrip('/')}/mcp"
            if self.config.base_url
            else "/mcp",
        }

    # --- Cobrança ---------------------------------------------------------

    def _url(self, caminho: str, base_url: str | None = None) -> str:
        return f"{(base_url or self.config.base_url).rstrip('/')}{caminho}"

    async def iniciar_checkout(
        self, usuario: Usuario, plano_id: str, modo: str, base_url: str | None = None
    ) -> str:
        """Create a Mercado Pago checkout and return the URL the user must open."""
        plano = self.plano(plano_id)
        if not self.mp.configurado:
            raise ErroRadar("Pagamentos ainda não configurados neste servidor.", 503)
        ref = referencia(usuario.id, plano.id, modo)
        if modo == "assinatura":
            resp = await self.mp.criar_assinatura(
                motivo=f"Radar Brasil — plano {plano.nome}",
                email_pagador=usuario.email,
                valor=plano.preco,
                referencia=ref,
                back_url=self._url("/conta?retorno=assinatura", base_url),
            )
            atual = self.store.assinatura(usuario.id)
            self.store.salvar_assinatura(
                usuario.id,
                plano=atual.plano if atual and self.acesso_ativo(usuario, atual) else plano.id,
                status=atual.status if atual and self.acesso_ativo(usuario, atual) else "pendente",
                origem="assinatura",
                mp_preapproval_id=str(resp.get("id", "")),
            )
        elif modo == "avulso":
            resp = await self.mp.criar_preferencia(
                titulo=f"Radar Brasil — {plano.nome} ({plano.dias} dias)",
                valor=plano.preco,
                email_pagador=usuario.email,
                referencia=ref,
                url_retorno=self._url("/conta?retorno=pagamento", base_url),
                url_notificacao=self._url("/webhooks/mercadopago?source_news=webhooks", base_url),
            )
        else:
            raise ErroRadar("Modo inválido. Use 'assinatura' ou 'avulso'.")
        url = resp.get("init_point")
        if not url:
            raise ErroRadar("Mercado Pago não retornou o link de pagamento.", 502)
        return str(url)

    async def cancelar_assinatura(self, usuario: Usuario) -> None:
        assinatura = self.store.assinatura(usuario.id)
        if not assinatura or not assinatura.mp_preapproval_id:
            raise ErroRadar("Você não tem assinatura recorrente ativa.")
        await self.mp.cancelar_assinatura(assinatura.mp_preapproval_id)
        # Access remains valid until the end of the period already paid
        self.store.salvar_assinatura(
            usuario.id, plano=assinatura.plano, status="cancelada", origem=assinatura.origem
        )

    def conceder(self, usuario_id: int, plano_id: str, dias: int) -> datetime:
        """Grant access manually (admin)."""
        self.plano(plano_id)
        return self.store.estender_periodo(usuario_id, plano_id, dias, "manual")

    # --- Webhooks ---------------------------------------------------------

    async def processar_notificacao(self, tipo: str, recurso_id: str) -> str:
        """Process a webhook. Data is always re-fetched from the MP API (never trusted)."""
        if tipo == "payment":
            pagamento = await self.mp.obter_pagamento(recurso_id)
            return self._processar_pagamento(pagamento)
        if tipo == "subscription_preapproval":
            return self._processar_preapproval(await self.mp.obter_assinatura(recurso_id))
        if tipo == "subscription_authorized_payment":
            autorizado = await self.mp.obter_pagamento_autorizado(recurso_id)
            pre_id = str(autorizado.get("preapproval_id") or "")
            resultado = "sem pagamento"
            pagamento_id = (autorizado.get("payment") or {}).get("id")
            if pagamento_id:
                pagamento = await self.mp.obter_pagamento(str(pagamento_id))
                resultado = self._processar_pagamento(pagamento, preapproval_id=pre_id)
            if pre_id:
                self._processar_preapproval(await self.mp.obter_assinatura(pre_id))
            return resultado
        return f"ignorado ({tipo})"

    def _dono_da_assinatura(self, preapproval: dict[str, Any]) -> tuple[int, str] | None:
        ref = ler_referencia(preapproval.get("external_reference"))
        if ref:
            return ref[0], ref[1]
        return None

    def _processar_preapproval(self, preapproval: dict[str, Any]) -> str:
        dono = self._dono_da_assinatura(preapproval)
        if dono is None:
            return "assinatura sem referência do Radar"
        usuario_id, plano_id = dono
        atual = self.store.assinatura(usuario_id)
        pre_id = str(preapproval.get("id", ""))
        if atual and atual.mp_preapproval_id and atual.mp_preapproval_id != pre_id:
            # User started a newer checkout; ignore updates from the old one
            return "assinatura antiga ignorada"
        status = _STATUS_PREAPPROVAL.get(str(preapproval.get("status")), "pendente")
        self.store.salvar_assinatura(
            usuario_id,
            plano=plano_id if status == "ativa" or not atual else atual.plano,
            status=status,
            origem="assinatura",
            mp_preapproval_id=pre_id,
        )
        return f"assinatura {status}"

    def _processar_pagamento(
        self, pagamento: dict[str, Any], preapproval_id: str | None = None
    ) -> str:
        pagamento_id = str(pagamento.get("id", ""))
        ref = ler_referencia(pagamento.get("external_reference"))
        if ref is None and preapproval_id:
            pre = self.store.assinatura_por_preapproval(preapproval_id)
            if pre:
                ref = (pre.usuario_id, pre.plano, "assinatura")
        if ref is None or not pagamento_id:
            return "pagamento sem referência do Radar"
        usuario_id, plano_id, modo = ref
        plano = self.config.planos.get(plano_id)
        if plano is None or self.store.usuario_por_id(usuario_id) is None:
            return "plano ou usuário inexistente"

        status = str(pagamento.get("status", ""))
        valor = float(pagamento.get("transaction_amount") or 0)
        self.store.registrar_pagamento(pagamento_id, usuario_id, plano.id, status, valor)

        if status == "approved":
            if pagamento.get("currency_id", "BRL") != "BRL" or valor + 0.01 < plano.preco:
                logger.warning("Pagamento %s com valor/moeda inesperados: %s", pagamento_id, valor)
                return "valor divergente"
            if self.store.marcar_creditado(pagamento_id, True):
                fim = self.store.estender_periodo(usuario_id, plano.id, plano.dias, modo)
                return f"creditado até {fim.date().isoformat()}"
            return "já creditado"
        if status in _STATUS_ESTORNO and self.store.marcar_creditado(pagamento_id, False):
            self.store.reduzir_periodo(usuario_id, plano.dias)
            return "estornado"
        return f"status {status}"
