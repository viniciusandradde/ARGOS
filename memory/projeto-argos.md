# Memória do projeto ARGOS

Estado consolidado em **04/11/2026** (tarde: app Android 1.0.0; noite: instalação via Tailscale). Atualize este arquivo ao fechar cada etapa.

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
  8. `a5a6f67` CLAUDE.md versionado + esta memória
  9. (este) app Android 1.0.0 + vigia de alertas + ícone premium + licença VSA
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

## App Android (`mobile/`)

- Capacitor 8.5.3, appId `br.com.vsa.argos`. **Motor local em JS** (`www/js/motor.js`), porte do coletor e
  de `clima/local.py`; o celular busca as fontes direto, sem servidor. `CapacitorHttp` nativo evita CORS.
- Telas: SALA, CLIMA, FEED e CONFIG (`www/index.html` e `www/js/app.js`). Os dados ficam no localStorage.
- `www/js/dados.js` é **gerado** a partir das constantes Python (`npm run dados` → `scripts/gerar_dados.py`).
- **Vigia** (`www/runners/vigia.js`), via Background Runner 3.0.0 / WorkManager, roda a cada ~15 min mesmo com o app fechado:
  - canais `argos_urgente` (push com som e vibração) e `argos_boletim` (1× por manhã, hora configurável, padrão 7 h);
  - urgente = INMET Perigo ou Grande Perigo (cidades pelo geocódigo, ou ponto dentro do polígono), risco
    iminente ≥ Perigo em 12 h no ponto do radar, surto crítico (OMS, ECDC, ONU, AB Saúde) e temas 🔔;
  - deduplicação de 8 dias; no máximo 6 notificações por rodada, o resto agrupado; o boletim tem prioridade;
  - o app envia a configuração ao vigia com `dispatchEvent('configurar')`; ele roda sem DOM (RSS por regex).
- Ícone premium: `mobile/marca/argos-icone.svg`, renderizado com `node scripts/gerar_icones.js`
  (mipmaps, ícone adaptativo, splash e favicon). A web também usa o ícone em `/icone.png`.
- APK: `bash mobile/scripts/gerar_apk.sh` → `mobile/releases/argos-X.Y.Z.apk`, `argos-ultima.apk` e `.sha256`.
  A versão vem do `mobile/package.json`. Assinatura: `mobile/assinatura/argos-sideload.jks` + `assinatura.properties`,
  **fora do Git** (o classificador bloqueou o commit da chave). Cert SHA-256 30:d4:19…dd:94:7b. Sem a mesma chave,
  a atualização não instala por cima. Restaurar via secret `ARGOS_KEYSTORE_B64` (ver LEIA-ME da pasta).
- Testes offline do vigia: `cd mobile && npm test` (node:test, fetch mockado).
- Licença: `LICENCA-ARGOS.md` (proprietária, VSA Soluções em Tecnologia) para radar/, mobile/, deploy e marca.
  O código do mcp-brasil continua MIT (`LICENSE` intacto). O modelo de licença precisa de revisão jurídica e
  dos dados da empresa (CNPJ, endereço).

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

- **Instalado em 04/11/2026 na VPS compartilhada** com `--tailscale`: acesso só pela tailnet, na porta 8062, porque as
  portas 80/443 são do Traefik do Dokploy. Sem Evolution e sem Metabase. O `.env` é `root:600`, então `docker compose`
  exige sudo; `docker exec argos-argos-1 ...` funciona sem root.
- Chaves de conta sem plano ativo recebem 401 no `/mcp`. Admin não precisa de plano.
- **ufw ligado pelo instalador em 04/11/2026 às 13:09** (entrada em DROP, só SSH/80/443), o que atinge serviços do host
  como o Samba (139/445). Portas publicadas pelo Docker não são afetadas. O usuário decide se mantém.
- **Open-Meteo:** o plano gratuito não permite uso comercial, então é preciso `OPEN_METEO_API_KEY`. Sem a chave,
  o radar local usa o MET Norway (sem rajadas nem CAPE).
- **Envios reais nunca testados:** Evolution, Telegram e Mercado Pago foram testados só com mocks e respx;
  faltam as credenciais.
- Do sandbox não deu para validar: LexML (bloqueio anti-robô do Senado) e Overpass (lista de bairros).
  Nos dois casos o código degrada com mensagem clara.
- Fontes descartadas: OPAS (403), OMS GHO (500), AwesomeAPI e CoinGecko (cota), CONAB (TLS inválido), GDELT.
- O aeroporto de Dourados (SBDO) não transmite METAR; o METAR mais próximo é Ponta Porã (SBPP, cerca de 96 km).
- **Fontes de temperatura (04/11/2026):** "agora" = Embrapa Guia Clima (raio de 25 km, `api/v1/guiaclima`, tempoReal e
  leituraAtual), depois estação INMET (`estacao/proxima/<geocódigo>`), depois modelo. Previsão diária = INMET
  (`previsao/<geocódigo>`), com Open-Meteo de reserva e faixa ECMWF/ICON/GFS. Esses endpoints **não têm documentação**:
  falta confirmar com a Embrapa e o INMET o uso comercial. A distância informada pelo INMET não é confiável (71 km para
  a estação dentro de Campo Grande), por isso ela é calculada pelas coordenadas.
- Evidência em 04/11/2026: máxima medida 35,4 °C (Embrapa) e 35,5 °C (UFGD); Open-Meteo 33,3, INMET 36, AccuWeather 38.
- **App 1.1.0:** código pronto e compilado com assinatura de depuração, mas o APK final não foi gerado: a chave de
  assinatura não está nesta VPS. `argos-ultima.apk` continua sendo o 1.0.0.
- Build nesta VPS: Android SDK em `~/android-sdk` e JDK 21 em `~/jdk-21` (o Java do sistema não tem `javac`). Rode
  `JAVA_HOME=$HOME/jdk-21 PATH=$HOME/jdk-21/bin:$PATH bash mobile/scripts/gerar_apk.sh`.
- Testes nesta VPS: o `.env` do root quebra `load_dotenv`, então rode o pytest numa cópia sem o `.env`.
- Não existe: recuperação de senha pelo cliente (só a CLI `redefinir-senha`) nem alertas por bairro.
  Os alertas por bairro (polígono do INMET mais modelos) foram sugeridos como próximo passo.
- App: o vigia nunca rodou num aparelho real (só em Node com shims e no navegador). Validar no celular:
  permissões, notificações com o app fechado e otimização de bateria do fabricante.
- App: a coleta completa (8 etapas) só roda com o app aberto; com ele fechado roda apenas o vigia (alertas e boletim).
- Abrir PR só se o usuário pedir.

## Armadilhas do ambiente (sandbox do Claude Code)

- Android SDK não vem instalado: baixar commandlinetools em `/root/android-sdk` e instalar
  `platforms;android-36` e `build-tools;36.0.0`. O Maven Central devolve 429: usar o init script
  `~/.gradle/init.d/espelho.gradle` (espelho do Google `maven-central.storage-download.googleapis.com`).
- A CARTO passou a exigir chave: o mapa usa tiles do OSM com o filtro de inversão (igual à web).
- Prints do app: servir `mobile/www` (`python3 -m http.server`) e abrir no Playwright com
  `--disable-web-security` e `devices["Pixel 7"]`.
- A ferramenta Write converteu `\u0300` em caracteres reais; escreva intervalos Unicode em regex com escape.

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
