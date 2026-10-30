"""Rotas HTTP do Radar Brasil: portal, API da conta, administração e webhook."""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from .mercadopago import MercadoPagoError, validar_assinatura_webhook
from .servico import ErroRadar, RadarService
from .store import Usuario

logger = logging.getLogger(__name__)

HEADER_SESSAO = "x-radar-sessao"
_PORTAL = pathlib.Path(__file__).with_name("portal.html")

Handler = Callable[[Request], Awaitable[Response]]


def _erro(mensagem: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"erro": mensagem}, status_code=status)


async def _corpo(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _base_url(servico: RadarService, request: Request) -> str:
    return servico.config.base_url or str(request.base_url).rstrip("/")


def registrar_rotas(mcp: FastMCP[Any], servico: RadarService) -> None:
    def tratar(handler: Handler) -> Handler:
        async def wrapper(request: Request) -> Response:
            try:
                return await handler(request)
            except ErroRadar as exc:
                return _erro(str(exc), exc.status)
            except MercadoPagoError as exc:
                logger.error("Mercado Pago: %s", exc)
                return _erro("Falha ao falar com o Mercado Pago. Tente novamente.", 502)

        return wrapper

    def logado(handler: Callable[[Request, Usuario], Awaitable[Response]]) -> Handler:
        async def wrapper(request: Request) -> Response:
            usuario = servico.usuario_da_sessao(request.headers.get(HEADER_SESSAO))
            if usuario is None:
                return _erro("Sessão inválida ou expirada. Entre novamente.", 401)
            return await handler(request, usuario)

        return tratar(wrapper)

    def admin(handler: Callable[[Request, Usuario], Awaitable[Response]]) -> Handler:
        async def wrapper(request: Request, usuario: Usuario) -> Response:
            if not usuario.admin:
                return _erro("Acesso restrito a administradores.", 403)
            return await handler(request, usuario)

        return logado(wrapper)

    def rota(path: str, methods: list[str], handler: Handler) -> None:
        mcp.custom_route(path, methods=methods)(handler)

    # --- Portal -------------------------------------------------------------

    async def portal(request: Request) -> Response:
        return HTMLResponse(_PORTAL.read_text(encoding="utf-8"))

    rota("/", ["GET"], portal)
    rota("/conta", ["GET"], portal)

    async def planos(request: Request) -> Response:
        return JSONResponse(
            {
                "planos": [p.to_dict() for p in servico.config.planos.values()],
                "pagamentos_ativos": servico.mp.configurado,
            }
        )

    rota("/api/planos", ["GET"], planos)

    # --- Conta --------------------------------------------------------------

    async def cadastro(request: Request) -> Response:
        dados = await _corpo(request)
        usuario = servico.cadastrar(
            str(dados.get("email", "")), str(dados.get("senha", "")), str(dados.get("nome", ""))
        )
        _, sessao = servico.autenticar(usuario.email, str(dados.get("senha", "")))
        return JSONResponse({"sessao": sessao, "usuario": usuario.publico()}, status_code=201)

    rota("/api/cadastro", ["POST"], tratar(cadastro))

    async def login(request: Request) -> Response:
        dados = await _corpo(request)
        usuario, sessao = servico.autenticar(
            str(dados.get("email", "")), str(dados.get("senha", ""))
        )
        return JSONResponse({"sessao": sessao, "usuario": usuario.publico()})

    rota("/api/login", ["POST"], tratar(login))

    async def eu(request: Request, usuario: Usuario) -> Response:
        resumo = servico.resumo(usuario)
        if not servico.config.base_url:
            resumo["mcp_url"] = f"{_base_url(servico, request)}/mcp"
        return JSONResponse(resumo)

    rota("/api/eu", ["GET"], logado(eu))

    async def senha(request: Request, usuario: Usuario) -> Response:
        dados = await _corpo(request)
        servico.trocar_senha(usuario, str(dados.get("atual", "")), str(dados.get("nova", "")))
        return JSONResponse({"ok": True})

    rota("/api/senha", ["POST"], logado(senha))

    async def criar_chave(request: Request, usuario: Usuario) -> Response:
        dados = await _corpo(request)
        return JSONResponse(
            servico.criar_chave(usuario, str(dados.get("nome", ""))[:60]), status_code=201
        )

    rota("/api/chaves", ["POST"], logado(criar_chave))

    async def revogar_chave(request: Request, usuario: Usuario) -> Response:
        chave_id = int(request.path_params["chave_id"])
        if not servico.store.revogar_chave(usuario.id, chave_id):
            return _erro("Chave não encontrada.", 404)
        return JSONResponse({"ok": True})

    rota("/api/chaves/{chave_id:int}", ["DELETE"], logado(revogar_chave))

    # --- Cobrança -----------------------------------------------------------

    async def checkout(request: Request, usuario: Usuario) -> Response:
        dados = await _corpo(request)
        url = await servico.iniciar_checkout(
            usuario,
            str(dados.get("plano", "")),
            str(dados.get("modo", "assinatura")),
            base_url=_base_url(servico, request),
        )
        return JSONResponse({"url": url})

    rota("/api/cobranca/checkout", ["POST"], logado(checkout))

    async def cancelar(request: Request, usuario: Usuario) -> Response:
        await servico.cancelar_assinatura(usuario)
        return JSONResponse({"ok": True})

    rota("/api/cobranca/cancelar", ["POST"], logado(cancelar))

    async def webhook(request: Request) -> Response:
        dados = await _corpo(request)
        params = request.query_params
        tipo = str(dados.get("type") or params.get("type") or params.get("topic") or "")
        data = dados.get("data") if isinstance(dados.get("data"), dict) else {}
        recurso_id = str(params.get("data.id") or (data or {}).get("id") or params.get("id") or "")

        segredo = servico.config.mp_webhook_secret
        if segredo and not validar_assinatura_webhook(
            request.headers.get("x-signature"),
            request.headers.get("x-request-id"),
            params.get("data.id") or recurso_id,
            segredo,
        ):
            logger.warning("Webhook Mercado Pago com assinatura inválida (tipo=%s)", tipo)
            return _erro("assinatura inválida", 401)
        if not recurso_id:
            return JSONResponse({"ok": True, "resultado": "sem id"})
        try:
            resultado = await servico.processar_notificacao(tipo, recurso_id)
        except MercadoPagoError as exc:
            # Non-2xx makes Mercado Pago retry the notification later
            logger.error("Webhook %s/%s falhou: %s", tipo, recurso_id, exc)
            return _erro("falha temporária", 500)
        logger.info("Webhook %s/%s: %s", tipo, recurso_id, resultado)
        return JSONResponse({"ok": True, "resultado": resultado})

    rota("/webhooks/mercadopago", ["POST"], webhook)

    # --- Administração ------------------------------------------------------

    async def admin_usuarios(request: Request, usuario: Usuario) -> Response:
        itens = []
        for u in servico.store.listar_usuarios():
            assinatura = servico.store.assinatura(u.id)
            itens.append(
                {
                    **u.publico(),
                    "assinatura": assinatura.publico() if assinatura else None,
                    "acesso_ativo": servico.acesso_ativo(u, assinatura),
                    "uso_hoje": servico.store.uso_hoje(u.id),
                }
            )
        return JSONResponse({"usuarios": itens})

    rota("/api/admin/usuarios", ["GET"], admin(admin_usuarios))

    async def admin_atualizar(request: Request, usuario: Usuario) -> Response:
        alvo_id = int(request.path_params["usuario_id"])
        if servico.store.usuario_por_id(alvo_id) is None:
            return _erro("Usuário não encontrado.", 404)
        dados = await _corpo(request)
        papel = dados.get("papel")
        if papel is not None and papel not in ("admin", "cliente"):
            return _erro("Papel inválido.")
        ativo = dados.get("ativo")
        servico.store.atualizar_usuario(
            alvo_id,
            ativo=bool(ativo) if ativo is not None else None,
            papel=str(papel) if papel is not None else None,
        )
        if dados.get("conceder_plano"):
            servico.conceder(alvo_id, str(dados["conceder_plano"]), int(dados.get("dias", 30)))
        return JSONResponse({"ok": True})

    rota("/api/admin/usuarios/{usuario_id:int}", ["PATCH"], admin(admin_atualizar))

    async def admin_pagamentos(request: Request, usuario: Usuario) -> Response:
        return JSONResponse({"pagamentos": servico.store.listar_pagamentos()})

    rota("/api/admin/pagamentos", ["GET"], admin(admin_pagamentos))
