# Radar Brasil — vendendo acesso ao servidor

O modo **Radar Brasil** (`MCP_BRASIL_AUTH_MODE=radar`) transforma o servidor MCP em um
produto pago:

- **Portal do cliente** em `/conta`, com cadastro, login, contratação de plano, chaves de API e histórico de pagamentos.
- **Chaves de API por cliente**: cada cliente conecta o assistente de IA ao endpoint `/mcp`
  com `Authorization: Bearer rb_...`. Uma chave só funciona enquanto o plano estiver em dia.
- **Planos com limite diário de consultas**, aplicado a cada chamada de tool.
- **Pagamentos pelo Mercado Pago**:
  - *Assinatura mensal* no cartão, com renovação automática (API de assinaturas `/preapproval`).
  - *Pagamento avulso de 30 dias* com Pix, boleto ou cartão (Checkout Pro).
- **Webhook** em `/webhooks/mercadopago`, que libera, renova ou corta o acesso sozinho.
- **Administração** pelo portal (para usuários `admin`) ou pela linha de comando.

## Como funciona

```
Cliente ──► /conta (portal) ──► escolhe plano ──► Mercado Pago (cartão / Pix / boleto)
                                                        │
                       /webhooks/mercadopago ◄──────────┘  (pagamento aprovado)
                                │
                     libera 30 dias de acesso
                                │
Assistente de IA ──► /mcp  +  Authorization: Bearer rb_...  ──► 45+ APIs do governo
```

O servidor **nunca confia no conteúdo do webhook**. Ao receber uma notificação, ele busca o
pagamento ou a assinatura direto na API do Mercado Pago com o seu Access Token e só então
libera o acesso. Antes de creditar, confere o valor e a moeda. Cada pagamento é creditado uma única vez, mesmo
que a notificação chegue repetida. Em caso de estorno ou contestação, os dias correspondentes
são removidos.

## 1. Credenciais do Mercado Pago

1. Acesse [Suas integrações](https://www.mercadopago.com.br/developers/panel/app) e crie uma
   aplicação. Em "Qual produto você está integrando?", escolha **Pagamentos online**, com
   Checkout Pro e Assinaturas.
2. Em **Credenciais de teste**, copie o *Access Token* (`TEST-...`). Use-o até validar todo
   o fluxo. Depois, troque pelo Access Token de **produção** (`APP_USR-...`).
3. Em **Webhooks → Configurar notificações**:
   - URL de produção: `https://SEU-DOMINIO/webhooks/mercadopago`
   - Eventos: **Pagamentos** e **Planos e assinaturas**
   - Salve e copie a **assinatura secreta**. Ela vai em `MERCADOPAGO_WEBHOOK_SECRET`.

> Na assinatura recorrente, o Mercado Pago exige que o cliente pague logado com **o mesmo
> e-mail** cadastrado no Radar. O pagamento avulso (Pix/boleto) não tem essa restrição.

## 2. Variáveis de ambiente

```bash
MCP_BRASIL_AUTH_MODE=radar
MCP_BRASIL_BASE_URL=https://radar.seudominio.com.br   # URL pública, com HTTPS
RADAR_SECRET_KEY=...            # python -c "import secrets; print(secrets.token_urlsafe(32))"
RADAR_DB_PATH=/app/data/radar.db
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_WEBHOOK_SECRET=...

# Opcionais
RADAR_PLANOS='[{"id":"essencial","nome":"Essencial","preco":49.9,"consultas_dia":300}]'
RADAR_CARENCIA_DIAS=3     # tolerância após o vencimento (atrasos na renovação)
RADAR_TESTE_DIAS=0        # dias grátis no cadastro (0 = sem teste)
RADAR_PLANO_TESTE=essencial

# Chaves das APIs do governo que exigem cadastro (recomendado preencher)
TRANSPARENCIA_API_KEY=...
DATAJUD_API_KEY=...
DADOS_GOV_BR_API_KEY=...
```

### Planos padrão

| ID | Nome | Preço/mês | Consultas/dia |
|----|------|-----------|---------------|
| `essencial` | Essencial | R$ 49,90 | 300 |
| `profissional` | Profissional | R$ 149,90 | 2.000 |
| `empresarial` | Empresarial | R$ 499,90 | 20.000 |

Para mudar preços ou limites, defina `RADAR_PLANOS` com um JSON. Cada plano aceita os campos
`id`, `nome`, `preco`, `consultas_dia`, `dias` (padrão 30) e `descricao`.

## 3. Subir o servidor

```bash
cp .env.example .env   # preencha as variáveis acima
docker compose up -d --build
```

O `docker-compose.yml` monta o volume `radar-data` em `/app/data`. Sem esse volume, o banco
de usuários e pagamentos seria perdido a cada novo deploy.

Coloque o servidor atrás de um proxy com HTTPS (Caddy, Nginx, Cloudflare). O Mercado Pago só
envia webhooks para URLs públicas.

## 4. Criar o administrador

```bash
docker compose exec mcp-brasil uv run python -m mcp_brasil.radar criar-admin --email voce@exemplo.com
```

Outros comandos:

```bash
python -m mcp_brasil.radar usuarios                                   # lista clientes e situação
python -m mcp_brasil.radar conceder --email x@y.com --plano profissional --dias 30
python -m mcp_brasil.radar criar-chave --email x@y.com --nome "Integração"
python -m mcp_brasil.radar redefinir-senha --email x@y.com
```

Administradores têm acesso ilimitado e veem a seção **Administração** no portal. Por lá dá para
conceder dias de acesso (cortesia, parceiros, testes) e desativar contas.

## 5. Como o cliente conecta

Depois de pagar, o cliente gera uma chave em `/conta` e configura o assistente de IA.

**Claude Code**

```bash
claude mcp add --transport http radar-brasil https://radar.seudominio.com.br/mcp \
  --header "Authorization: Bearer rb_..."
```

**Claude Desktop / Cursor / VS Code** (qualquer cliente MCP com HTTP e cabeçalhos):

```json
{
  "mcpServers": {
    "radar-brasil": {
      "type": "http",
      "url": "https://radar.seudominio.com.br/mcp",
      "headers": { "Authorization": "Bearer rb_..." }
    }
  }
}
```

## 6. Testar antes de vender

1. Use o Access Token de **teste** e crie [usuários de teste](https://www.mercadopago.com.br/developers/panel/test-users)
   (um vendedor e um comprador).
2. Cadastre no Radar o e-mail do comprador de teste e faça uma compra avulsa com os
   [cartões de teste](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/additional-content/your-integrations/test/cards).
3. Confira no log a linha `Webhook payment/...: creditado até AAAA-MM-DD`. No portal, o
   acesso deve aparecer como ativo.
4. Para testar o webhook em ambiente local, exponha a porta com um túnel (`cloudflared tunnel`, `ngrok`)
   e use a URL do túnel em `MCP_BRASIL_BASE_URL` e no painel do Mercado Pago.

## Endpoints

| Método | Caminho | Autenticação | Descrição |
|--------|---------|--------------|-----------|
| GET | `/` e `/conta` | — | Portal do cliente |
| GET | `/api/planos` | — | Planos e se os pagamentos estão ativos |
| POST | `/api/cadastro` | — | `{email, senha, nome}` → sessão |
| POST | `/api/login` | — | `{email, senha}` → sessão |
| GET | `/api/eu` | sessão | Conta, plano, uso do dia, chaves e pagamentos |
| POST | `/api/senha` | sessão | `{atual, nova}` |
| POST | `/api/chaves` | sessão | Gera chave (exibida uma única vez) |
| DELETE | `/api/chaves/{id}` | sessão | Revoga chave |
| POST | `/api/cobranca/checkout` | sessão | `{plano, modo: "assinatura" \| "avulso"}` → `{url}` |
| POST | `/api/cobranca/cancelar` | sessão | Cancela a renovação; o acesso continua até o fim do período pago |
| POST | `/webhooks/mercadopago` | assinatura `x-signature` | Notificações do Mercado Pago |
| GET | `/api/admin/usuarios` | sessão admin | Lista clientes |
| PATCH | `/api/admin/usuarios/{id}` | sessão admin | `{ativo?, papel?, conceder_plano?, dias?}` |
| GET | `/api/admin/pagamentos` | sessão admin | Últimos pagamentos |
| POST | `/mcp` | `Bearer rb_...` | Endpoint MCP (tools das APIs do governo) |

A sessão do portal vai no cabeçalho `X-Radar-Sessao`.

## Limitações atuais e próximos passos

- **Banco SQLite**: atende bem uma única instância. Para rodar várias réplicas, troque
  `radar/store.py` por PostgreSQL (a interface da classe `Store` foi pensada para isso).
- **Sem confirmação de e-mail nem "esqueci minha senha"**. Por enquanto, o administrador
  redefine a senha com `python -m mcp_brasil.radar redefinir-senha`. Para a recuperação
  pelo próprio cliente falta integrar um serviço de envio de e-mail.
- **Limite diário** zera à meia-noite UTC (21h no horário de Brasília).
- Os alertas automáticos (monitoramento agendado com aviso por e-mail ou WhatsApp) ainda não
  existem. Esta camada só cuida de acesso e cobrança.
