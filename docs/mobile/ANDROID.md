# ARGOS para Android

App nativo (Capacitor 8) com o mesmo visual da sala de situação web. **Roda 100% no celular**: o
próprio aparelho coleta as fontes públicas, sem servidor e sem assinatura. A versão web (VPS)
continua igual e independente.

| | Web (VPS) | Android |
|---|---|---|
| Onde roda | servidor `argos` + Caddy | no próprio celular |
| Coleta | coletor embutido a cada 15 min → `indicadores.db` | motor JS no aparelho (abrir/voltar ao app e a cada N min) |
| Usuários e cobrança | portal `/conta` + Mercado Pago | não tem (uso pessoal) |
| Alertas | Telegram e WhatsApp (Evolution) | **notificações locais**: urgentes + boletim da manhã |
| Dados | SQLite | `localStorage` do app (só no aparelho) |

## Baixar e instalar

1. No celular, abra o link do APK (versionado no repositório):
   `mobile/releases/argos-ultima.apk` (sempre a última) ou `mobile/releases/argos-X.Y.Z.apk`.
   Sem login no GitHub, um repositório privado não abre. Nesse caso, mande o APK por WhatsApp ou e-mail para si mesmo.
2. Toque no arquivo baixado. O Android pede para **permitir a instalação deste app de origem
   desconhecida** (Chrome / Arquivos → Permitir).
3. Abra o ARGOS e autorize **notificações** e, se quiser usar o botão 📍, **localização**.
4. Em celulares Xiaomi, Samsung, Motorola etc., para os alertas chegarem com o app fechado:
   Configurações → Apps → ARGOS → Bateria → **Sem restrições**. Mais detalhes por fabricante em
   [dontkillmyapp.com](https://dontkillmyapp.com).

Para conferir a integridade do arquivo, compare o hash publicado em `argos-X.Y.Z.apk.sha256`:

```bash
sha256sum argos-1.0.0.apk
```

## Telas

- **SALA**: El Niño (NOAA), clima das cidades e avisos INMET, arboviroses (InfoDengue), radar de surtos,
  alertas críticos, IPCA de alimentos, pesquisa própria de preços (salva no aparelho), câmbio, sismos e status das coletas.
- **CLIMA**: radar climático local por município e bairro, igual ao `/clima` da web. Inclui mapa, polígono oficial do INMET,
  riscos em 48 h, METAR, focos de queimada, gráficos e consenso entre modelos. Toque no mapa ou use 📍 para escolher o ponto exato.
- **FEED**: 48 fontes com filtros e abas por tema.
- **CONFIG**: cidades monitoradas, temas (🔔 = alerta), notificações, hora do boletim,
  localidades do IPCA e chave Open-Meteo.

## Alertas no celular: política

O "vigia" (`www/runners/vigia.js`) roda em segundo plano pelo WorkManager do Android a cada ~15 minutos,
**mesmo com o app fechado**. Ele usa dois canais de notificação, configuráveis em Ajustes do Android:

| Canal | Quando | Como chega |
|---|---|---|
| 🔴 **ARGOS · Alertas urgentes** | a qualquer hora, assim que detectado | push com som, vibração e luz vermelha |
| ☀ **ARGOS · Boletim da manhã** | 1× por dia, na primeira checagem depois da hora escolhida (padrão 07:00) | discreto, sem vibrar |

**O que é urgente** (cada item pode ser ligado ou desligado em CONFIG):

1. **Aviso do INMET** de nível *Perigo* ou *Grande Perigo* que cubra uma cidade monitorada (pelo
   geocódigo IBGE) ou o **ponto do radar climático** (teste ponto-no-polígono). *Perigo Potencial*
   não dispara push e entra só no boletim.
2. **Risco iminente** nas próximas 12 h, no ponto do radar, calculado pelos modelos com os limiares do INMET e da NOAA:
   - rajadas a partir de 60 km/h;
   - chuva a partir de 30 mm/h;
   - sensação térmica a partir de 41 °C;
   - trovoada com CAPE a partir de 1500 J/kg.
3. **Surto ou emergência sanitária**: notícia *crítica* com termo de surto (Marburg, H5N1, cólera, sarampo…)
   publicada pela OMS, ECDC, ONU Saúde ou Agência Brasil Saúde.
4. **Temas com 🔔**: qualquer notícia nova que bata com os termos do tema.
5. Opcional: **toda notícia crítica**. Desligado por padrão, porque são dezenas por dia.

**Boletim da manhã:**

- **Clima hoje:** previsão de cada cidade (mín/máx, condição, chance e volume de chuva, rajadas).
- **Avisos INMET** vigentes nas suas cidades, por tipo e nível.
- **Arboviroses** em nível amarelo ou acima, com Rt quando a transmissão está em alta.
- **El Niño:** o ONI mais recente.
- **Dólar** do dia.
- **Notícias críticas** das últimas 24 h, até 3 títulos.

**Regras anti-spam:** cada alerta é enviado **uma única vez** (deduplicação de 8 dias). Os riscos de
modelo valem um por tipo por dia. A cada rodada vão no máximo 6 notificações, e o excesso vira uma
notificação agrupada "⚠ +N alertas".

> O Android pode adiar o vigia em economia de bateria ou modo soneca. O intervalo de 15 minutos é o
> mínimo permitido pelo sistema, não uma garantia. Para alertas críticos de vida, mantenha também
> os canais oficiais: Defesa Civil por SMS (envie seu CEP para **40199**) e o alerta de emergência do celular.

Botão **[ENVIAR BOLETIM AGORA + CHECAR ALERTAS]** em CONFIG: executa o vigia na hora, para testar.

## Gerar uma nova versão do APK

Pré-requisitos: Node 22, JDK 21 e Android SDK (platform 36 e build-tools 36).

```bash
cd mobile
npm install
npm run dados          # regenera www/js/dados.js a partir das constantes Python (fontes, IPCA, municípios)
npm test               # testes offline do vigia
# altere "version" no package.json (ex.: 1.0.1) e então:
bash scripts/gerar_apk.sh
```

O script sincroniza a versão (versionCode = MAJOR·10000 + MINOR·100 + PATCH), compila o release e assina
com a chave de `mobile/assinatura/`. A chave **fica fora do Git**; veja `mobile/assinatura/LEIA-ME.md`. Em seguida grava `releases/argos-X.Y.Z.apk`, `releases/argos-ultima.apk` e o
`.sha256`. **Sempre use a mesma chave**: o Android só atualiza por cima se a assinatura for igual.

Para trocar o ícone, edite `mobile/marca/argos-icone.svg` e rode `node scripts/gerar_icones.js`. O
script gera os mipmaps, o ícone adaptativo, o splash e os favicons.

## Licença

© 2026 VSA Soluções em Tecnologia. Software proprietário, conforme `LICENCA-ARGOS.md`. O código
de origem mcp-brasil continua sob a licença MIT (`LICENSE`).
