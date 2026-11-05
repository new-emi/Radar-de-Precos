# Roteiro e histórico de decisões — Radar de Preços

Organizado em 04/11/2026. Black Friday 2026: **27/11**. Objetivo final: publicar no GitHub e deixar online.

## Fase 1 — Antes da Black Friday (até ~20/11)
O que faz diferença para a compra de verdade.

- [x] **Preço por unidade calculado no código** (R$/litro, R$/100g, R$/rolo, R$/unidade), lido do título
  ("1,5L", "180g", "3 rolos", "kit 3 un"). Mostrar na lista de ofertas e ordenar por ele.
  Hoje só a IA faz essa conta, e às vezes erra.
- [x] **Histórico de preços (SQLite):** cada busca é guardada em vez de sobrescrever o JSON.
  No painel: gráfico por produto e selo "caiu X% / subiu X% desde a semana passada".
  É o que mostra se o "desconto" da Black Friday é real.
- [x] **Busca automática todo dia** pelo Agendador de Tarefas do Windows, sem servidor.
  O histórico se enche sozinho até a Black Friday.
- [x] **Busca mais rápida:** lojas VTEX em paralelo (threads) e esperas fixas trocadas por `wait_for_selector`.

- [x] **Análise "O desconto foi real?"**: pré-registro (`docs/METODOLOGIA_BLACK_FRIDAY.md`), `radar/analise.py`,
  `scripts/analise_black_friday.py` e testes. Falta rodar com os dados reais depois de 30/11.

## Fase 2 — Preparar o GitHub
- [x] **Organizar o código em pastas:** pacote `radar/` com `lojas/` (um arquivo por loja), `ia.py`, `banco.py`, `unidades.py`.
- [x] **Testes automáticos (pytest)** com dados de mentira, sem internet (37 testes).
- [x] **README** com prints, diagrama de como funciona, como instalar e rodar, e o que cada loja exige.
- [ ] **Limpeza:** apagar scripts de teste antigos e `backup_v1/`, gerar chave nova do DeepSeek, conferir o `.gitignore`.
- [x] Licença (MIT) e `requirements.txt` com versões fixas.

## Fase 3 — Online
O robô de Magalu/Amazon precisa de um navegador de verdade, então a arquitetura fica dividida:
- [ ] **Banco na nuvem** (Supabase/Postgres, gratuito) no lugar de `lista.txt` + SQLite.
- [ ] **Painel no Streamlit Community Cloud** (gratuito), lendo do banco, com senha para editar a lista.
- [ ] **Coleta:** lojas VTEX + IA rodando no GitHub Actions (agendado, gratuito), e Magalu/Amazon no PC
  enviando para o mesmo banco. Testar antes se as lojas aceitam IP de nuvem.

## Depois
- O `robo.py` já abre o Chrome sozinho (feito na Fase 1).
- Alertas no WhatsApp ou Telegram quando um item cair mais de X%.
- Palavras-chave inteligentes: se um termo trouxer 0 resultados, a IA sugere uma variação e o robô tenta de novo.
- Carrefour e Drogasil via navegador (a API delas bloqueia).

## Mercado Livre (desligado)
- Fica desligado por padrão; liga com `ML_ATIVO=1` no `.env`.
- Site: pede captcha para robôs (o robô pausa e espera alguém resolver).
- API oficial (04/11/2026): login OK, mas `/sites/MLB/search` e `/products/search` dão 403
  `PA_UNAUTHORIZED_RESULT_FROM_POLICIES`. O ML só libera busca para parceiros. `ml_api.py` fica pronto
  caso isso mude (`python -m radar.lojas.ml_api diagnostico` para testar de novo).

## Lojas: o que já foi testado

### Teste VTEX de 04/11/2026 (`testar_lojas_novas.py`)
| Loja | Resultado | Decisão |
|---|---|---|
| Super Muffato | 9/9 com preço | ✅ **Adicionada** (`https://www.supermuffato.com.br`). Conferir se o preço é o da região (CEP de Arapongas). |
| Nissei | HTTP 404 (retestada em 04/11) | ❌ Não é VTEX, e o robots.txt do site proíbe robôs na página de busca. Fora por enquanto. |
| Drogaria São Paulo | 6 com preço | Guardada. Mesmo grupo e catálogo da Pacheco: só uma das duas, se um dia entrar. |
| Drogarias Pacheco | 8 com preço | Guardada (ver acima). Traz itens fora do pedido (Kleenex em "papel toalha"). |
| Pague Menos | 2 com preço | Guardada. A maioria veio com preço zerado (indisponível). |
| Savegnago | 10 com preço | Guardada. Rede do interior de SP: provavelmente não entrega no PR. |
| Angeloni | 7 com preço | Guardada. Rede de SC/Curitiba: checar entrega. |
| Sam's Club | 5 com preço | ❌ Descartada (pedido da mãe). Exige ser sócio, embalagens de atacado. |
| Carrefour | HTTP 503 | Bloqueio de firewall (Akamai). Só via navegador. |
| Drogasil | HTTP 503 | Bloqueio de firewall. Só via navegador. |
| Condor, Panvel, Época Cosméticos | HTTP 404 | Não são VTEX (ou mudaram a API). |
| Beleza na Web | HTTP 403 | Bloqueada. |

Para colocar uma loja guardada: uma linha em `LOJAS_VTEX` em `radar/lojas/__init__.py` (+ a cor em `COR_LOJA` no `painel.py`).

### Tentativas da IA antiga
| Loja | Erro | Motivo |
|---|---|---|
| Google Shopping | Captcha | Detectou o Playwright. |
| Magalu (API) | 403 | Cloudflare. ✅ Resolvido via navegador. |
| Amazon (API) | 503 | AWS WAF. ✅ Resolvido via navegador. |
| Carrefour | 503/403 | Akamai; bloqueou até o curl_cffi. |
| Assaí | 404 | Sem busca online. Descartado. |
| Drogasil / Droga Raia | 403/503 | Firewall; só via navegador. |
| Nissei | SSLError | Retestada em 04/11: 404, não é VTEX (ver acima). |
| Muffato | JSONDecodeError | Recebeu HTML. ✅ Funcionou no teste novo (endereço VTEX certo). |
| Shopee | — | Cloudflare pesado + tokens anti-CSRF. Descartada. |
