# ARGOS — sala de situação, coletor e Metabase

> **ARGOS**, de Argos Panoptes, o gigante de cem olhos da mitologia grega que via tudo.
> É o nome padrão do produto e pode ser trocado com `RADAR_NOME`.

Este guia complementa o [guia comercial](radar-brasil.md), que trata de usuários, planos e Mercado Pago.

## Arquitetura (simples de propósito)

```
               ┌────────────── coletor (a cada 15 min) ───────────────┐
 NOAA · OMS · ECDC · ONU · INMET · InfoDengue · IBGE · BCE · USGS · 48 feeds RSS
               └──────────────────────────┬───────────────────────────┘
                                          ▼
                              indicadores.db (SQLite)
                     ┌────────────────────┼─────────────────────┐
                     ▼                    ▼                     ▼
          /painel (sala de situação)   Metabase (relatórios)   tools MCP
           tempo real, por assinante    histórico, BI            assistente de IA
```

- **Sem filas, sem Kafka, sem Postgres obrigatório.** Um processo coleta, um arquivo SQLite guarda
  os dados, a sala de situação e o Metabase leem esse arquivo.
- **Bancos separados:** `radar.db` guarda usuários, chaves e pagamentos e é privado.
  `indicadores.db` guarda só dados públicos e é o único que o Metabase enxerga.

## Sala de situação (`/painel`)

A tela tem visual de terminal e se atualiza sozinha a cada 60 segundos. É exclusiva para
assinantes ativos (ou administradores).

| Painel | Fonte | O que mostra |
|---|---|---|
| El Niño | NOAA Climate Prediction Center | Status oficial (Watch/Advisory), ONI, Niño 3.4 e 1+2 semanais, sinopse, impactos no Brasil |
| Biovigilância | InfoDengue (Fiocruz/FGV) | Dengue, chikungunya e zika por município: nível 1–4, casos, Rt |
| Radar de surtos | OMS, ECDC, ONU, Guardian, STAT, Lancet, BBC, NYT | Notícias de surtos, epidemias e pandemias |
| Alertas críticos | 48 feeds | Letreiro e lista de notícias classificadas como críticas |
| Clima | Open-Meteo + INMET | Tempo atual e previsão de 5 dias; avisos do INMET, com destaque para a sua região |
| Alimentos | IPCA/IBGE (tabela 7060) | Variação mensal e em 12 meses dos principais itens da mesa |
| Preços nos mercados | Pesquisa própria | Média, mínimo e máximo por produto, registrados pela equipe |
| Câmbio | BCE (Frankfurter) | USD/BRL, EUR/BRL e outras moedas, com gráfico de 60 dias |
| Sismos | USGS | Terremotos de magnitude 4,5 ou mais na semana, com alerta de tsunami |
| Feed global | 48 feeds | Filtros por termo, Brasil/mundo, categoria e nível; uma aba por tema |
| Configuração | — | Criação e remoção de temas monitorados |
| Status das coletas | — | Última execução de cada etapa do coletor (OK ou falha) |

### Temas e filtros por usuário

Cada usuário cria até 20 temas. Um tema é um filtro salvo com:

- **termos:** casa se *qualquer* termo aparecer no título ou no resumo, sem diferenciar acentos nem maiúsculas;
- **excluir:** descarta a notícia se *qualquer* desses termos aparecer;
- **categorias:** geral, política, economia, saúde, epidemias, clima, desastres, justiça, legislativo e governo;
- **escopo:** Brasil, mundo ou ambos;
- **nível mínimo:** normal, alto ou crítico.

Cada tema vira uma aba no feed. Exemplos: "Gripe aviária" (`h5n1, bird flu, gripe aviária`),
"Reforma tributária" (`IBS, CBS, reforma tributária` excluindo `futebol`), "Agro MS" (`soja, milho, boi, Dourados`).

### Criticidade

Cada notícia recebe um nível pela presença de palavras-chave em português e inglês
(veja `data/noticias/criticidade.py`):

- 🔴 **crítico:** pandemia, surto, epidemia, Ebola, H5N1, terremoto, tsunami, enchente, desastre, guerra, "aviso de tempestade";
- 🟠 **alto:** alerta, dengue, zika, chikungunya, seca, queimadas, El Niño, inflação, Selic, juros, crise.

A regra é simples e previsível, mas gera falsos positivos (por exemplo, "surto psicótico").
Para refinar, edite as listas no arquivo ou use **excluir** nos temas.

### Pesquisa de preços (Dourados e qualquer cidade)

Não existe API pública com preços dos mercados de Dourados. O IBGE só pesquisa capitais, e Campo Grande é a
referência regional mostrada no painel de alimentos. Por isso o ARGOS tem uma **pesquisa própria**:

- qualquer assinante registra produto, mercado, preço, unidade e data;
- o painel mostra média, mínimo, máximo e número de mercados dos últimos 30 dias;
- os dados ficam em `precos_mercado` e aparecem no Metabase (consultas 7 e 8 de `docs/metabase/consultas.sql`).

A cidade padrão é a primeira de `RADAR_CIDADES`.

## Coletor

```bash
python -m mcp_brasil.radar coletar                      # uma rodada, todas as etapas
python -m mcp_brasil.radar coletar --etapas enso,noticias
python -m mcp_brasil.radar coletar --loop               # a cada RADAR_COLETA_MINUTOS
```

| Etapa | Fonte | Frequência real da fonte |
|---|---|---|
| `noticias` | 48 feeds RSS/Atom | minutos |
| `enso` | NOAA CPC | semanal (Niño), mensal (ONI e discussão oficial) |
| `arboviroses` | InfoDengue | semanal |
| `alimentos` | IBGE/SIDRA | mensal |
| `cambio` | BCE/Frankfurter | diária (dias úteis) |
| `clima` | Open-Meteo | horária |
| `avisos_inmet` | INMET | minutos |
| `terremotos` | USGS | minutos |

Uma etapa que falha não interrompe as outras. A falha fica registrada em `coletas` e aparece no painel.
Sem um serviço separado, o próprio servidor web roda o coletor (`RADAR_COLETOR_EMBUTIDO=1`, padrão).

### Configuração

```bash
RADAR_NOME=ARGOS
RADAR_INDICADORES_DB=/indicadores/indicadores.db
RADAR_CIDADES=Dourados/MS,Campo Grande/MS        # clima + arboviroses (a 1ª é a cidade da pesquisa de preços)
RADAR_ALIMENTOS_LOCALIDADES=brasil,campo_grande  # IPCA: brasil + 16 capitais
RADAR_AREA_INMET=Mato Grosso do Sul              # avisos do INMET em destaque
RADAR_COLETA_MINUTOS=15
RADAR_COLETOR_EMBUTIDO=1                         # 0 quando o serviço "coletor" está rodando
```

## Metabase (relatórios)

O `docker-compose.yml` já sobe o Metabase na porta 3000.

1. Abra `http://SEU-SERVIDOR:3000` e crie o usuário administrador do Metabase.
2. **Adicionar banco de dados → SQLite**, com o caminho `/indicadores/indicadores.db`.
3. Crie as perguntas a partir de `docs/metabase/consultas.sql`: El Niño (ONI e semanal), arboviroses,
   alimentos, preços de Dourados, câmbio, volume de notícias por criticidade e saúde do coletor.
4. Monte um painel "ARGOS — relatório semanal" e, se quiser, ative o envio por e-mail ou Slack
   (recurso nativo do Metabase).

**Por que Metabase?** Ele é de código aberto, gratuito para hospedar, lê SQLite direto, permite que pessoas
sem SQL montem gráficos e envia relatórios agendados. O Grafana é melhor para métricas de segundo a segundo,
mas aqui os dados mudam em minutos ou semanas, e o tempo real fica com a sala de situação do próprio ARGOS.
Se o volume crescer muito, troque o SQLite por PostgreSQL: o Metabase continua igual.

## Tools MCP novas

Estas tools ficam disponíveis no assistente de IA conectado ao ARGOS:

- `clima_el_nino`, `clima_previsao_tempo`, `clima_qualidade_ar`, `clima_avisos_inmet`, `clima_terremotos`,
  `clima_eventos_naturais`
- `vigilancia_painel_arboviroses`, `vigilancia_radar_surtos`
- `alimentos_inflacao_alimentos`, `alimentos_historico_alimento`
- `mundo_cotacoes_moedas`, `mundo_historico_cambio`, `mundo_indicador_banco_mundial`
- `noticias_buscar_noticias` (com filtros de escopo, idioma, nível e exclusão) e `noticias_alertas_criticos`

## Fontes testadas e descartadas

| Fonte | Motivo |
|---|---|
| OPAS/PAHO (RSS) | Bloqueia acesso automatizado (HTTP 403) |
| OMS GHO (API) | Erro 500 recorrente |
| AwesomeAPI e CoinGecko | Limite gratuito estourado a partir de IPs compartilhados |
| CONAB (preços agropecuários) | Certificado TLS inválido no servidor de downloads |
| GDELT | Limite de uma requisição a cada 5 segundos e respostas vazias |
| Feeds gov.br (Saúde, Anvisa, Fazenda, MEC) | Inexistentes ou listam pastas no lugar de notícias |
