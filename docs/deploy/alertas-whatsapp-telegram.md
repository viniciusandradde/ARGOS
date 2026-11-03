# Alertas por WhatsApp e Telegram

O ARGOS envia alertas para os assinantes que conectarem um canal no portal (**Conta → Alertas**).
A cada rodada do coletor (padrão: 15 min), cada assinante recebe **uma única mensagem-resumo**,
e só quando há novidade. O mesmo item nunca é enviado duas vezes.

## O que pode gerar alerta

O assinante escolhe os tipos no portal:

| Tipo | Padrão | Gatilho |
|---|---|---|
| Temas marcados com 🔔 | ligado | Notícia nova que casa com um tema da sala de situação marcado como "alertar" |
| Surtos e epidemias | ligado | Notícias de saúde/epidemias com termos como surto, outbreak, Ebola, H5N1, sarampo, dengue |
| Todas as críticas | desligado | Qualquer notícia classificada como crítica (volume alto) |
| Arboviroses | ligado | Dengue, zika ou chikungunya em nível laranja ou vermelho nas cidades de `RADAR_CIDADES` (no máximo um alerta por semana epidemiológica) |
| El Niño | ligado | Mudança no status oficial da NOAA (Watch → Advisory → Final...) |
| INMET | ligado | Aviso de "Perigo" ou "Grande Perigo" que cite a região de `RADAR_AREA_INMET` |

Só assinantes com acesso ativo recebem alertas. Ao conectar um canal, o histórico anterior é
ignorado e só chegam novidades.

## Telegram (gratuito, 5 minutos)

1. No Telegram, abra o **@BotFather**, envie `/newbot` e escolha um nome, por exemplo `ARGOS Alertas` / `ArgosAlertasBot`.
2. Copie o token e configure:
   ```bash
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_BOT_USERNAME=ArgosAlertasBot
   ```
3. Reinicie com `docker compose up -d`.

O cliente clica em **Conectar Telegram**, toca em **Iniciar** no bot e volta ao portal para clicar em **Já enviei**.
O vínculo usa um código de uso único no link (`/start <código>`), então o cliente não digita nada.

> O ARGOS lê as mensagens do bot com `getUpdates`. **Não configure webhook** nesse bot; se já
> existir um, remova com `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.

## WhatsApp (API oficial da Meta)

O WhatsApp só permite que empresas iniciem conversas com **templates aprovados**, e a Meta cobra
por conversa de "utilidade" (valores baixos, em centavos por conversa no Brasil; confira a tabela
atual da Meta). APIs não oficiais (Evolution, Z-API, Baileys) violam os termos do WhatsApp e o número
pode ser banido, por isso não são usadas aqui.

1. **Conta:** crie um app do tipo *Business* em [developers.facebook.com](https://developers.facebook.com/apps)
   e adicione o produto **WhatsApp**. Vincule uma conta do **WhatsApp Business** (empresa verificada
   no Meta Business Suite) e um número de telefone que **não** esteja em uso no app do WhatsApp.
2. **Template:** em WhatsApp Manager → Modelos de mensagem → Criar:
   - Categoria: **Utilidade**
   - Nome: `alerta_argos`
   - Idioma: **Português (BR)**
   - Corpo, por exemplo:
     ```
     🛰 {{1}}

     {{2}}

     Você recebe esta mensagem porque ativou alertas no ARGOS.
     ```
   - Envie para aprovação, que costuma levar de minutos a algumas horas. O mesmo template serve para os
     alertas e para o código de verificação.
3. **Token permanente:** em Meta Business Suite → Configurações → Usuários do sistema, crie um usuário
   do sistema, atribua o app e o WhatsApp e gere um token com as permissões `whatsapp_business_messaging`
   e `whatsapp_business_management`.
4. Configure:
   ```bash
   WHATSAPP_TOKEN=EAAG...
   WHATSAPP_PHONE_NUMBER_ID=1234567890   # em WhatsApp → Configuração da API
   WHATSAPP_TEMPLATE=alerta_argos
   WHATSAPP_TEMPLATE_IDIOMA=pt_BR
   ```

O cliente informa o número, recebe um código de 6 dígitos no WhatsApp e confirma no portal.
O sistema limita a um código por minuto e cinco tentativas por código.

## Testar

- No portal: **Enviar alerta de teste**.
- Na linha de comando, uma coleta seguida do envio dos alertas:
  ```bash
  docker compose exec coletor uv run python -m mcp_brasil.radar coletar
  ```
- No log do coletor aparece `Alertas: {'usuarios': N, 'mensagens': M}` a cada rodada.

## Custos e limites

| Canal | Custo | Observações |
|---|---|---|
| Telegram | gratuito | Limite do Telegram: cerca de 30 mensagens por segundo por bot (folgado para este uso) |
| WhatsApp | por conversa iniciada (categoria utilidade) | Uma conversa dura 24h, e vários alertas no mesmo dia contam como uma só |

Para reduzir custo no WhatsApp, deixe "Todas as críticas" desligado (já vem assim) e aumente
`RADAR_COLETA_MINUTOS`.
