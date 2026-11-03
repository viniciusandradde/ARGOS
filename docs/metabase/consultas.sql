-- ============================================================================
-- ARGOS — consultas prontas para o Metabase (banco SQLite indicadores.db)
-- Em Metabase: Novo → Pergunta SQL → cole uma consulta → Visualizar → Salvar
-- ============================================================================

-- 1) El Niño: evolução do ONI e RONI (gráfico de linha)
SELECT ano || '-' || trimestre AS periodo, oni, roni
FROM enso_oni
ORDER BY ano, CASE trimestre WHEN 'DJF' THEN 1 WHEN 'JFM' THEN 2 WHEN 'FMA' THEN 3 WHEN 'MAM' THEN 4
  WHEN 'AMJ' THEN 5 WHEN 'MJJ' THEN 6 WHEN 'JJA' THEN 7 WHEN 'JAS' THEN 8 WHEN 'ASO' THEN 9
  WHEN 'SON' THEN 10 WHEN 'OND' THEN 11 ELSE 12 END;

-- 2) El Niño: anomalias semanais por região Niño (gráfico de linhas múltiplas)
SELECT data, nino12 AS "Niño 1+2", nino3 AS "Niño 3", nino34 AS "Niño 3.4", nino4 AS "Niño 4"
FROM enso_semanal ORDER BY data;

-- 3) Arboviroses: casos por semana epidemiológica e município (linha / barras)
SELECT semana, municipio, doenca, casos_semana, nivel, rt
FROM arboviroses
WHERE doenca = {{doenca}}            -- variável do Metabase: dengue | chikungunya | zika
ORDER BY semana;

-- 4) Arboviroses: situação atual (tabela com formatação condicional no nível)
SELECT a.municipio, a.doenca, a.semana, a.nivel, a.casos_semana, a.casos_ano, a.incidencia_100k, a.rt
FROM arboviroses a
JOIN (SELECT geocodigo, doenca, MAX(semana) s FROM arboviroses GROUP BY geocodigo, doenca) m
  ON a.geocodigo = m.geocodigo AND a.doenca = m.doenca AND a.semana = m.s
ORDER BY a.nivel DESC, a.casos_ano DESC;

-- 5) Alimentos: variação mensal por item e localidade (tabela dinâmica)
SELECT mes_codigo, mes, localidade, item, variacao_mes, variacao_12m
FROM alimentos_ipca
ORDER BY mes_codigo DESC, localidade, item;

-- 6) Alimentos: maiores altas do último mês
SELECT localidade, item, variacao_mes, variacao_12m
FROM alimentos_ipca
WHERE mes_codigo = (SELECT MAX(mes_codigo) FROM alimentos_ipca)
  AND item NOT LIKE 'Alimentação%'
ORDER BY variacao_mes DESC
LIMIT 10;

-- 7) Pesquisa de preços: média por produto e mercado (Dourados) nos últimos 30 dias
SELECT produto, mercado, unidade, ROUND(AVG(preco), 2) AS preco_medio, COUNT(*) AS coletas,
       MAX(data) AS ultima_coleta
FROM precos_mercado
WHERE cidade = 'Dourados/MS' AND data >= date('now', '-30 day')
GROUP BY produto, mercado, unidade
ORDER BY produto, preco_medio;

-- 8) Pesquisa de preços: evolução semanal da média de um produto
SELECT strftime('%Y-%W', data) AS semana, produto, ROUND(AVG(preco), 2) AS preco_medio
FROM precos_mercado
WHERE cidade = 'Dourados/MS'
GROUP BY semana, produto
ORDER BY semana;

-- 9) Câmbio: dólar e euro em reais (linha)
SELECT data,
       MAX(CASE WHEN base = 'USD' AND moeda = 'BRL' THEN valor END) AS usd_brl,
       MAX(CASE WHEN base = 'EUR' AND moeda = 'BRL' THEN valor END) AS eur_brl
FROM cambio GROUP BY data ORDER BY data;

-- 10) Notícias: volume diário por nível de criticidade (barras empilhadas)
SELECT date(publicado_em) AS dia, nivel, COUNT(*) AS noticias
FROM noticias
WHERE publicado_em >= date('now', '-30 day')
GROUP BY dia, nivel ORDER BY dia;

-- 11) Notícias críticas por categoria e escopo nos últimos 7 dias
SELECT categoria, escopo, COUNT(*) AS criticas
FROM noticias
WHERE nivel = 'critico' AND publicado_em >= date('now', '-7 day')
GROUP BY categoria, escopo ORDER BY criticas DESC;

-- 12) Clima: previsão das cidades monitoradas
SELECT cidade, data, tmin, tmax, chuva_mm, prob_chuva FROM clima_previsao ORDER BY cidade, data;

-- 13) Saúde do coletor: última execução de cada etapa
SELECT etapa, ok, mensagem, quando FROM coletas
WHERE id IN (SELECT MAX(id) FROM coletas GROUP BY etapa) ORDER BY etapa;
