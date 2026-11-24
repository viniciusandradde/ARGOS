# Proposta para a compra do mês em Dourados

Proposta de produto para o ARGOS Android, baseada no piloto 1.2.2. Pesquisa de fontes em 24/11/2026. A alternativa web prevê uma entrada exclusiva para Compras e estoque compartilhado entre os aparelhos. [Proposta para o GitHub Pages](PROPOSTA-COMPRAS-PAGES.md)

A primeira tela de **Compras** daria acesso direto a **Dar baixa**, **Buscar nas minhas notas** e **Gerar lista do mês**. O piloto já importa NFC-e, registra consumo, guarda histórico e calcula faltas no aparelho. A melhoria transforma esses recursos em um ciclo que liga a despensa, a cotação por filial e o valor efetivamente pago. [Fluxo atual](COMPRAS.md)

## Usar o estoque no dia a dia

- Na linha de cada produto, **Dar baixa** oferece atalhos como “1 unidade” ou “meio quilo”, além de quantidade livre. A tela mostra o saldo antes e depois. Um extrato registra data, quantidade e motivo de cada entrada, consumo, perda ou ajuste de contagem. **Desfazer** cria o movimento inverso. Uma baixa acima do saldo pede que o usuário confira a quantidade.
- Cada produto pode ter unidade de estoque, embalagem de compra e conversão confirmada. Por exemplo, comprar uma caixa com 12 litros de leite acrescenta 12 L. Consumir 500 mL reduz o saldo em 0,5 L. Produto a granel admite fração. O ARGOS só converte uma unidade comercial em peso ou volume quando conhece o conteúdo da embalagem.
- **Buscar nas minhas notas** aceita o nome da lista e a abreviação usada pelo mercado. Há filtros por mês ou intervalo, filial e número ou chave da nota. Uma busca por “leite” mostra data, loja, quantidade, preço da embalagem e preço por litro. Tocar no resultado abre a nota completa, incluindo o valor pago. Descontos gerais ficam identificados quando a nota não permite atribuí-los a um item.

## O que faz o botão Gerar lista do mês

1. Abre o mês atual com a lista padrão. O primeiro comparativo traz sempre o **Fortaleza Parque Alvorada** e o **Leve Max da Avenida Guaicurus**, em Dourados. A falta é o maior valor entre zero, a pendência avulsa e o padrão menos o saldo. Com meta de 6 L de leite, saldo de 2 L e pedido avulso de 3 L, entram 4 L. O usuário vê esse cálculo antes de editar.
2. Ajusta a quantidade à embalagem que realmente pode ser comprada. Para repor 750 g de café disponível apenas em pacotes de 500 g, orça dois pacotes e informa os 250 g excedentes. Marcas ou tamanhos alternativos dependem da preferência do usuário.
3. Salva a lista no aparelho e consulta preços para os itens faltantes em paralelo. O usuário já pode usar a lista enquanto as cotações chegam. Abrir de novo recupera a lista do mesmo mês. **Atualizar preços** refaz a cotação. **Recalcular faltas** usa o estoque atual e permite revisar alterações manuais e compras parciais.
4. Mostra o custo de resolver a compra em uma única loja. O resultado de cada filial informa valor, cobertura, data, canal e itens pendentes. Uma segunda opção simula no máximo duas lojas e inclui o custo adicional de deslocamento informado pelo usuário. O ranking usa o preço das embalagens necessárias e considera quantidade mínima, cartão, clube e frete aplicáveis.
5. Ao voltar do mercado, o usuário escolhe a lista e confirma a NFC-e. O ARGOS dá entrada uma vez, mostra o previsto e o pago por item, conserva o preço usado na decisão e mantém o saldo que ainda falta comprar. Marcar um item no carrinho, gerar a lista ou atualizar a cotação não movimenta o estoque.

### Como a comparação aparece

Ao gerar, reabrir ou atualizar a lista, as duas filiais aparecem lado a lado, inclusive quando uma fonte está fora do ar. Para cada produto, a tela mostra quantidade a comprar, preço em cada loja e a diferença em reais. Quando falta um preço vigente, a célula mostra **Sem cotação**. O rodapé soma os mesmos produtos com preço nas duas filiais e informa quantos itens da lista essa soma cobre. A diferença da compra inteira só aparece quando ambas cobrem toda a lista. Sem itens em comum, a tela informa que ainda não é possível calcular a diferença. As cotações de Abevê, Atacadão e Comper aparecem abaixo desse par.

Exemplo **ilustrativo**, com três produtos e valores fictícios. São duas unidades de arroz, quatro de leite e um pacote de café, com apresentações equivalentes. [Ver a comparação em imagem](exemplo-comparacao-alvorada.png)

| Produto e quantidade | Fortaleza Parque Alvorada | Leve Max Guaicurus | Diferença para a lista |
| --- | ---: | ---: | --- |
| Arroz · 2 pacotes | 2 × R$ 20 = R$ 40 | 2 × R$ 19 = R$ 38 | R$ 2 a menos no Leve Max |
| Leite · 4 caixas | 4 × R$ 5 = R$ 20 | 4 × R$ 5,50 = R$ 22 | R$ 2 a menos no Fortaleza |
| Café · 1 pacote | R$ 16 | Sem cotação | Pendente |
| **Itens em comum (2 de 3)** | **R$ 60** | **R$ 60** | Mesmo valor |
| **Lista inteira (3 itens)** | **R$ 76** | Falta o café | Pendente |

Nesse exemplo, arroz e leite somam R$ 60 em cada mercado. Falta o preço do café no Leve Max, então a diferença da cesta inteira fica em aberto. Comprar o arroz no Leve Max e os demais itens no Fortaleza custaria R$ 74 em mercadorias. Com R$ 5 de deslocamento adicional, essa divisão sairia por R$ 79, três reais acima de comprar tudo no Fortaleza.

## Fontes para Dourados

| Fonte verificada | Uso proposto | Condição para entrar no orçamento |
| --- | --- | --- |
| **Fortaleza Parque Alvorada**, Rua Cláudio Goelzer, 1620. A rede divulga campanhas semanais e o Clube F+. | Primeira coluna do comparativo fixo. Conferir o encarte datado que inclui essa filial ou todas as lojas da rede em Dourados. | O calendário indica os dias das campanhas. Para cotar, é preciso identificar produto, embalagem, valor e vigência. Desconto F+ depende da adesão do usuário. [Lojas, campanhas e Clube F+ do Fortaleza](https://supermercadofortalezams.com.br/) |
| **Leve Max da Avenida Guaicurus**, Av. Guaicurus, 500. A rede divulga ofertas e compra on-line em Dourados. | Segunda coluna do comparativo fixo. Cotar as ofertas de loja física aplicáveis à Guaicurus e registrar a quantidade mínima de cada faixa de atacado. | Usar o preço elegível para a quantidade da lista. Uma publicação da Marcelino Pires precisa incluir expressamente a Guaicurus para valer nessa coluna. Ofertas de entrega ficam identificadas pelo canal e filial atendente. [Cadastro da unidade Guaicurus](https://ngvcred.com.br/lojas?page=3) · [Canais do Leve Max](https://linktr.ee/levemax) |
| **Abevê Supermercados (ABV)** divulga ofertas para Dourados e identifica Albino Torraca e Água Boa como unidades no iFood. | Comparação adicional, inicialmente com a filial Albino Torraca. Registrar filial e canal de cada preço. | Identificar ofertas de clube e incluir taxas aplicáveis em cotações de entrega. O preço de aplicativo só vale na loja física se a rede confirmar a mesma condição. [Canais do Abevê](https://linktr.ee/abeve) · [Cadastro de filiais](https://ngvcred.com.br/lojas) |
| Atacadão e Comper têm filiais identificáveis em Dourados. O Comper publica encartes com seletores de cidade e loja. | Comparações adicionais. Priorizar arquivo ou integração fornecida pela rede. Encarte oficial datado pode ser cadastrado e revisado durante o piloto. | Confirmar filial, canal, embalagem, validade e condições. Na pesquisa, a página de encartes do Comper abriu em Campo Grande. Um preço dessa tela só entra após verificar que se aplica à filial de Dourados. [Atacadão Dourados](https://www.atacadao.com.br/loja/dourados) · [Comper Dourados, loja 144](https://www.comper.com.br/3049/nossas-lojas) · [Encarte Comper](https://www.comper.com.br/encartes) |
| Procon Municipal de Dourados publica pesquisas com produtos, apresentações e preços por estabelecimento. | Usar como referência local datada e para conferir se uma cotação é plausível. | Guardar data da coleta. Quando o levantamento informa apenas categoria e peso, apresentar a referência da categoria. Em abril de 2025, por exemplo, a linha de arroz tipo I de 5 kg variava de R$ 18,79 a R$ 22,90. São valores históricos. [Pesquisas municipais](https://pgm.dourados.ms.gov.br/procon/pesquisa-de-precos-do-procon/) · [Tabela municipal de abril de 2025](https://pgm.dourados.ms.gov.br/wp-content/uploads/2025/04/01-04-2025-Cesta-Basica.pdf) |
| NFC-e importadas pelo usuário e pesquisa manual de preços do ARGOS. | Mostrar **Último preço pago** ou **Preço observado**, com loja, data e origem. Aproveitar registros antigos quando filial, unidade e data puderem ser identificadas. | A consulta da SEFAZ-MS parte da chave da nota. Uma compra passada é evidência do valor pago naquela data. Pode alimentar uma estimativa identificada e o comparativo após a compra. [SEFAZ-MS](https://www.sefaz.ms.gov.br/documentos-fiscais-eletronicos/nfc-e/) |
| Menor Preço Brasil, da Receita Estadual do RS e da Procergs, usa documentos fiscais para mostrar vendas recentes. | Candidato a uma fonte adicional de preços praticados. | Antes de planejar integração, demonstrar cobertura de Dourados com produtos da cesta e confirmar acesso documentado para o ARGOS. Não foi confirmada uma API pública com essa cobertura. [Secretaria da Fazenda do RS](https://fazenda.rs.gov.br/desenvolvido-no-rs-app-menor-preco-brasil-ja-comparou-40-bilhoes-de-notas-fiscais-para-15-estados-e-df) |

**Preço vigente** exige publicação aplicável à filial, ao canal e à data da compra. **Venda observada** informa quando o preço foi praticado. **Referência histórica** ajuda a planejar o gasto. **Sem cotação** mantém o produto visível e fora do subtotal. A validade vence mesmo se a mesma página for baixada outra vez. Uma promoção condicionada a clube ou atacado só participa do total quando o usuário e a quantidade atendem à condição.

## Como implantar e medir

| Etapa | Entrega | Critério para avançar |
| --- | --- | --- |
| 1. Estoque e notas | Extrato de movimentos, baixa rápida, desfazer, índices de pesquisa e lista mensal salva no IndexedDB. Na migração, registrar o saldo atual como abertura, manter as notas antigas pesquisáveis e preservar os vínculos já confirmados. | Importar a mesma nota duas vezes não duplica estoque. Dar baixa e desfazer restaura o saldo. Uma nota antiga aparece na busca. A lista abre e funciona offline. |
| 2. Piloto de cotação | Testar 20 produtos frequentes nas duas filiais fixas e ampliar a coleta para uma unidade local de cada uma das outras três redes. Usar a infraestrutura de preços do ARGOS para guardar ofertas por filial, produto e validade. No celular ficam notas, consumo e preferências. A consulta externa precisa apenas de produtos, quantidades e filiais. | Conferir fonte, embalagem, canal e cobertura por filial. Gerar a lista com cobertura completa, parcial e com uma das fontes indisponível. Nos três casos o par continua visível. Uma oferta exclusiva de outra unidade fica fora da comparação. A economia total exige cobertura completa nas duas filiais. |
| 3. Automação e comparação | Atualizar as fontes compatíveis em intervalos adequados à publicação. Ao gerar a lista, reutilizar ofertas ainda válidas e atualizar fontes vencidas. Usar código de barras (GTIN) quando disponível, alternativa por marca, conteúdo e unidade, e revisão para correspondências ambíguas. Salvar a versão da cotação usada na lista. | Uma filial indisponível gera resultado parcial. Oferta vencida, outra cidade ou clube incompatível não entram no total. Medir a diferença entre previsto e pago e mostrar sua causa quando identificável. |

A primeira liberação pode usar encartes oficiais revisados e já oferecer a cotação automática da lista sobre esses dados. A expansão por rede depende de obter e validar um canal de atualização recorrente, com formato, permissão de uso e frequência definidos com a fonte. Assim é possível medir a cobertura real em Dourados antes de prometer um orçamento completo para qualquer cesta.
