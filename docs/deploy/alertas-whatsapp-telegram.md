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

## WhatsApp com Evolution API (padrão nesta versão)

A [Evolution API](https://doc.evolution-api.com) roda no seu servidor e conecta um **chip comum de
WhatsApp**, como o WhatsApp Web. Não há template, aprovação da Meta nem custo por mensagem.

> ⚠️ **Não é uma API oficial do WhatsApp.** O número pode ser restrito ou banido se o WhatsApp
> entender que é envio em massa. Para reduzir o risco:
> - use um **chip exclusivo** para o ARGOS (nunca o seu número pessoal ou o da empresa);
> - "aqueça" o número antes, usando-o normalmente por alguns dias;
> - envie só para quem pediu: o ARGOS já exige a confirmação do número por código;
> - mantenha `WHATSAPP_INTERVALO_SEG` em 3 segundos ou mais, e um resumo por rodada (já é o padrão).
>
> A API oficial da Meta já está implementada (`WHATSAPP_PROVEDOR=meta`) e fica para a próxima versão.

### 1. Subir a Evolution API

No `.env`:

```bash
WHATSAPP_PROVEDOR=evolution
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=troque-por-uma-chave-longa      # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
EVOLUTION_INSTANCIA=argos
EVOLUTION_DB_SENHA=troque-esta-senha
```

```bash
docker compose --profile whatsapp up -d --build
```

Isso sobe a `evolution-api` e o banco `evolution-postgres`. A Evolution fica acessível só por dentro
do servidor (`127.0.0.1:8080`) e pela rede interna do Docker.

### 2. Conectar o chip (código de pareamento, sem QR)

```bash
docker compose exec coletor uv run python -m mcp_brasil.radar whatsapp conectar --numero 5567999999999
```

O comando cria a instância `argos` e mostra um **código de pareamento**. No celular do chip, abra
WhatsApp → **Aparelhos conectados** → **Conectar aparelho** → **Conectar com número de telefone**
e digite o código.

Depois confira e faça um teste:

```bash
docker compose exec coletor uv run python -m mcp_brasil.radar whatsapp status    # deve mostrar "open"
docker compose exec coletor uv run python -m mcp_brasil.radar whatsapp teste --numero 5567SEUNUMERO
```

Administradores também podem usar a API: `GET /api/admin/whatsapp` retorna o estado e
`POST /api/admin/whatsapp {"numero": "..."}` gera um novo código de pareamento.

### 3. Uso pelo cliente

No portal, o cliente informa o número. O ARGOS **confere se o número tem WhatsApp**, envia um código
de 6 dígitos e o cliente confirma. O sistema limita a um código por minuto e cinco tentativas por código.
Os alertas chegam como texto formatado (negrito, itálico e links).

### Se o chip desconectar

O celular precisa ficar ligado e com internet só no pareamento, porque a sessão fica na Evolution.
Se o WhatsApp encerrar a sessão, `whatsapp status` deixa de mostrar `open`. Rode `whatsapp conectar`
de novo; os envios que falharem nesse período aparecem no log do coletor.

## WhatsApp com a API oficial da Meta (próxima versão)

O cliente já existe e está testado, mas não é o padrão desta versão. Para usar, defina
`WHATSAPP_PROVEDOR=meta`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` e crie um template de
**Utilidade** chamado `alerta_argos` com `{{1}}` (título) e `{{2}}` (detalhes). Na API oficial, as
quebras de linha do alerta viram " | ", porque a Meta não aceita quebras de linha em parâmetros de template.

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
| WhatsApp (Evolution) | só o chip e o servidor | Não oficial: risco de bloqueio do número; use chip exclusivo e envie só para quem confirmou |
| WhatsApp (Meta, próxima versão) | por conversa iniciada (categoria utilidade) | Oficial, exige template aprovado |

Para diminuir o volume (e o risco no WhatsApp), deixe "Todas as críticas" desligado (já vem assim)
e aumente `RADAR_COLETA_MINUTOS` se precisar.
