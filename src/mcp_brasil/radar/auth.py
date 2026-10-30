"""Integração do Radar Brasil com a autenticação e o pipeline de tools do FastMCP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

if TYPE_CHECKING:
    from .servico import RadarService

logger = logging.getLogger(__name__)

# Discovery calls don't count against the daily quota
TOOLS_ISENTAS = frozenset({"search_tools", "listar_features"})


class RadarTokenVerifier(TokenVerifier):
    """Accepts ``Authorization: Bearer rb_...`` keys of users with an active plan."""

    def __init__(self, servico: RadarService, base_url: str | None = None) -> None:
        super().__init__(base_url=base_url or None, required_scopes=["read"])
        self._servico = servico

    async def verify_token(self, token: str) -> AccessToken | None:
        usuario = self._servico.usuario_por_chave(token)
        if usuario is None:
            return None
        return AccessToken(
            token=token,
            client_id=f"radar:{usuario.id}",
            scopes=["read"],
            expires_at=None,
            claims={"radar_usuario_id": usuario.id, "email": usuario.email},
        )


class QuotaMiddleware(Middleware):
    """Enforce the per-plan daily limit of tool calls."""

    def __init__(self, servico: RadarService) -> None:
        self._servico = servico

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        token = get_access_token()
        usuario_id = token.claims.get("radar_usuario_id") if token else None
        if usuario_id is not None and context.message.name not in TOOLS_ISENTAS:
            usuario = self._servico.store.usuario_por_id(int(usuario_id))
            if usuario is None:
                raise ToolError("Usuário não encontrado.")
            limite = self._servico.limite_diario(usuario)
            if (
                limite is not None
                and self._servico.store.registrar_uso(usuario.id, limite) is None
            ):
                conta = f"{self._servico.config.base_url.rstrip('/')}/conta"
                raise ToolError(
                    f"Limite diário de {limite} consultas do seu plano atingido. "
                    f"O contador zera à meia-noite (UTC). Faça upgrade em {conta}"
                )
        return await call_next(context)
