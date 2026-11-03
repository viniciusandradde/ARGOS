# HANDOFF — instalar e rodar o ARGOS numa VPS

> **Para o Claude (ou quem for instalar).** Este documento é autossuficiente: siga na ordem.
> Cada passo tem o comando, o resultado esperado e o que fazer se falhar.
> Objetivo: deixar o ARGOS rodando com HTTPS, coletor ativo, administrador criado e backup diário,
> **sem Metabase** e com o menor consumo possível.

## 0. O que vai rodar

| Serviço | Função | RAM típica | Sobe por padrão? |
|---|---|---|---|
| `argos` | Portal, sala de situação (`/painel`), clima local (`/clima`), endpoint MCP (`/mcp`), coletor e alertas (tudo num processo Python) | ~200 MB (limite 512 MB) | **sim** |
| `caddy` | HTTPS automático (Let's Encrypt) e proxy reverso | ~20 MB | **sim** |
| `evolution-api` + `evolution-postgres` | WhatsApp (Evolution API) | ~600 MB | só com `--whatsapp` |
| `metabase` | Relatórios | ~1 GB | **não** (perfil `relatorios`; não instalar agora) |

Os dados ficam em SQLite no volume Docker `argos-data`, com dois arquivos:
- `radar.db`: usuários, chaves e pagamentos;
- `indicadores.db`: dados públicos coletados.

## 1. Requisitos da VPS

- Ubuntu 22.04 ou 24.04 (Debian 12 também serve), com acesso root por SSH.
- **1 vCPU, 1 GB de RAM e 10 GB de disco.** O instalador cria 1 GB de swap se faltar memória.
  Com WhatsApp, use **2 GB de RAM**.
- Portas 80 e 443 livres; o instalador liga o firewall (ufw) só com SSH, 80 e 443.

## 2. Perguntar ao usuário ANTES de começar

Peça, e anote sem repetir segredos no chat:

1. **Domínio** do sistema (ex.: `argos.empresa.com.br`), com registro **A** já apontando para o IP da VPS.
   Sem domínio, dá para instalar e acessar por `http://IP` e adicionar o domínio depois.
2. **E-mail do administrador** (login do portal).
3. Opcionais, que também podem entrar depois no `.env`:
   - Mercado Pago: `MERCADOPAGO_ACCESS_TOKEN` (comece com o de teste `TEST-...`) e `MERCADOPAGO_WEBHOOK_SECRET`;
   - Telegram: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_BOT_USERNAME` (criados no @BotFather);
   - WhatsApp pela Evolution API: sim ou não (precisa de um chip exclusivo);
   - Open-Meteo: `OPEN_METEO_API_KEY`. **Obrigatório para uso comercial**, porque o plano gratuito é só para uso não comercial. Sem a chave, o sistema funciona e usa o MET Norway como reserva;
   - chaves gratuitas de dados: `TRANSPARENCIA_API_KEY`, `DATAJUD_API_KEY`, `DADOS_GOV_BR_API_KEY`;
   - preços dos planos (`RADAR_PLANOS`) e cidades monitoradas (`RADAR_CIDADES`, padrão `Dourados/MS,Campo Grande/MS`).

## 3. Instalação

```bash
ssh root@IP_DA_VPS
apt-get update -qq && apt-get install -y -qq git
git clone https://github.com/viniciusandradde/mcp-brasil.git /opt/argos
cd /opt/argos
git checkout ccr-d79070a6-p6sovy      # ou "main", se o branch já tiver sido incorporado
```

**Conferir o DNS** (quando houver domínio). Os dois comandos devem mostrar o mesmo IP:

```bash
getent hosts argos.empresa.com.br | awk '{print $1}'
curl -4 -s https://api.ipify.org; echo
```

Se forem diferentes, avise o usuário e instale sem `--dominio` por enquanto (passo 8 adiciona depois).

**Rodar o instalador** (idempotente, pode repetir):

```bash
bash scripts/instalar_vps.sh --dominio argos.empresa.com.br --email admin@empresa.com.br
# sem domínio:      bash scripts/instalar_vps.sh --email admin@empresa.com.br
# com WhatsApp:     acrescente --whatsapp
```

O que ele faz:
1. instala o Docker;
2. cria swap se necessário e configura o firewall;
3. gera o `.env` com segredos aleatórios (`RADAR_SECRET_KEY`, chaves da Evolution), sem sobrescrever valores existentes;
4. faz o build e sobe `argos` e `caddy`;
5. espera o `/health` responder;
6. cria o administrador e salva as credenciais em `/root/argos-credenciais.txt` (permissão 600);
7. agenda o backup diário às 03:17;
8. roda a verificação.

O primeiro build leva de 3 a 8 minutos numa VPS pequena.

**Esperado no final:** `Pronto. Portal: https://argos.empresa.com.br/conta` e a verificação com `[OK]`.

## 4. Preencher as credenciais externas

```bash
cd /opt/argos
nano .env          # preencha as chaves que o usuário forneceu (ver passo 2)
docker compose up -d --force-recreate argos
```

Variáveis principais (todas documentadas no `.env.example`):

```bash
MERCADOPAGO_ACCESS_TOKEN=TEST-...       # depois troque por APP_USR-...
MERCADOPAGO_WEBHOOK_SECRET=...
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_BOT_USERNAME=ArgosAlertasBot
OPEN_METEO_API_KEY=...                  # uso comercial
RADAR_CIDADES=Dourados/MS,Campo Grande/MS
RADAR_AREA_INMET=Mato Grosso do Sul
```

> Nunca mostre o conteúdo do `.env` no chat nem o envie para o Git (ele já está no `.gitignore`).

## 5. Verificar

```bash
bash scripts/verificar.sh
```

Esperado:
- `argos: running healthy` e `caddy: running`;
- `[OK] /health`, `[OK] Portal público ... (HTTP 200)` e `[OK] API de planos`;
- **Coletor**: oito etapas com `[OK]` (`noticias`, `enso`, `arboviroses`, `alimentos`, `cambio`, `clima`, `avisos_inmet`, `terremotos`). A primeira coleta termina cerca de 1 minuto após subir;
- **Memória**: `argos` perto de 200 MB.

Teste manual, ou peça ao usuário para fazer:
1. abrir `https://DOMINIO/conta` e entrar com as credenciais de `/root/argos-credenciais.txt`;
2. trocar a senha;
3. abrir `https://DOMINIO/painel` (sala de situação) e `https://DOMINIO/clima` (radar climático local).

## 6. Mercado Pago (o usuário faz no painel do Mercado Pago)

1. Em [Suas integrações](https://www.mercadopago.com.br/developers/panel/app) → aplicação → **Webhooks**:
   - URL: `https://DOMINIO/webhooks/mercadopago`
   - Eventos: **Pagamentos** e **Planos e assinaturas**
2. Copiar a assinatura secreta para `MERCADOPAGO_WEBHOOK_SECRET` e recriar o container (`docker compose up -d --force-recreate argos`).
3. Teste com credenciais de teste e cartão de teste; o log deve mostrar `Webhook payment/...: creditado`:
   ```bash
   docker compose logs -f argos | grep -i webhook
   ```

## 7. Alertas

**Telegram:** com `TELEGRAM_BOT_TOKEN` preenchido, o cliente conecta em **Conta → Alertas**. Não configure webhook no bot.

**WhatsApp (Evolution API)**, só se o usuário quiser e a VPS tiver 2 GB ou mais:

```bash
docker compose --profile whatsapp up -d
docker compose exec argos python -m mcp_brasil.radar whatsapp conectar --numero 55DDDNUMERODOCHIP
# usuário: WhatsApp do chip → Aparelhos conectados → Conectar com número de telefone → digitar o código
docker compose exec argos python -m mcp_brasil.radar whatsapp status     # esperado: open
docker compose exec argos python -m mcp_brasil.radar whatsapp teste --numero 55DDDNUMERO
```

Riscos e boas práticas: `docs/deploy/alertas-whatsapp-telegram.md`.

## 8. Adicionar o domínio depois (instalação feita só com IP)

```bash
cd /opt/argos
sed -i -E 's|^ARGOS_DOMINIO=.*|ARGOS_DOMINIO=argos.empresa.com.br|; s|^MCP_BRASIL_BASE_URL=.*|MCP_BRASIL_BASE_URL=https://argos.empresa.com.br|' .env
docker compose up -d --force-recreate
bash scripts/verificar.sh
```

## 9. Operação do dia a dia

| Tarefa | Comando |
|---|---|
| Ver logs | `docker compose logs -f argos` |
| Reiniciar | `docker compose restart argos` |
| Atualizar para a versão nova | `bash scripts/atualizar.sh` (faz backup, `git pull`, rebuild e verificação) |
| Backup agora | `bash scripts/backup.sh`, que salva em `/var/backups/argos/*.db.gz` e mantém 14 dias |
| Coletar agora | `docker compose exec argos python -m mcp_brasil.radar coletar` |
| Listar usuários | `docker compose exec argos python -m mcp_brasil.radar usuarios` |
| Dar acesso manual | `docker compose exec argos python -m mcp_brasil.radar conceder --email X --plano profissional --dias 30` |
| Redefinir senha | `docker compose exec argos python -m mcp_brasil.radar redefinir-senha --email X` |
| Uso de memória | `docker stats --no-stream` |

**Restaurar um backup**. Confirme com o usuário antes, porque isso substitui os dados atuais:

```bash
cd /opt/argos
gunzip -k /var/backups/argos/radar-AAAA-MM-DD-HHMM.db.gz
docker compose stop argos
docker compose cp /var/backups/argos/radar-AAAA-MM-DD-HHMM.db argos:/data/radar.db
docker compose start argos
```

## 10. Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| Build morre ou trava em VPS de 1 GB | Falta de memória | Confirme a swap (`swapon --show`); rode o instalador de novo |
| Portal retorna erro de certificado | DNS não aponta para a VPS ou portas 80/443 fechadas no provedor | Confira o DNS (passo 3) e o firewall do provedor; `docker compose logs caddy` |
| `/conta` dá 502 | `argos` não subiu | `docker compose logs argos`; quase sempre é erro de digitação no `.env` |
| Coletor com `[FALHA]` em `clima` | Limite do Open-Meteo gratuito | Configure `OPEN_METEO_API_KEY`; o radar local usa o MET Norway como reserva |
| Coletor com `[FALHA]` em uma etapa isolada | Fonte pública fora do ar | Normal e temporário; as outras etapas continuam. Veja de novo em 15 min |
| Pagamento aprovado mas acesso não liberado | Webhook não chegou ou assinatura inválida | Confira a URL no painel do MP, `MERCADOPAGO_WEBHOOK_SECRET` e `docker compose logs argos \| grep -i webhook` |
| WhatsApp `status` diferente de `open` | Chip desconectou | Rode `whatsapp conectar` de novo |

## 11. Regras para quem estiver instalando

- **Não** exponha as portas 8061, 8080 ou 3000. Só o Caddy (80/443) fica público.
- **Não** suba o perfil `relatorios` (Metabase) sem pedido do usuário.
- **Não** mostre segredos no chat (`.env`, `/root/argos-credenciais.txt`); diga onde estão.
- Peça confirmação antes de qualquer ação destrutiva (`docker volume rm`, restauração de backup, `git reset`).
- Ao terminar, entregue ao usuário:
  1. URL do portal;
  2. onde estão as credenciais;
  3. o que ficou pendente (ex.: webhook do Mercado Pago, token do Telegram);
  4. a saída do `scripts/verificar.sh`.
