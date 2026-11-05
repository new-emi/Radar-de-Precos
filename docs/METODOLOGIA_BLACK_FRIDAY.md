# O desconto da Black Friday foi real? — Metodologia (pré-registro)

**Escrito em 05/11/2026, antes da coleta dos dados.** As regras abaixo foram definidas *antes* de ver os preços
da Black Friday, para que o resultado não influencie a forma de medir. Isso se chama **pré-registro**: sem ele,
fica fácil (mesmo sem querer) escolher a régua que confirma o que se esperava. Qualquer mudança depois desta data
será registrada na seção *Alterações* no fim do arquivo, com o motivo.

## Pergunta

Nas cinco lojas monitoradas pelo Radar de Preços, os preços dos produtos de casa, higiene e limpeza na
Black Friday de 2026 foram **realmente menores** que os preços praticados no começo de novembro?
E existe o padrão de **"maquiagem de desconto"**: o preço sobe nas semanas anteriores e "cai" na Black Friday
de volta para o valor de antes?

## Hipótese principal (acrescentada em 05/11, antes dos dados)

**H1:** a proporção de produtos com **maquiagem de desconto** é **maior** no grupo *Típicos de Black Friday*
do que no grupo *Casa (controle)*.

Os dois grupos vêm de uma **lista fixa do estudo** (`lista_estudo.txt`), congelada em 05/11/2026 e separada da
lista de compras da família (que pode mudar a qualquer momento):

- **Casa (controle), 10 itens:** produtos de mercado, higiene e limpeza de marcas comuns (creme dental, amaciante,
  sabão em pó, papel higiênico, detergente, desodorante, shampoo, papel toalha, sabonete, café).
- **Típicos de Black Friday, 10 itens:** escolhidos a partir das categorias que aparecem nos levantamentos dos
  Procons das últimas edições: fritadeira elétrica de 4 L, sanduicheira, panela elétrica e ferro de passar
  (Procon Recife 2025; Procon de Fortaleza 2023), smart TV de 43" e smartphone (Procon de Porto Alegre 2019;
  Procon de Fortaleza 2023), além de fone bluetooth, liquidificador, cafeteira de cápsula e assistente de voz,
  itens frequentes nas ofertas de Black Friday das lojas monitoradas.

Cada item tem marca e modelo, para que as lojas devolvam sempre os mesmos produtos. Os itens da lista da família
entram na análise como um terceiro grupo (*Lista da família*), apenas descritivo.

## Dados

- **Fonte:** `historico.db`, gravado pelo robô a cada busca (uma por dia, às 11h, pelo Agendador do Windows).
- **Lojas:** Americanas, Atacadão, Muffato (API VTEX), Magalu e Amazon (navegador).
- **Produto:** identificado por uma **chave estável** (`radar/analise.py → chave_produto`): na Amazon, o código
  ASIN do link (`/dp/B07DTLS9M7`); nas outras lojas, o endereço do produto sem os parâmetros após `?`.
  Motivo: a Amazon muda o código de rastreamento do link a cada busca (59 de 183 produtos tinham links diferentes
  para o mesmo produto em 04–05/11).
- **Preço do dia:** o menor preço daquele produto no dia (se houve mais de uma busca no mesmo dia).

## Janelas de tempo

| Janela | Período | Papel |
|---|---|---|
| **Base** | 05/11 a 15/11 | preço "normal" de referência |
| **Pré-Black Friday** | 16/11 a 26/11 | onde se procura o aumento antes do "desconto" |
| **Black Friday** | 27/11 a 30/11 | sexta da Black Friday até a Cyber Monday |

## Métricas (por produto)

- **P_base** = **mediana** dos preços diários na janela Base. A mediana, e não a média, para um dia atípico
  (promoção relâmpago ou erro de leitura) não distorcer a referência.
- **P_pré** = maior preço diário na janela Pré-Black Friday.
- **P_bf** = menor preço diário na janela Black Friday (o melhor momento para comprar).
- **Variação** = (P_bf − P_base) / P_base.

**Dados mínimos:** o produto só entra na análise se tiver **pelo menos 3 dias** na janela Base e **pelo menos
1 dia** na janela Black Friday. Os demais são contados como "dados insuficientes" e reportados, não descartados
em silêncio.

## Classificação (limiar fixo de 5%)

| Classe | Regra |
|---|---|
| **Desconto real** | P_bf ≤ P_base × 0,95 |
| **Maquiagem de desconto** | P_pré ≥ P_base × 1,05 **e** P_bf < P_pré **e** P_bf > P_base × 0,95 (subiu antes e "caiu" na Black Friday, mas não ficou realmente mais barato que o normal) |
| **Ficou mais caro** | P_bf ≥ P_base × 1,05 e não é maquiagem |
| **Sem mudança** | os demais casos (variação entre −5% e +5%) |

O limiar de 5% foi escolhido para ignorar oscilações pequenas e normais de preço.

## Nível da lista de compras

Além de cada produto, a pergunta prática: **comprar a lista na Black Friday saiu mais barato?**
Para cada item da lista, usa-se a **melhor escolha da IA** de cada dia (a da última busca do dia), comparada pelo
**preço por unidade** (R$/L, R$/100 g, R$/10 m, R$/un) na unidade mais comum do item na janela Base: mediana da
janela Base × menor valor da janela Black Friday. Itens cujo título não diz a quantidade são comparados pelo preço.
O total da lista é o da **mesma compra**: o preço normal de cada item (mediana da Base) corrigido pela variação
dele. Soma só os itens que têm dados nas duas janelas.

## Limitações conhecidas (declaradas antes)

- Preços **sem frete, cupom ou cashback**, que podem mudar o preço final de verdade.
- Só **5 lojas** e só os **5 primeiros resultados** de cada busca: não é uma amostra do varejo inteiro.
- Supermercados (Muffato) podem mostrar preço de uma região padrão, não necessariamente a de Arapongas (PR).
- **O "preço normal" pode já incluir o "esquenta Black Friday".** Muitas lojas começam promoções (ou aumentos)
  no início de novembro, e a coleta começou em 05/11, sem dados de outubro. Se isso aconteceu, a janela Base
  já está deslocada e o efeito medido fica menor do que o real.
- O resultado descreve **esta lista de compras nestas 5 lojas**; não é uma amostra estatística do varejo.
- Dias sem busca (PC desligado) ficam sem dado; por isso a exigência de dias mínimos.
- A melhor escolha da IA pode mudar de produto entre os dias; por isso o nível da lista é complementar ao
  nível do produto (que acompanha sempre o **mesmo** produto).

## Como reproduzir

```powershell
python scripts\analise_black_friday.py
```

Gera `docs/black-friday.html` (o relatório) e `docs/black-friday-resultados.json` (os números).

## Alterações

- **05/11/2026 (antes de qualquer dado de Black Friday):** criada a lista fixa do estudo (`lista_estudo.txt`) com dois
  grupos de 10 itens e a hipótese H1 (comparação Casa × Típicos de Black Friday). Motivo: a lista da família muda de nome,
  e um grupo de controle permite uma pergunta mais forte. Validação com dados simulados (40% × 10% de maquiagem
  plantados) recuperou 40% × 11%. Nenhuma regra de cálculo foi alterada.
- **05/11/2026 (antes de qualquer dado de Black Friday):** acrescentadas duas limitações — possível "esquenta" já na janela Base e o caráter descritivo do resultado. Nenhuma regra de cálculo foi alterada.
- **05/11/2026 (antes de qualquer dado de Black Friday):** o nível da lista passou a comparar o **preço por unidade**
  da melhor escolha, e não o preço. Motivo: a melhor escolha da IA muda de embalagem entre os dias (no absorvente,
  o pacote de 16 em 04/11 e o de 48 em 05/11), e comparar os preços daria "+190%" quando por unidade foi −3%.
  Também corrigida a chave dos anúncios patrocinados da Amazon (`/sspa/click`), que escondem o ASIN dentro do link:
  antes, 213 de 531 ofertas da Amazon viravam um único "produto". As regras de classificação não mudaram.
