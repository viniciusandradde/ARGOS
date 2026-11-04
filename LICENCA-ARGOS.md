# Licença de Uso de Software — ARGOS

**Titular:** VSA Soluções em Tecnologia
**Produto:** ARGOS — Monitoramento Ativo (servidor web, sala de situação, radar climático local,
alertas e aplicativo Android)
**Versão da licença:** 1.0 — novembro de 2026

Copyright © 2026 VSA Soluções em Tecnologia. Todos os direitos reservados.

## 1. Objeto e abrangência

Esta licença cobre os componentes do ARGOS desenvolvidos para a VSA Soluções em Tecnologia
("Componentes ARGOS"):

| Componente | Caminho no repositório |
|---|---|
| Camada comercial: usuários, planos, cobrança, telas, coletor e alertas | `src/mcp_brasil/radar/` |
| Aplicativo Android, vigia em segundo plano, ícones e identidade visual | `mobile/` |
| Deploy, instalação e operação | `deploy/`, `scripts/`, `docker-compose.yml`, `Dockerfile` |
| Documentação do produto | `docs/deploy/`, `docs/metabase/`, `memory/` |
| Marca "ARGOS", o ícone (olho com radar) e o nome comercial | todo o projeto |

O código derivado do projeto aberto **mcp-brasil** (Copyright © 2025 Jonatas Soares) continua sob
a **Licença MIT** original, reproduzida no arquivo `LICENSE`, que deve ser mantido em todas as
cópias. Esta licença não restringe os direitos que a Licença MIT concede sobre aquele código.

## 2. Concessão de uso

A VSA Soluções em Tecnologia concede ao licenciado uma licença **não exclusiva, intransferível e
revogável** para instalar e usar os Componentes ARGOS:

- (a) conforme o plano contratado (Essencial, Profissional, Empresarial ou contrato específico);
- (b) somente no número de usuários, aparelhos e instâncias previsto no plano.

## 3. Restrições

Sem autorização prévia e por escrito da VSA Soluções em Tecnologia, é proibido:

1. copiar, redistribuir, sublicenciar, vender, alugar ou disponibilizar os Componentes ARGOS a
   terceiros, inclusive o arquivo APK;
2. modificar, descompilar, fazer engenharia reversa ou criar obras derivadas dos Componentes ARGOS,
   exceto na medida permitida por lei;
3. remover ou alterar avisos de direitos autorais, a marca ARGOS ou esta licença;
4. usar a marca, o nome ou o ícone ARGOS em outros produtos ou serviços.

## 4. Dados de terceiros

O ARGOS consulta fontes públicas, e cada uma mantém seus próprios termos:

- **Fontes e seus termos:**
  - INMET, IBGE/SIDRA, InfoDengue (Fiocruz/FGV), INPE, NOAA, USGS, NASA e BCE/Frankfurter;
  - Open-Meteo (CC BY 4.0): o uso comercial exige plano pago com chave de API;
  - MET Norway (CC BY 4.0);
  - OpenStreetMap (ODbL), incluindo Nominatim, Photon e Overpass;
  - feeds RSS dos veículos citados no aplicativo.
- O licenciado é responsável por respeitar esses termos no seu uso, em especial a exigência de
  plano comercial do Open-Meteo e o limite de 1 requisição por segundo do Nominatim.
- As notícias pertencem aos respectivos veículos. O ARGOS exibe título, resumo e link para a fonte
  original.

## 5. Componentes de código aberto incluídos

| Componente | Licença |
|---|---|
| mcp-brasil | MIT |
| FastMCP | Apache 2.0 |
| Capacitor e plugins oficiais | MIT |
| Leaflet | BSD-2-Clause |
| Fonte JetBrains Mono | SIL Open Font License 1.1 |

Os textos dessas licenças acompanham os respectivos pacotes, por exemplo
`mobile/www/vendor/leaflet/LICENSE` e `mobile/www/vendor/fonts/OFL.txt`.

## 6. Isenção de garantia e limitação de responsabilidade

Os alertas, avisos, riscos e boletins do ARGOS são **informativos**. Eles derivam de fontes
públicas e de modelos numéricos que podem falhar, atrasar ou ficar indisponíveis.

- O ARGOS **não substitui** os canais oficiais: Defesa Civil (199), INMET, Corpo de Bombeiros (193)
  e autoridades de saúde.
- Na extensão máxima permitida pela lei, a VSA Soluções em Tecnologia não responde por danos
  decorrentes de decisões tomadas com base nessas informações.
- O software é fornecido "no estado em que se encontra", sem garantias além das previstas em lei
  ou em contrato específico.

## 7. Vigência e rescisão

- A licença vigora enquanto o plano contratado estiver ativo.
- Ela termina automaticamente se qualquer cláusula for descumprida. Nesse caso, o licenciado deve
  desinstalar e apagar todas as cópias dos Componentes ARGOS.

## 8. Foro

Fica eleito o foro da comarca da sede da VSA Soluções em Tecnologia para dirimir questões
decorrentes desta licença. Aplica-se a legislação brasileira, em especial a Lei nº 9.609/1998
(Lei do Software) e a Lei nº 9.610/1998 (Direitos Autorais).

---

*Modelo preparado para revisão jurídica. Antes da comercialização, complete os dados da empresa
(razão social, CNPJ e endereço) e valide o texto com o advogado responsável.*
