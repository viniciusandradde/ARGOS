# Memória do projeto ARGOS

Estado consolidado em **04/11/2026**. Atualize este arquivo ao fechar cada etapa.

## Quem é o usuário e o que ele quer

- Vinicius (viniciusandradde), foco em **Dourados/MS**. Conversa em português e pede **prints e exports** para ver o resultado.
- Produto comercial: vender acesso a um sistema de **monitoramento ativo** do Brasil e do mundo:
  governo, leis, impostos, saúde/epidemias, clima, alimentos e notícias.
- Prefere stack **simples, leve e eficiente** (VPS pequena). Não quer Metabase por enquanto.
- Nome do produto: **ARGOS** (Argos Panoptes, "cem olhos"). Configurável em `RADAR_NOME`.
  O pacote Python continua `mcp_brasil`; é um fork de jxnxts/mcp-brasil, mantido assim para facilitar a sincronização.

## Onde está o código

- Repositório: `viniciusandradde/mcp-brasil`. Branch de trabalho: **`ccr-d79070a6-p6sovy`** (não há PR aberto).
- Commits da sessão, do mais antigo para o mais novo:
  1. `ab7d243` siconfi, lexml, noticias
  2. `5daff46` modo comercial: usuários, planos, Mercado Pago, portal `/conta`
  3. `0019c28` notícias internacionais, El Niño, clima, vigilância, alimentos, mundo
  4. `287a41a` sala de situação `/painel`, coletor, temas, pesquisa de preços, Metabase
  5. `1982ef9` alertas Telegram e WhatsApp
  6. `0b57c56` WhatsApp via Evolution API (Meta oficial guardada para a próxima versão)
  7. `10ad15b` radar climático local `/clima` e deploy leve em VPS (handoff)
- CI: `make ci` (ruff, mypy strict, pytest). Último resultado: **2.447 testes passando**.

## Arquitetura (resumo)

- `src/mcp_brasil/data/<feature>/`: 49 integrações e cerca de 400 tools MCP. Novas nesta sessão: `siconfi`,
  `lexml`, `noticias` (48 feeds com criticidade), `clima` (NOAA ENSO, Open-Meteo, INMET, USGS,
  NASA EONET e `local.py` com risco por bairro), `vigilancia` (InfoDengue e surtos), `alimentos` (IPCA SIDRA
  7060) e `mundo` (Frankfurter e Banco Mundial).
- `src/mcp_brasil/radar/`: camada comercial, ativada com `MCP_BRASIL_AUTH_MODE=radar`:
  - acesso e cobrança: `store.py` (usuários, chaves, assinaturas, temas, preferências de alerta),
    `servico.py`, `mercadopago.py`, `auth.py` (verificação das chaves `rb_...` e limite diário);
  - rotas e telas: `rotas.py`, `portal.html` (`/conta`), `painel.html` (`/painel`), `clima.html` (`/clima`);
  - dados e alertas: `coletor.py`, `indicadores.py` (`indicadores.db`, público), `alertas.py`,
    `notificadores.py` (Telegram, Evolution e Meta);
  - `__main__.py`: linha de comando (`criar-admin`, `conceder`, `usuarios`, `criar-chave`,
    `redefinir-senha`, `coletar`, `whatsapp status|conectar|teste`).
- O coletor e os alertas rodam **dentro do processo web** desde o boot (`coletor_lifespan`, composto em `server.py`).
- Deploy: `Dockerfile` (usuário sem privilégios, venv no PATH), `docker-compose.yml` com `argos` e `caddy`
  (perfis opcionais `whatsapp` e `relatorios`), `deploy/Caddyfile`, e `scripts/`
  (`instalar_vps.sh`, `verificar.sh`, `backup.sh`, `atualizar.sh`).
  Roteiro de instalação: `docs/deploy/HANDOFF_VPS.md`. O `CLAUDE.md` aponta para ele.
- RAM medida: cerca de **190 MB** no processo `argos`, com tudo carregado.

## Decisões tomadas (não rediscutir sem motivo)

- WhatsApp: **Evolution API** como padrão. A API oficial da Meta está pronta, mas fica para a próxima versão
  (`WHATSAPP_PROVEDOR=meta`). O usuário já foi avisado do risco de banimento: chip exclusivo, opt-in por código
  e pausa de 3 s entre envios.
- Metabase: **desligado** (perfil `relatorios`). Consultas prontas em `docs/metabase/consultas.sql`.
- Banco: SQLite, com `radar.db` privado e `indicadores.db` público.
- Precisão climática: o polígono oficial do INMET é a camada mais precisa. Os modelos têm resolução de 9 a 25 km,
  e isso aparece de forma transparente no painel.
- Preços de mercado de Dourados: não existe API, por isso há uma **pesquisa própria** (tabela `precos_mercado`).
  O IPCA usa Campo Grande como referência regional.
- Planos padrão provisórios: Essencial R$ 49,90, Profissional R$ 149,90 e Empresarial R$ 499,90 (`RADAR_PLANOS`).

## Pendências e pontos de atenção

- **Build Docker nunca foi executado.** O sandbox não tem daemon Docker. O primeiro build vai ser na VPS.
- **Open-Meteo:** o plano gratuito não permite uso comercial, então é preciso `OPEN_METEO_API_KEY`. Sem a chave,
  o radar local usa o MET Norway (sem rajadas nem CAPE).
- **Envios reais nunca testados:** Evolution, Telegram e Mercado Pago foram testados só com mocks e respx;
  faltam as credenciais.
- Do sandbox não deu para validar: LexML (bloqueio anti-robô do Senado) e Overpass (lista de bairros).
  Nos dois casos o código degrada com mensagem clara.
- Fontes descartadas: OPAS (403), OMS GHO (500), AwesomeAPI e CoinGecko (cota), CONAB (TLS inválido), GDELT.
- O aeroporto de Dourados (SBDO) não transmite METAR; a estação mais próxima é Ponta Porã (SBPP, cerca de 96 km).
- Não existe: recuperação de senha pelo cliente (só a CLI `redefinir-senha`) nem alertas por bairro.
  Os alertas por bairro (polígono do INMET mais modelos) foram sugeridos como próximo passo.
- Abrir PR só se o usuário pedir.

## Armadilhas do ambiente (sandbox do Claude Code)

- Não existe Docker daemon; `docker compose config` funciona para validar o arquivo.
- O endereço de saída é compartilhado e estoura cotas (Open-Meteo diário, AwesomeAPI, CoinGecko). Isso não acontece numa VPS própria.
- Nunca use `pkill -f "<padrão>"` quando o padrão também aparece na própria linha de comando: isso mata o shell.
- O formatador (`ruff format`) reescreve trechos. Antes de editar com substituição de texto, confira o arquivo atual.
- Para subir o servidor local e tirar prints:
  ```bash
  export MCP_BRASIL_AUTH_MODE=radar RADAR_DB_PATH=<scratch>/radar2.db RADAR_INDICADORES_DB=<scratch>/ind.db \
         RADAR_SECRET_KEY=teste RADAR_COLETOR_EMBUTIDO=0 MCP_BRASIL_BASE_URL=http://127.0.0.1:8091
  .venv/bin/python -c "from mcp_brasil.server import mcp; mcp.run(transport='streamable-http', host='127.0.0.1', port=8091)"
  # admin local de teste: admin@argos.test / senha-forte-1 (só no banco do scratchpad)
  ```
  Prints com Playwright (`require('playwright')`, `chromium.launch()`): definir `radar_sessao` e
  `argos_clima` no localStorage via `addInitScript` e esperar `#riscos .card`.

## Último export (04/11/2026, 13:21, bairro Monte Carlo, Dourados/MS)

Resumo completo em `memory/exports/2026-11-04-monte-carlo-dourados.md`.
- INMET: **Tempestade em Perigo hoje, com o ponto dentro do polígono**, e Perigo Potencial de 05 a 07/11.
- Modelos: tempestade em **Grande Perigo** (cálculo próprio; CAPE de 4.180 J/kg, trovoada e granizo por volta das 13h),
  ventania em Perigo Potencial (56–58 km/h) e calor em Perigo Potencial (sensação de 38 °C em 06/11).
- METAR SBPP: 33 °C. Nenhum foco de queimada em 50 km.
