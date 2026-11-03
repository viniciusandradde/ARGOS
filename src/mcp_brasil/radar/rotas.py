"""Rotas HTTP do Radar Brasil: portal, API da conta, administração e webhook."""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from mcp_brasil.data.noticias.filtros import Filtro

from . import painel as painel_dados
from .alertas import TIPOS, TIPOS_PADRAO, Alertas, gerar_codigo
from .coletor import ConfigColeta, coletar_tudo, loop_coleta
from .indicadores import Indicadores
from .mercadopago import MercadoPagoError, validar_assinatura_webhook
from .notificadores import NotificacaoError, normalizar_whatsapp
from .servico import ErroRadar, RadarService
from .store import Usuario

logger = logging.getLogger(__name__)

HEADER_SESSAO = "x-radar-sessao"
_PORTAL = pathlib.Path(__file__).with_name("portal.html")
_PAINEL = pathlib.Path(__file__).with_name("painel.html")

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


def _pagina(caminho: pathlib.Path, nome: str) -> HTMLResponse:
    return HTMLResponse(caminho.read_text(encoding="utf-8").replace("{{NOME}}", nome))


def registrar_rotas(
    mcp: FastMCP[Any],
    servico: RadarService,
    indicadores: Indicadores | None = None,
    coleta: ConfigColeta | None = None,
    coletor_embutido_minutos: int = 0,
    alertas: Alertas | None = None,
    telegram_bot: str = "",
) -> None:
    ind = indicadores or Indicadores(":memory:")
    cfg_coleta = coleta or ConfigColeta()
    tarefas: dict[str, asyncio.Task[Any]] = {}

    def garantir_coletor() -> None:
        """Start the in-process collector loop on first use (single-container deployments)."""
        if coletor_embutido_minutos <= 0:
            return
        tarefa = tarefas.get("loop")
        if tarefa is None or tarefa.done():
            depois = alertas.despachar if alertas and alertas.configurado else None
            tarefas["loop"] = asyncio.create_task(
                loop_coleta(ind, cfg_coleta, coletor_embutido_minutos, depois)
            )

    def tratar(handler: Handler) -> Handler:
        async def wrapper(request: Request) -> Response:
            try:
                return await handler(request)
            except ErroRadar as exc:
                return _erro(str(exc), exc.status)
            except MercadoPagoError as exc:
                logger.error("Mercado Pago: %s", exc)
                return _erro("Falha ao falar com o Mercado Pago. Tente novamente.", 502)
            except NotificacaoError as exc:
                logger.error("Notificação: %s", exc)
                return _erro(
                    "Falha ao enviar a mensagem. Verifique o número e tente de novo.", 502
                )

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

    nome = servico.config.nome

    async def portal(request: Request) -> Response:
        return _pagina(_PORTAL, nome)

    rota("/", ["GET"], portal)
    rota("/conta", ["GET"], portal)

    async def painel_html(request: Request) -> Response:
        return _pagina(_PAINEL, nome)

    rota("/painel", ["GET"], painel_html)

    async def planos(request: Request) -> Response:
        return JSONResponse(
            {
                "nome": nome,
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

    # --- Sala de situação, temas e pesquisa de preços -----------------------

    def assinante(handler: Callable[[Request, Usuario], Awaitable[Response]]) -> Handler:
        async def wrapper(request: Request, usuario: Usuario) -> Response:
            if not servico.acesso_ativo(usuario):
                return _erro("Recurso exclusivo para assinantes.", 402)
            return await handler(request, usuario)

        return logado(wrapper)

    async def painel_api(request: Request, usuario: Usuario) -> Response:
        garantir_coletor()
        q = request.query_params
        feed = Filtro(
            termos=[q["q"]] if q.get("q") else [],
            categorias=[q["categoria"]] if q.get("categoria") else [],
            escopo=q.get("escopo", "todos"),
            nivel_minimo=q.get("nivel", "normal"),
        )
        dados = await asyncio.to_thread(
            painel_dados.montar,
            ind,
            temas=servico.store.listar_temas(usuario.id),
            area_inmet=servico.config.area_inmet,
            cidade_precos=q.get("cidade_precos", servico.config.cidade_precos),
            feed_filtro=feed,
        )
        dados["nome"] = nome
        dados["cidades"] = cfg_coleta.cidades
        dados["admin"] = usuario.admin
        return JSONResponse(dados)

    rota("/api/painel", ["GET"], assinante(painel_api))

    async def listar_temas(request: Request, usuario: Usuario) -> Response:
        return JSONResponse({"temas": servico.store.listar_temas(usuario.id)})

    rota("/api/temas", ["GET"], logado(listar_temas))

    async def criar_tema(request: Request, usuario: Usuario) -> Response:
        if len(servico.store.listar_temas(usuario.id)) >= 20:
            return _erro("Limite de 20 temas por conta.")
        try:
            tema = painel_dados.validar_tema(await _corpo(request))
        except ValueError as exc:
            return _erro(str(exc))
        nome_tema = tema.pop("nome")
        tema_id = servico.store.criar_tema(usuario.id, nome_tema, tema)
        return JSONResponse({"id": tema_id, "nome": nome_tema, **tema}, status_code=201)

    rota("/api/temas", ["POST"], assinante(criar_tema))

    async def remover_tema(request: Request, usuario: Usuario) -> Response:
        if not servico.store.remover_tema(usuario.id, int(request.path_params["tema_id"])):
            return _erro("Tema não encontrado.", 404)
        return JSONResponse({"ok": True})

    rota("/api/temas/{tema_id:int}", ["DELETE"], logado(remover_tema))

    async def listar_precos(request: Request, usuario: Usuario) -> Response:
        cidade = request.query_params.get("cidade") or None
        return JSONResponse(
            {
                "medias": ind.medias_precos(cidade),
                "precos": ind.listar_precos(cidade, 200),
            }
        )

    rota("/api/precos", ["GET"], assinante(listar_precos))

    async def adicionar_preco(request: Request, usuario: Usuario) -> Response:
        dados = await _corpo(request)
        try:
            preco = float(str(dados.get("preco", "")).replace(",", "."))
        except ValueError:
            return _erro("Preço inválido.")
        produto = str(dados.get("produto", "")).strip()[:80]
        mercado = str(dados.get("mercado", "")).strip()[:80]
        cidade = str(dados.get("cidade", servico.config.cidade_precos)).strip()[:80]
        if not produto or not mercado or preco <= 0:
            return _erro("Informe produto, mercado e um preço maior que zero.")
        data = str(dados.get("data") or "")[:10] or date.today().isoformat()
        preco_id = ind.adicionar_preco(
            produto=produto,
            mercado=mercado,
            cidade=cidade,
            preco=round(preco, 2),
            unidade=str(dados.get("unidade", "un")).strip()[:20] or "un",
            data=data,
            usuario_id=usuario.id,
        )
        return JSONResponse({"id": preco_id}, status_code=201)

    rota("/api/precos", ["POST"], assinante(adicionar_preco))

    async def remover_preco(request: Request, usuario: Usuario) -> Response:
        preco_id = int(request.path_params["preco_id"])
        ok = ind.remover_preco(preco_id, None if usuario.admin else usuario.id)
        return JSONResponse({"ok": True}) if ok else _erro("Registro não encontrado.", 404)

    rota("/api/precos/{preco_id:int}", ["DELETE"], logado(remover_preco))

    # --- Alertas por Telegram e WhatsApp --------------------------------------

    bot = {"nome": telegram_bot}

    def exige_alertas() -> Alertas:
        if alertas is None or not alertas.configurado:
            raise ErroRadar("Alertas ainda não configurados neste servidor.", 503)
        return alertas

    def resumo_alertas(usuario: Usuario) -> dict[str, Any]:
        prefs = servico.store.preferencias_alerta(usuario.id)
        numero = prefs.get("whatsapp_numero") or ""
        return {
            "telegram": {
                "disponivel": bool(alertas and alertas.telegram.configurado),
                "conectado": bool(prefs.get("telegram_chat_id")),
            },
            "whatsapp": {
                "disponivel": bool(alertas and alertas.whatsapp.configurado),
                "numero": f"+{numero[:4]}•••••{numero[-4:]}" if numero else "",
                "verificado": bool(prefs.get("whatsapp_verificado")),
                "aguardando_codigo": bool(prefs.get("whatsapp_codigo")),
            },
            "tipos": [
                {"id": k, "descricao": v, "ativo": {**TIPOS_PADRAO, **prefs["tipos"]}[k]}
                for k, v in TIPOS.items()
            ],
        }

    async def alertas_get(request: Request, usuario: Usuario) -> Response:
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas", ["GET"], logado(alertas_get))

    async def alertas_put(request: Request, usuario: Usuario) -> Response:
        dados = await _corpo(request)
        tipos = dados.get("tipos") if isinstance(dados.get("tipos"), dict) else {}
        servico.store.salvar_preferencias(
            usuario.id, tipos={k: bool(v) for k, v in (tipos or {}).items() if k in TIPOS}
        )
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas", ["PUT"], assinante(alertas_put))

    async def telegram_link(request: Request, usuario: Usuario) -> Response:
        al = exige_alertas()
        if not al.telegram.configurado:
            raise ErroRadar("Telegram não configurado neste servidor.", 503)
        if not bot["nome"]:
            bot["nome"] = await al.telegram.nome_usuario()
        codigo = gerar_codigo()
        servico.store.salvar_preferencias(usuario.id, telegram_codigo=codigo)
        return JSONResponse({"link": f"https://t.me/{bot['nome']}?start={codigo}"})

    rota("/api/alertas/telegram", ["POST"], assinante(telegram_link))

    async def telegram_verificar(request: Request, usuario: Usuario) -> Response:
        await exige_alertas().processar_telegram()
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas/telegram/verificar", ["POST"], assinante(telegram_verificar))

    async def telegram_remover(request: Request, usuario: Usuario) -> Response:
        servico.store.salvar_preferencias(usuario.id, telegram_chat_id=None, telegram_codigo=None)
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas/telegram", ["DELETE"], logado(telegram_remover))

    async def whatsapp_iniciar(request: Request, usuario: Usuario) -> Response:
        al = exige_alertas()
        if not al.whatsapp.configurado:
            raise ErroRadar("WhatsApp não configurado neste servidor.", 503)
        numero = normalizar_whatsapp(str((await _corpo(request)).get("numero", "")))
        if numero is None:
            raise ErroRadar("Número inválido. Use DDD + número, ex: 67 99999-9999.")
        chave = f"wa_codigo_ts:{usuario.id}"
        ultimo = float(servico.store.estado(chave) or 0)
        if datetime.now().timestamp() - ultimo < 60:
            raise ErroRadar("Aguarde um minuto antes de pedir outro código.", 429)
        servico.store.salvar_estado(chave, str(datetime.now().timestamp()))
        await al.iniciar_whatsapp(usuario, numero)
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas/whatsapp", ["POST"], assinante(whatsapp_iniciar))

    async def whatsapp_confirmar(request: Request, usuario: Usuario) -> Response:
        prefs = servico.store.preferencias_alerta(usuario.id)
        codigo = str((await _corpo(request)).get("codigo", "")).strip()
        tentativas = int(servico.store.estado(f"wa_tentativas:{usuario.id}") or 0)
        if not prefs.get("whatsapp_codigo") or tentativas >= 5:
            servico.store.salvar_preferencias(usuario.id, whatsapp_codigo=None)
            servico.store.salvar_estado(f"wa_tentativas:{usuario.id}", "0")
            raise ErroRadar("Código expirado. Peça um novo.")
        if codigo != prefs["whatsapp_codigo"]:
            servico.store.salvar_estado(f"wa_tentativas:{usuario.id}", str(tentativas + 1))
            raise ErroRadar("Código incorreto.")
        servico.store.salvar_estado(f"wa_tentativas:{usuario.id}", "0")
        servico.store.salvar_preferencias(
            usuario.id,
            whatsapp_verificado=True,
            whatsapp_codigo=None,
            ativo_desde=datetime.now(timezone.utc).isoformat(),
        )
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas/whatsapp/confirmar", ["POST"], assinante(whatsapp_confirmar))

    async def whatsapp_remover(request: Request, usuario: Usuario) -> Response:
        servico.store.salvar_preferencias(
            usuario.id, whatsapp_numero=None, whatsapp_verificado=False, whatsapp_codigo=None
        )
        return JSONResponse(resumo_alertas(usuario))

    rota("/api/alertas/whatsapp", ["DELETE"], logado(whatsapp_remover))

    async def alertas_teste(request: Request, usuario: Usuario) -> Response:
        al = exige_alertas()
        from .alertas import Evento

        evento = Evento(
            chave="teste",
            titulo="Teste de alerta — tudo funcionando",
            detalhe="Você receberá aqui os alertas configurados no portal.",
            nivel="normal",
        )
        canais = await al.enviar(servico.store.preferencias_alerta(usuario.id), [evento])
        if not canais:
            raise ErroRadar("Nenhum canal conectado (ou o envio falhou).")
        return JSONResponse({"enviado_para": canais})

    rota("/api/alertas/teste", ["POST"], assinante(alertas_teste))

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

    async def admin_coletar(request: Request, usuario: Usuario) -> Response:
        resultados = await coletar_tudo(ind, cfg_coleta)
        return JSONResponse({"resultados": resultados})

    rota("/api/admin/coletar", ["POST"], admin(admin_coletar))
