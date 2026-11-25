# Integração financeira com o FiscalFlow

Status (2026-11-25): fila offline implementada no app (`mobile/www/js/fiscalflow.js`) e API v1 implementada no FiscalFlow
(ADR-007 do FiscalFlow). Testado ponta a ponta com nota fictícia contra um FiscalFlow local descartável. Não distribuído em APK.

## Como funciona
- Opcional: em COMPRAS → "FiscalFlow (opcional)", o usuário informa o endereço HTTPS e entra com a própria conta. O app guarda
  somente endereço, e-mail e token de sessão; **a senha não é guardada**.
- Ao confirmar uma nota, ela entra na fila IndexedDB `argos-fiscalflow` (banco separado de `argos-compras`) e o app tenta enviar.
  O item só sai da fila após resposta 2xx do servidor.
- Sem rede, 429 ou 5xx: reenvio com backoff exponencial (30 s, dobrando, teto de 6 h), ao voltar a rede ou pelo botão
  "Enviar pendentes agora". 401/403: pede nova conexão e mantém a fila. 409: fica como conflito para revisão no FiscalFlow.
  400/404/413: fica como recusada (não reenvia).
- Payload mínimo (v1): chave fiscal, estabelecimento, data, total em centavos, itens (descrição, quantidade, unidade, total).
  Não envia CPF, XML, URL do QR, dados de cartão. Consumo e baixa de estoque nunca são enviados (não são despesa).
- O FiscalFlow deduplica por usuário + chave fiscal e concilia com transações/cartões existentes, sem criar despesa duplicada.

- Forma de pagamento: o XML da NFC-e é lido em `pag/detPag` (`tPag` 01 dinheiro, 03 crédito, 04 débito, 10–13 vale, 17 Pix, demais
  "outro"; `vTroco` sai do dinheiro; `90` ignorado) e enviada como `payment_methods`. A leitura pela página da SEFAZ não traz pagamento.
- Orçamento: a seção mostra o disponível do mês para uma categoria (padrão "Supermercado", configurável), lido do FiscalFlow.

## Pendências
Teste Playwright cobrindo a fila; revisão de dados reais em `docs/mobile/COMPRAS.md` e
`docs/mobile/consulta-sefaz-ms.png` antes de novas publicações neste repositório público.
