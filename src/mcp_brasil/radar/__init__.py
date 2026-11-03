"""Radar Brasil — camada comercial do servidor MCP.

Ativada com ``MCP_BRASIL_AUTH_MODE=radar``. Adiciona:

- cadastro/login de usuários e portal do cliente (``/conta``);
- chaves de API por usuário (``Authorization: Bearer rb_...`` no endpoint ``/mcp``);
- planos com limite diário de consultas;
- cobrança via Mercado Pago (assinatura recorrente ou pagamento avulso com Pix/boleto)
  e webhook em ``/webhooks/mercadopago``;
- endpoints de administração (``/api/admin/*``);
- sala de situação em tempo real (``/painel``), temas de notícias por usuário,
  pesquisa de preços e coletor de indicadores (``indicadores.db``, lido pelo Metabase).
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Any

from fastmcp import FastMCP

from .alertas import Alertas
from .coletor import ConfigColeta
from .indicadores import Indicadores
from .planos import carregar_planos
from .servico import RadarConfig, RadarService
from .store import Store

logger = logging.getLogger(__name__)


def config_from_settings() -> RadarConfig:
    from mcp_brasil import settings

    segredo = settings.RADAR_SECRET_KEY
    if not segredo:
        segredo = secrets.token_urlsafe(32)
        logger.warning(
            "RADAR_SECRET_KEY não definido — usando chave temporária "
            "(sessões do portal expiram a cada reinício)."
        )
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        logger.warning("MERCADOPAGO_ACCESS_TOKEN não definido — checkout desativado.")
    if settings.MERCADOPAGO_ACCESS_TOKEN and not settings.MERCADOPAGO_WEBHOOK_SECRET:
        logger.warning("MERCADOPAGO_WEBHOOK_SECRET não definido — webhooks sem validação.")
    return RadarConfig(
        db_path=settings.RADAR_DB_PATH,
        segredo=segredo,
        base_url=settings.MCP_BRASIL_BASE_URL,
        mp_access_token=settings.MERCADOPAGO_ACCESS_TOKEN,
        mp_webhook_secret=settings.MERCADOPAGO_WEBHOOK_SECRET,
        planos=carregar_planos(settings.RADAR_PLANOS),
        carencia_dias=settings.RADAR_CARENCIA_DIAS,
        sessao_horas=settings.RADAR_SESSAO_HORAS,
        teste_dias=settings.RADAR_TESTE_DIAS,
        plano_teste=settings.RADAR_PLANO_TESTE,
        nome=settings.RADAR_NOME,
        area_inmet=settings.RADAR_AREA_INMET,
        cidade_precos=settings.RADAR_CIDADES[0] if settings.RADAR_CIDADES else "",
    )


def config_coleta_from_settings() -> ConfigColeta:
    from mcp_brasil import settings

    return ConfigColeta(
        cidades=settings.RADAR_CIDADES,
        alimentos_localidades=settings.RADAR_ALIMENTOS_LOCALIDADES,
    )


@lru_cache(maxsize=1)
def get_alertas() -> Alertas:
    from mcp_brasil import settings

    from .notificadores import EvolutionClient, TelegramClient, WhatsAppClient

    whatsapp: EvolutionClient | WhatsAppClient
    if settings.WHATSAPP_PROVEDOR == "meta":
        whatsapp = WhatsAppClient(
            settings.WHATSAPP_TOKEN,
            settings.WHATSAPP_PHONE_NUMBER_ID,
            template=settings.WHATSAPP_TEMPLATE,
            idioma=settings.WHATSAPP_TEMPLATE_IDIOMA,
            versao=settings.WHATSAPP_API_VERSAO,
        )
    else:
        whatsapp = EvolutionClient(
            settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCIA
        )
    return Alertas(
        get_servico(),
        get_indicadores(),
        TelegramClient(settings.TELEGRAM_BOT_TOKEN),
        whatsapp,
        max_itens=settings.RADAR_ALERTAS_MAX_ITENS,
        intervalo_whatsapp=settings.WHATSAPP_INTERVALO_SEG,
    )


@lru_cache(maxsize=1)
def get_indicadores() -> Indicadores:
    from mcp_brasil import settings

    return Indicadores(settings.RADAR_INDICADORES_DB)


@lru_cache(maxsize=1)
def get_servico() -> RadarService:
    """Process-wide Radar service built from environment settings."""
    config = config_from_settings()
    return RadarService(config, Store(config.db_path))


def build_verifier() -> Any:
    from .auth import RadarTokenVerifier

    servico = get_servico()
    return RadarTokenVerifier(servico, base_url=servico.config.base_url)


def install(
    mcp: FastMCP[Any],
    servico: RadarService | None = None,
    indicadores: Indicadores | None = None,
    alertas: Alertas | None = None,
) -> RadarService:
    """Register the portal, situation room, billing routes and the quota middleware."""
    from mcp_brasil import settings

    from .auth import QuotaMiddleware
    from .rotas import registrar_rotas

    servico = servico or get_servico()
    registrar_rotas(
        mcp,
        servico,
        indicadores if indicadores is not None else get_indicadores(),
        config_coleta_from_settings(),
        settings.RADAR_COLETA_MINUTOS if settings.RADAR_COLETOR_EMBUTIDO else 0,
        alertas if alertas is not None else get_alertas(),
        settings.TELEGRAM_BOT_USERNAME,
    )
    mcp.add_middleware(QuotaMiddleware(servico))
    logger.info(
        "Radar Brasil ativo: %d planos, banco em %s",
        len(servico.config.planos),
        servico.config.db_path,
    )
    return servico
