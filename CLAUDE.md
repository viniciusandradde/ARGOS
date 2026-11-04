# ARGOS (mcp-brasil) — guia para o Claude

## Memória do projeto (leia primeiro)

Estado atual, decisões, pendências e armadilhas do ambiente: **`memory/projeto-argos.md`**.
Branch de trabalho: `ccr-d79070a6-p6sovy`. Responda ao usuário em português e mande prints dos resultados.
Ao concluir uma etapa, atualize `memory/projeto-argos.md` e faça commit e push.

## Se a tarefa for instalar/rodar em VPS

Siga **`docs/deploy/HANDOFF_VPS.md`** do início ao fim: requisitos, perguntas ao usuário, instalação
(`scripts/instalar_vps.sh`), verificação (`scripts/verificar.sh`), backup, atualização e problemas comuns.
Não suba o Metabase (perfil `relatorios`) sem pedido explícito.

## Visão geral do código

- `src/mcp_brasil/data/<feature>/`: uma pasta por fonte de dados (auto-registry). Cada uma tem
  `__init__.py` (FEATURE_META), `server.py` (registra tools), `tools.py`, `client.py` (HTTP) e `schemas.py`.
- `src/mcp_brasil/radar/`: camada comercial ARGOS (`MCP_BRASIL_AUTH_MODE=radar`):
  - acesso e cobrança: usuários, chaves de API e planos; Mercado Pago;
  - telas: portal `/conta`, sala de situação `/painel` e radar climático local `/clima`;
  - coletor (`coletor.py`, que roda embutido no processo web) e alertas por Telegram e WhatsApp (Evolution API).
- Bancos SQLite: `radar.db` (privado) e `indicadores.db` (dados públicos coletados).

## Comandos de desenvolvimento

```bash
make dev          # dependências
make ci           # ruff + mypy --strict + pytest (tudo deve passar antes de commit)
make test-feature F=clima
```

Convenções: código e docstrings de tools em português, comentários de código em inglês,
linha máxima de 99 colunas, mypy strict, testes com `respx` para HTTP.
