# Proposta para a compra do mês em Dourados

Proposta de produto para o ARGOS Android, baseada no piloto 1.2.2. Pesquisa de fontes em 24/11/2026.

A primeira tela de **Compras** daria acesso direto a **Dar baixa**, **Buscar nas minhas notas** e **Gerar lista do mês**. O piloto já importa NFC-e, registra consumo, guarda histórico e calcula faltas no aparelho. A melhoria transforma esses recursos em um ciclo que liga a despensa, a cotação por filial e o valor efetivamente pago. [Fluxo atual](COMPRAS.md)

## Usar o estoque no dia a dia

- Na linha de cada produto, **Dar baixa** oferece atalhos como “1 unidade” ou “meio quilo”, além de quantidade livre. A tela mostra o saldo antes e depois. Um extrato registra data, quantidade e motivo de cada entrada, consumo, perda ou ajuste de contagem. **Desfazer** cria o movimento inverso. Uma baixa acima do saldo pede que o usuário confira a quantidade.
- Cada produto pode ter unidade de estoque, embalagem de compra e conversão confirmada. Por exemplo, comprar uma caixa com 12 litros de leite acrescenta 12 L. Consumir 500 mL reduz o saldo em 0,5 L. Produto a granel admite fração. O ARGOS só converte uma unidade comercial em peso ou volume quando conhece o conteúdo da embalagem.
- **Buscar nas minhas notas** aceita o nome da lista e a abreviação usada pelo mercado. Há filtros por mês ou intervalo, filial e número ou chave da nota. Uma busca por “leite” mostra data, loja, quantidade, preço da embalagem e preço por litro. Tocar no resultado abre a nota completa, incluindo o valor pago. Descontos gerais ficam identificados quando a nota não permite atribuí-los a um item.

## O que faz o botão Gerar lista do mês

1. Abre o mês atual com a lista padrão e as filiais preferidas de Dourados. A falta é o maior valor entre zero, a pendência avulsa e o padrão menos o saldo. Com meta de 6 L de leite, saldo de 2 L e pedido avulso de 3 L, entram 4 L. O usuário vê esse cálculo antes de editar.
2. Ajusta a quantidade à embalagem que realmente pode ser comprada. Para repor 750 g de café disponível apenas em pacotes de 500 g, orça dois pacotes e informa os 250 g excedentes. Marcas ou tamanhos alternativos dependem da preferência do usuário.
3. Salva a lista no aparelho e consulta preços para os itens faltantes em paralelo. O usuário já pode usar a lista enquanto as cotações chegam. Abrir de novo recupera a lista do mesmo mês. **Atualizar preços** refaz a cotação. **Recalcular faltas** usa o estoque atual e permite revisar alterações manuais e compras parciais.
4. Mostra o custo de resolver a compra em uma única loja. O resultado de cada filial informa valor, cobertura, data, canal e itens pendentes. Uma segunda opção simula no máximo duas lojas e inclui o custo adicional de deslocamento informado pelo usuário. O ranking usa o preço das embalagens necessárias e considera quantidade mínima, cartão, clube e frete aplicáveis.
5. Ao voltar do mercado, o usuário escolhe a lista e confirma a NFC-e. O ARGOS dá entrada uma vez, mostra o previsto e o pago por item, conserva o preço usado na decisão e mantém o saldo que ainda falta comprar. Marcar um item no carrinho, gerar a lista ou atualizar a cotação não movimenta o estoque.

### Como a comparação aparece

Exemplo **ilustrativo**, com três produtos e valores fictícios. São duas unidades de arroz, quatro de leite e um pacote de café, com apresentações equivalentes.

| Filial | Arroz | Leite | Café | Resultado |
| --- | ---: | ---: | ---: | --- |
| A | 2 × R$ 20 | 4 × R$ 5 | R$ 16 | **R$ 76**, cesta completa |
| B | 2 × R$ 19 | 4 × R$ 5,50 | Sem cotação vigente | **R$ 60** para 2 de 3 produtos |

Para os dois itens em comum, ambas somam R$ 60. A indicação para resolver a lista inteira é a filial A entre as opções com cobertura completa. Comprar arroz em B e os demais itens em A somaria R$ 74 em mercadorias. Com R$ 5 de deslocamento adicional, essa divisão custaria R$ 79. A tela pode explicar a escolha com esses números.

## Fontes para Dourados

| Fonte verificada | Uso proposto | Condição para entrar no orçamento |
| --- | --- | --- |
| Atacadão e Comper têm filiais identificáveis em Dourados. O Comper publica encartes com seletores de cidade e loja. | Primeiros candidatos para preços anunciados. Priorizar arquivo ou integração fornecida pela rede. Encarte oficial datado pode ser cadastrado e revisado durante o piloto. | Confirmar filial, canal, embalagem, validade e condições. Na pesquisa, a página de encartes do Comper abriu em Campo Grande. Um preço dessa tela só entra após verificar que se aplica à filial de Dourados. [Atacadão Dourados](https://www.atacadao.com.br/loja/dourados) · [Comper Dourados, loja 144](https://www.comper.com.br/3049/nossas-lojas) · [Encarte Comper](https://www.comper.com.br/encartes) |
| Procon Municipal de Dourados publica pesquisas com produtos, apresentações e preços por estabelecimento. | Usar como referência local datada e para conferir se uma cotação é plausível. | Guardar data da coleta. Quando o levantamento informa apenas categoria e peso, apresentar a referência da categoria. Em abril de 2025, por exemplo, a linha de arroz tipo I de 5 kg variava de R$ 18,79 a R$ 22,90. São valores históricos. [Pesquisas municipais](https://pgm.dourados.ms.gov.br/procon/pesquisa-de-precos-do-procon/) · [Tabela municipal de abril de 2025](https://pgm.dourados.ms.gov.br/wp-content/uploads/2025/04/01-04-2025-Cesta-Basica.pdf) |
| NFC-e importadas pelo usuário e pesquisa manual de preços do ARGOS. | Mostrar **Último preço pago** ou **Preço observado**, com loja, data e origem. Aproveitar registros antigos quando filial, unidade e data puderem ser identificadas. | A consulta da SEFAZ-MS parte da chave da nota. Uma compra passada é evidência do valor pago naquela data. Pode alimentar uma estimativa identificada e o comparativo após a compra. [SEFAZ-MS](https://www.sefaz.ms.gov.br/documentos-fiscais-eletronicos/nfc-e/) |
| Menor Preço Brasil, da Receita Estadual do RS e da Procergs, usa documentos fiscais para mostrar vendas recentes. | Candidato a uma fonte adicional de preços praticados. | Antes de planejar integração, demonstrar cobertura de Dourados com produtos da cesta e confirmar acesso documentado para o ARGOS. Não foi confirmada uma API pública com essa cobertura. [Secretaria da Fazenda do RS](https://fazenda.rs.gov.br/desenvolvido-no-rs-app-menor-preco-brasil-ja-comparou-40-bilhoes-de-notas-fiscais-para-15-estados-e-df) |

**Preço vigente** exige publicação aplicável à filial, ao canal e à data da compra. **Venda observada** informa quando o preço foi praticado. **Referência histórica** ajuda a planejar o gasto. **Sem cotação** mantém o produto visível e fora do subtotal. A validade vence mesmo se a mesma página for baixada outra vez. Uma promoção condicionada a clube ou atacado só participa do total quando o usuário e a quantidade atendem à condição.

## Como implantar e medir

| Etapa | Entrega | Critério para avançar |
| --- | --- | --- |
| 1. Estoque e notas | Extrato de movimentos, baixa rápida, desfazer, índices de pesquisa e lista mensal salva no IndexedDB. Na migração, registrar o saldo atual como abertura, manter as notas antigas pesquisáveis e preservar os vínculos já confirmados. | Importar a mesma nota duas vezes não duplica estoque. Dar baixa e desfazer restaura o saldo. Uma nota antiga aparece na busca. A lista abre e funciona offline. |
| 2. Piloto de cotação | Escolher 20 produtos frequentes e duas filiais. Usar a infraestrutura de preços já existente do ARGOS para guardar ofertas públicas por filial, produto e validade. No celular ficam notas, consumo e preferências. A consulta externa precisa apenas dos produtos, das quantidades necessárias para promoções e das filiais. | Cada preço do teste tem fonte verificável e embalagem compatível. Conferir ofertas no canal anunciado. Medir quantos dos 20 produtos têm cotação elegível em cada loja. Só liberar a indicação de cesta completa quando todos os itens estiverem cobertos. |
| 3. Automação e comparação | Atualizar as fontes compatíveis em intervalos adequados à publicação. Ao gerar a lista, reutilizar ofertas ainda válidas e atualizar fontes vencidas. Usar código de barras (GTIN) quando disponível, alternativa por marca, conteúdo e unidade, e revisão para correspondências ambíguas. Salvar a versão da cotação usada na lista. | Uma filial indisponível gera resultado parcial. Oferta vencida, outra cidade ou clube incompatível não entram no total. Medir a diferença entre previsto e pago e mostrar sua causa quando identificável. |

A primeira liberação pode usar encartes oficiais revisados e já oferecer a cotação automática da lista sobre esses dados. A expansão por rede depende de obter e validar um canal de atualização recorrente, com formato, permissão de uso e frequência definidos com a fonte. Assim é possível medir a cobertura real em Dourados antes de prometer um orçamento completo para qualquer cesta.
