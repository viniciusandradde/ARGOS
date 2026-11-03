"""Alertas por Telegram e WhatsApp.

A cada rodada do coletor, para cada assinante com canal conectado:
1. detecta eventos novos (notícias de temas marcados, surtos, críticos, arboviroses
   em nível alto, mudança no alerta do El Niño, avisos do INMET na região);
2. descarta o que já foi enviado (tabela ``alertas_enviados``);
3. junta tudo em **uma** mensagem por canal (resumo), para não inundar o cliente.
"""

from __future__ import annotations

import contextlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp_brasil.data.noticias.filtros import Filtro
from mcp_brasil.data.vigilancia.constants import TERMOS_SURTO

from .indicadores import Indicadores
from .notificadores import NotificacaoError, TelegramClient, WhatsAppClient, escapar
from .painel import CAMPOS_NOTICIA, filtrar, filtro_do_tema
from .servico import RadarService
from .store import Usuario

logger = logging.getLogger(__name__)

TIPOS = {
    "temas": "Notícias dos temas marcados para alerta",
    "surtos": "Surtos, epidemias e pandemias",
    "criticos": "Todas as notícias críticas (volume alto)",
    "arboviroses": "Dengue/zika/chikungunya em nível laranja ou vermelho nas cidades monitoradas",
    "enso": "Mudança no alerta oficial do El Niño (NOAA)",
    "inmet": "Avisos de Perigo do INMET na sua região",
}
TIPOS_PADRAO = {"temas": True, "surtos": True, "criticos": False, "arboviroses": True,
                "enso": True, "inmet": True}  # fmt: skip
JANELA_HORAS = 6
NIVEL_ICONE = {"critico": "🔴", "alto": "🟠", "normal": "⚪"}


@dataclass
class Evento:
    chave: str
    titulo: str
    detalhe: str = ""
    link: str = ""
    nivel: str = "alto"


def gerar_codigo() -> str:
    return secrets.token_hex(4)


def gerar_codigo_numerico() -> str:
    return f"{secrets.randbelow(10**6):06d}"


class Alertas:
    def __init__(
        self,
        servico: RadarService,
        ind: Indicadores,
        telegram: TelegramClient,
        whatsapp: WhatsAppClient,
        max_itens: int = 8,
    ) -> None:
        self.servico = servico
        self.store = servico.store
        self.ind = ind
        self.telegram = telegram
        self.whatsapp = whatsapp
        self.max_itens = max_itens

    @property
    def configurado(self) -> bool:
        return self.telegram.configurado or self.whatsapp.configurado

    # --- Detecção de eventos --------------------------------------------------

    def eventos_para(self, usuario: Usuario, prefs: dict[str, Any]) -> list[Evento]:
        tipos = {**TIPOS_PADRAO, **prefs.get("tipos", {})}
        ativo_desde = prefs.get("ativo_desde") or ""
        janela = (datetime.now(timezone.utc) - timedelta(hours=JANELA_HORAS)).isoformat()
        desde = max(ativo_desde, janela)
        recentes = self.ind.consultar(
            f"SELECT {CAMPOS_NOTICIA} FROM noticias WHERE coletado_em >= ? "
            "ORDER BY publicado_em DESC LIMIT 1500",
            (desde,),
        )
        eventos: list[Evento] = []

        def noticias(linhas: list[dict[str, Any]], rotulo: str) -> None:
            for r in linhas:
                eventos.append(
                    Evento(
                        chave=f"noticia:{r['link']}",
                        titulo=f"{rotulo}{r['titulo']}",
                        detalhe=r["fonte_nome"],
                        link=r["link"],
                        nivel=r["nivel"],
                    )
                )

        if tipos.get("temas"):
            for tema in self.store.listar_temas(usuario.id):
                if tema.get("alertar"):
                    noticias(filtrar(recentes, filtro_do_tema(tema), 10), f"[{tema['nome']}] ")
        if tipos.get("surtos"):
            filtro = Filtro(
                termos=TERMOS_SURTO,
                categorias=["saude", "epidemias"],
                nivel_minimo="alto",
                apenas_titulo=True,
            )
            noticias(filtrar(recentes, filtro, 10), "[Surto] ")
        if tipos.get("criticos"):
            noticias(filtrar(recentes, Filtro(nivel_minimo="critico"), 15), "")

        if tipos.get("arboviroses"):
            for a in self.ind.consultar(
                "SELECT a.* FROM arboviroses a JOIN (SELECT geocodigo, doenca, MAX(semana) s "
                "FROM arboviroses GROUP BY geocodigo, doenca) m ON a.geocodigo = m.geocodigo "
                "AND a.doenca = m.doenca AND a.semana = m.s WHERE a.nivel >= 3"
            ):
                cor = "VERMELHO" if a["nivel"] == 4 else "LARANJA"
                eventos.append(
                    Evento(
                        chave=f"arbo:{a['geocodigo']}:{a['doenca']}:{a['semana']}:{a['nivel']}",
                        titulo=f"{a['doenca'].capitalize()} em {a['municipio']}: nível {cor}",
                        detalhe=(
                            f"{a['casos_semana']} casos na semana, {a['casos_ano']} no ano, "
                            f"Rt {a['rt']}"
                        ),
                        nivel="critico" if a["nivel"] == 4 else "alto",
                    )
                )

        if tipos.get("enso"):
            for s in self.ind.consultar("SELECT alerta, fase FROM enso_status WHERE alerta != ''"):
                eventos.append(
                    Evento(
                        chave=f"enso:{s['alerta']}",
                        titulo=f"El Niño — NOAA: {s['alerta']}",
                        detalhe=s["fase"] or "",
                        link="https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/",
                    )
                )

        area = self.servico.config.area_inmet.casefold()
        if tipos.get("inmet") and area:
            for a in self.ind.consultar(
                "SELECT * FROM avisos_inmet WHERE severidade IN ('Perigo', 'Grande Perigo')"
            ):
                if area in (a["area"] or "").casefold():
                    eventos.append(
                        Evento(
                            chave=f"inmet:{a['link']}",
                            titulo=f"INMET: {a['evento']} — {a['severidade']}",
                            detalhe=f"{a['inicio']} → {a['fim']}",
                            link=a["link"],
                            nivel="critico" if a["severidade"] == "Grande Perigo" else "alto",
                        )
                    )

        vistos: set[str] = set()
        unicos = []
        for e in eventos:
            if e.chave not in vistos:
                vistos.add(e.chave)
                unicos.append(e)
        return unicos

    # --- Mensagens --------------------------------------------------------------

    def _texto_telegram(self, eventos: list[Evento]) -> str:
        nome = escapar(self.servico.config.nome)
        linhas = [f"<b>🛰 {nome} — {len(eventos)} alerta(s)</b>", ""]
        for e in eventos[: self.max_itens]:
            titulo = escapar(e.titulo)
            if e.link:
                titulo = f'<a href="{escapar(e.link)}">{titulo}</a>'
            linhas.append(f"{NIVEL_ICONE.get(e.nivel, '')} {titulo}")
            if e.detalhe:
                linhas.append(f"   <i>{escapar(e.detalhe)}</i>")
        if len(eventos) > self.max_itens:
            linhas.append(f"\n+{len(eventos) - self.max_itens} outros no painel.")
        if self.servico.config.base_url:
            linhas.append(f"\n{escapar(self.servico.config.base_url.rstrip('/'))}/painel")
        return "\n".join(linhas)

    def _texto_whatsapp(self, eventos: list[Evento]) -> tuple[str, str]:
        titulo = f"{len(eventos)} alerta(s) do {self.servico.config.nome}"
        partes = [f"{NIVEL_ICONE.get(e.nivel, '')} {e.titulo}" for e in eventos[: self.max_itens]]
        if len(eventos) > self.max_itens:
            partes.append(f"+{len(eventos) - self.max_itens} outros")
        if self.servico.config.base_url:
            partes.append(f"Painel: {self.servico.config.base_url.rstrip('/')}/painel")
        return titulo, " | ".join(partes)

    async def enviar(self, prefs: dict[str, Any], eventos: list[Evento]) -> list[str]:
        """Send the digest through every connected channel. Returns channels that succeeded."""
        ok: list[str] = []
        if prefs.get("telegram_chat_id") and self.telegram.configurado:
            try:
                await self.telegram.enviar(
                    prefs["telegram_chat_id"], self._texto_telegram(eventos)
                )
                ok.append("telegram")
            except NotificacaoError as exc:
                logger.warning("Telegram falhou para %s: %s", prefs["usuario_id"], exc)
        if prefs.get("whatsapp_verificado") and self.whatsapp.configurado:
            titulo, detalhes = self._texto_whatsapp(eventos)
            try:
                await self.whatsapp.enviar_template(prefs["whatsapp_numero"], titulo, detalhes)
                ok.append("whatsapp")
            except NotificacaoError as exc:
                logger.warning("WhatsApp falhou para %s: %s", prefs["usuario_id"], exc)
        return ok

    # --- Rodada -----------------------------------------------------------------

    async def despachar(self) -> dict[str, int]:
        """One dispatch round over all subscribers with a connected channel."""
        if not self.configurado:
            return {"usuarios": 0, "mensagens": 0}
        await self.processar_telegram()
        usuarios = mensagens = 0
        for prefs in self.store.listar_preferencias_alerta():
            usuario = self.store.usuario_por_id(prefs["usuario_id"])
            if usuario is None or not self.servico.acesso_ativo(usuario):
                continue
            canais = bool(prefs.get("telegram_chat_id")) or bool(prefs.get("whatsapp_verificado"))
            if not canais:
                continue
            novos = [
                e
                for e in self.eventos_para(usuario, prefs)
                if not self.store.alerta_enviado(usuario.id, e.chave)
            ]
            if not novos:
                continue
            # Local/official signals first, then news; critical before high within each group
            novos.sort(
                key=lambda e: (
                    e.chave.startswith("noticia:"),
                    {"critico": 0, "alto": 1}.get(e.nivel, 2),
                )
            )
            enviados = await self.enviar(prefs, novos)
            if enviados:
                self.store.marcar_alertas(usuario.id, [e.chave for e in novos])
                usuarios += 1
                mensagens += len(enviados)
        return {"usuarios": usuarios, "mensagens": mensagens}

    # --- Vinculação de canais -----------------------------------------------------

    async def processar_telegram(self) -> int:
        """Read pending ``/start <código>`` messages and link chats to users."""
        if not self.telegram.configurado:
            return 0
        offset = int(self.store.estado("telegram_offset") or 0)
        vinculados = 0
        for upd in await self.telegram.atualizacoes(offset):
            offset = max(offset, int(upd.get("update_id", 0)) + 1)
            msg = upd.get("message") or {}
            texto = str(msg.get("text") or "")
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            if not texto.startswith("/start") or not chat_id:
                continue
            codigo = texto.removeprefix("/start").strip()
            usuario_id = self.store.vincular_telegram(codigo, chat_id) if codigo else None
            resposta = (
                f"✅ Conectado ao {self.servico.config.nome}! Você receberá alertas aqui."
                if usuario_id
                else "Código inválido. Gere um novo link em Conta → Alertas."
            )
            with contextlib.suppress(NotificacaoError):
                await self.telegram.enviar(chat_id, escapar(resposta))
            vinculados += int(bool(usuario_id))
        self.store.salvar_estado("telegram_offset", str(offset))
        return vinculados

    async def iniciar_whatsapp(self, usuario: Usuario, numero: str) -> None:
        codigo = gerar_codigo_numerico()
        self.store.salvar_preferencias(
            usuario.id,
            whatsapp_numero=numero,
            whatsapp_verificado=False,
            whatsapp_codigo=codigo,
        )
        await self.whatsapp.enviar_template(
            numero,
            f"Código de verificação {self.servico.config.nome}",
            f"Seu código é {codigo}. Digite-o no portal para ativar os alertas.",
        )
