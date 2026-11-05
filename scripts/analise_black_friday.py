# analise_black_friday.py — gera o relatório "O desconto da Black Friday foi real?"
#
# Segue as regras de docs/METODOLOGIA_BLACK_FRIDAY.md (escritas ANTES dos dados) e gera:
#   docs/black-friday.html             -> a página do relatório (no visual do site)
#   docs/black-friday-resultados.json  -> os números, para quem quiser conferir
#
# Uso:
#   .venv\Scripts\python scripts\analise_black_friday.py          -> com o historico.db de verdade
#   .venv\Scripts\python scripts\analise_black_friday.py --demo   -> prévia com dados SIMULADOS
import html
import json
import random
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para achar o pacote radar/ na raiz

from radar import analise, banco  # noqa: E402
from radar.config import PASTA  # noqa: E402

COR = {analise.DESCONTO_REAL: "#17804A", analise.MAQUIAGEM: "#D9A400",
       analise.SEM_MUDANCA: "#9AA59E", analise.MAIS_CARO: "#B42318"}
INICIO, FIM = date(2026, 11, 5), date(2026, 11, 30)


def esc(t):
    return html.escape(str(t or ""))


def reais(v):
    i, c = f"{v:,.2f}".split(".")
    return f"R$ {i.replace(',', '.')},{c}"


def pct(v, sinal=True):
    return f"{'+' if sinal and v > 0 else ''}{v * 100:.0f}%".replace("-", "−")


# ------------------------------------------------------------------ gráficos (SVG à mão)
def barra_classes(contagem):
    total = sum(contagem.get(c, 0) for c in analise.CLASSES) or 1
    x, partes, legenda = 0.0, [], []
    for c in analise.CLASSES:
        n = contagem.get(c, 0)
        w = 1000 * n / total
        if n:
            partes.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="44" fill="{COR[c]}"><title>{c}: {n}</title></rect>')
            if w > 70:
                partes.append(f'<text x="{x + w / 2:.1f}" y="28" text-anchor="middle" fill="#fff" font-size="16" font-weight="700">{n / total * 100:.0f}%</text>')
        x += w
        legenda.append(f'<span><i style="background:{COR[c]}"></i>{c}: <b>{n}</b></span>')
    return (f'<svg viewBox="0 0 1000 44" class="barra" role="img" aria-label="Distribuição das classes">{"".join(partes)}</svg>'
            f'<div class="legenda">{"".join(legenda)}</div>')


def mini_grafico(dias):
    """Linha do preço de 05/11 a 30/11, com as três janelas pintadas ao fundo."""
    larg, alt, m = 320, 110, 8
    total = (FIM - INICIO).days
    pts = sorted((date.fromisoformat(d), p) for d, p in dias.items() if INICIO <= date.fromisoformat(d) <= FIM)
    if len(pts) < 2:
        return ""
    lo, hi = min(p for _, p in pts), max(p for _, p in pts)
    folga = (hi - lo) * 0.2 or hi * 0.05 or 1

    def x(d):
        return m + (larg - 2 * m) * (d - INICIO).days / total

    def y(p):
        return m + (alt - 2 * m - 14) * (1 - (p - (lo - folga)) / ((hi + folga) - (lo - folga)))

    faixas = ""
    for (ini, fim), cor in [(analise.JANELA_PRE, "#FFF8DC"), (analise.JANELA_BF, "#DDF0E3")]:
        a, b = x(date.fromisoformat(ini)), x(date.fromisoformat(fim) + timedelta(days=1))
        faixas += f'<rect x="{a:.1f}" y="0" width="{b - a:.1f}" height="{alt - 14}" fill="{cor}"/>'
    linha = " ".join(f"{x(d):.1f},{y(p):.1f}" for d, p in pts)
    rot = "".join(f'<text x="{x(d):.1f}" y="{alt - 2}" text-anchor="{ancora}" font-size="10" fill="#5F6C64">{d.day:02d}/11</text>'
                  for d, ancora in ((INICIO, "start"), (date(2026, 11, 16), "middle"), (date(2026, 11, 27), "middle")))
    return (f'<svg viewBox="0 0 {larg} {alt}" class="mini" role="img" aria-label="Preço diário">{faixas}'
            f'<polyline points="{linha}" fill="none" stroke="#0F4D2E" stroke-width="2.2" stroke-linejoin="round"/>'
            + "".join(f'<circle cx="{x(d):.1f}" cy="{y(p):.1f}" r="2.6" fill="#0F4D2E"><title>{d:%d/%m}: {reais(p)}</title></circle>' for d, p in pts)
            + f"{rot}</svg>")


def comparacao_grupos(por_grupo):
    ordem = [g for g in ("casa", "black_friday", analise.GRUPO_FAMILIA) if g in por_grupo]
    if not ordem:
        return "<p>Ainda não há dados suficientes.</p>"
    blocos = []
    for g in ordem:
        cont = por_grupo[g]
        n = sum(cont.get(k, 0) for k in analise.CLASSES)
        blocos.append(f'<div class="cartao grupo"><h3>{esc(analise.NOMES_GRUPO.get(g, g))} <small>({n} produtos)</small></h3>'
                      f'{barra_classes(cont)}</div>')
    linhas = "".join(
        f"<tr><td>{esc(analise.NOMES_GRUPO.get(g, g))}</td>"
        + "".join(f"<td>{por_grupo[g].get(k, 0) / max(sum(por_grupo[g].get(c, 0) for c in analise.CLASSES), 1) * 100:.0f}%</td>"
                  for k in analise.CLASSES) + "</tr>" for g in ordem)
    return ("".join(blocos) + f'<table><thead><tr><th>Grupo</th>{"".join(f"<th>{k}</th>" for k in analise.CLASSES)}</tr></thead>'
            f"<tbody>{linhas}</tbody></table>")


def cartao_produto(p):
    pre = f" · pico antes: <b>{reais(p['p_pre'])}</b>" if p.get("p_pre") else ""
    return (f'<div class="produto"><div class="loja">{esc(p["loja"])} · {esc(p["termo"])}</div>'
            f'<div class="titulo">{esc(p["titulo"])}</div>{mini_grafico(p["dias"])}'
            f'<div class="nums">normal: <b>{reais(p["p_base"])}</b>{pre} · Black Friday: <b>{reais(p["p_bf"])}</b> '
            f'<span class="var">({pct(p["variacao"])})</span></div></div>')


# ------------------------------------------------------------------ página
def gerar_html(prod, lista, demo=False):
    validos = [p for p in prod["produtos"] if p["classe"] != analise.INSUFICIENTE]
    n = len(validos)
    c = prod["contagem"]
    real, maq = c.get(analise.DESCONTO_REAL, 0), c.get(analise.MAQUIAGEM, 0)
    resposta = (f"Em <b>{real / n * 100:.0f}%</b> dos {n} produtos acompanhados, o preço da Black Friday foi "
                f"realmente menor (pelo menos 5%) que o do começo de novembro. Em <b>{maq / n * 100:.0f}%</b>, "
                f"o preço subiu antes e “caiu” de volta: maquiagem de desconto.") if n else "Ainda não há dados suficientes."
    maquiagens = sorted([p for p in validos if p["classe"] == analise.MAQUIAGEM], key=lambda p: -(p["p_pre"] / p["p_base"]))[:4]
    descontos = sorted([p for p in validos if p["classe"] == analise.DESCONTO_REAL], key=lambda p: p["variacao"])[:4]
    lojas = "".join(
        f"<tr><td>{esc(loja)}</td><td>{sum(cont.values())}</td>"
        + "".join(f"<td>{cont.get(k, 0)}</td>" for k in analise.CLASSES)
        + f"<td><b>{cont.get(analise.DESCONTO_REAL, 0) / max(sum(cont.values()), 1) * 100:.0f}%</b></td></tr>"
        for loja, cont in prod["por_loja"].items())
    itens = "".join(
        f"<tr><td>{esc(i['termo'])}</td><td>{reais(i['p_base'])}</td><td>{reais(i['p_bf'])} <small>({esc(i['loja_bf'])})</small></td>"
        f"<td class=\"{'neutro' if abs(i['variacao']) < 0.005 else 'bom' if i['economia'] > 0 else 'ruim'}\">"
        f"{'0%' if abs(i['variacao']) < 0.005 else pct(i['variacao'])}</td></tr>"
        for i in sorted(lista["itens"], key=lambda i: i["variacao"]))
    aviso = ('<div class="aviso"><b>Prévia com dados simulados</b>Os números desta página são inventados, só para mostrar '
             'como o relatório vai ficar. O relatório de verdade é gerado depois de 30/11 com o historico.db.</div>') if demo else ""
    economia = (f'<p class="destaque">A mesma compra da lista, no preço por unidade da Black Friday, saiu por <b>{reais(lista["total_bf"])}</b>, '
                f'contra <b>{reais(lista["total_base"])}</b> no começo de novembro: '
                f'{"economia" if lista["economia"] >= 0 else "gasto a mais"} de <b>{reais(abs(lista["economia"]))}</b> '
                f'({pct(-lista["economia_pct"]) if lista["economia_pct"] is not None else "—"}).</p>') if lista["itens"] else ""
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Black Friday 2026 — Radar de Preços</title>
<meta name="description" content="O desconto da Black Friday foi real? Análise dos preços diários de produtos de casa em cinco lojas.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="site.css">
<style>
.barra{{width:100%;height:44px;border-radius:10px;overflow:hidden;display:block}}
.legenda{{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:12px;font-size:.95rem}}
.legenda i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.grupo{{margin-bottom:14px}} .grupo h3{{margin:0 0 12px}} .grupo small{{color:var(--apoio);font-weight:500;font-size:.9rem}}
.produtos{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.produto{{background:#fff;border:1px solid var(--linha);border-radius:14px;padding:18px 20px}}
.produto .loja{{font-size:.84rem;color:var(--apoio)}}
.produto .titulo{{font-weight:600;margin:2px 0 8px;line-height:1.35}}
.produto .nums{{font-size:.9rem;color:var(--apoio)}}
.produto .nums b{{color:var(--tinta)}}
.mini{{width:100%;height:auto;display:block;margin:4px 0 8px}}
.destaque{{font-size:1.15rem;max-width:68ch}}
td.bom{{color:var(--verde);font-weight:700}} td.ruim{{color:#B42318;font-weight:700}} td.neutro{{color:var(--apoio)}}
.chave{{display:flex;gap:16px;flex-wrap:wrap;font-size:.88rem;color:var(--apoio);margin:-6px 0 14px}}
.chave i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;border:1px solid var(--linha)}}
@media (max-width:900px){{.produtos{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header class="topo">
  <div class="topo-dentro">
    <h1>O desconto da Black Friday foi real?</h1>
    <p class="sub">{resposta}</p>
    <div class="badges">
      <span class="badge">🗓️ 05/11 a 30/11/2026</span>
      <span class="badge">🛒 {len(prod['por_loja'])} lojas</span>
      <span class="badge">📦 {n} produtos com dados suficientes</span>
      <span class="badge">📐 Regras definidas antes dos dados</span>
    </div>
    <div class="acoes">
      <a class="botao amarelo" href="index.html">Sobre o Radar de Preços</a>
      <a class="botao contorno" href="https://github.com/new-emi/Radar-de-Precos/blob/main/docs/METODOLOGIA_BLACK_FRIDAY.md">Metodologia (pré-registro)</a>
    </div>
  </div>
</header>
<main class="miolo">
{aviso}
<section>
  <h2>O resultado</h2>
  <p class="intro">Cada produto foi acompanhado todo dia e classificado comparando o menor preço da Black Friday (27 a 30/11) com o preço normal (mediana de 05 a 15/11).</p>
  <div class="cartao">{barra_classes(c)}</div>
  <div class="numeros" style="margin-top:16px">
    <div class="numero"><b>{n}</b><span>produtos analisados</span></div>
    <div class="numero"><b>{real / n * 100 if n else 0:.0f}%</b><span>com desconto real (≥ 5%)</span></div>
    <div class="numero"><b>{maq / n * 100 if n else 0:.0f}%</b><span>com maquiagem de desconto</span></div>
    <div class="numero"><b>{pct(prod['variacao_mediana']) if prod['variacao_mediana'] is not None else '—'}</b><span>variação mediana do preço</span></div>
  </div>
</section>
<section>
  <h2>Itens de casa × itens típicos de Black Friday</h2>
  <p class="intro">A pergunta principal do estudo: a maquiagem de desconto é mais comum nos itens que mais aparecem nas ofertas de Black Friday do que nos itens de casa? Os dois grupos vêm da lista fixa do estudo (<code>lista_estudo.txt</code>), congelada em 05/11.</p>
  {comparacao_grupos(prod["por_grupo"])}
</section>
<section>
  <h2>A lista de compras saiu mais barata?</h2>
  {economia}
  <table><thead><tr><th>Item</th><th>Normal (início de nov.)</th><th>Black Friday</th><th>Variação</th></tr></thead><tbody>{itens}</tbody></table>
</section>
<section>
  <h2>Maquiagem de desconto: os casos mais claros</h2>
  <p class="intro">O preço subiu nas semanas anteriores e “caiu” na Black Friday, mas sem ficar realmente mais barato que o normal.</p>
  <div class="chave"><span><i style="background:#FFF8DC"></i>semanas antes (16 a 26/11)</span><span><i style="background:#DDF0E3"></i>Black Friday (27 a 30/11)</span></div>
  <div class="produtos">{''.join(cartao_produto(p) for p in maquiagens) or '<p>Nenhum caso encontrado.</p>'}</div>
</section>
<section>
  <h2>Os maiores descontos reais</h2>
  <div class="produtos">{''.join(cartao_produto(p) for p in descontos) or '<p>Nenhum caso encontrado.</p>'}</div>
</section>
<section>
  <h2>Por loja</h2>
  <table><thead><tr><th>Loja</th><th>Produtos</th>{''.join(f'<th>{k}</th>' for k in analise.CLASSES)}<th>% desconto real</th></tr></thead><tbody>{lojas}</tbody></table>
</section>
<section>
  <h2>Como foi medido</h2>
  <div class="cartao">
    <ul>
      <li><b>Regras escritas antes dos dados</b> (05/11/2026), no <a href="https://github.com/new-emi/Radar-de-Precos/blob/main/docs/METODOLOGIA_BLACK_FRIDAY.md">pré-registro</a>: janelas, limiar de 5% e dias mínimos.</li>
      <li><b>Produto = o mesmo item da loja ao longo dos dias</b>, identificado por uma chave estável (na Amazon, o código ASIN, porque o link muda a cada busca).</li>
      <li><b>Preço normal = mediana</b> de 05 a 15/11, para um dia atípico não distorcer a referência.</li>
      <li><b>Limitações:</b> preços sem frete, cupom ou cashback; 5 lojas e os 5 primeiros resultados de cada busca; supermercado pode mostrar preço de outra região.</li>
      <li>Produtos sem dados suficientes: {c.get(analise.INSUFICIENTE, 0)} (pelo menos 3 dias de 05 a 15/11 e 1 dia de 27 a 30/11).</li>
    </ul>
  </div>
</section>
</main>
<footer><strong>Emily Cristofoleti</strong> · Radar de Preços · relatório gerado em {gerado}</footer>
</body>
</html>"""


# ------------------------------------------------------------------ dados simulados (--demo)
def banco_demo():
    """Cria um banco TEMPORÁRIO com preços inventados, usando nomes de produtos reais do historico.db."""
    random.seed(2026)
    con = banco.conectar()
    reais_ = con.execute("SELECT DISTINCT termo, loja, titulo, link, preco FROM precos").fetchall()
    con.close()
    vistos, produtos = set(), []
    for r in reais_:
        k = analise.chave_produto(r["link"], r["loja"])
        if k not in vistos:
            vistos.add(k)
            produtos.append(dict(r))
    produtos = random.sample(produtos, min(120, len(produtos)))
    destino = Path(tempfile.mkdtemp()) / "demo.db"
    # metade dos itens vira "casa", metade "black_friday" (só na simulação); perfis diferentes por grupo
    termos = sorted({p["termo"] for p in produtos})
    grupos = {banco.normalizar(t): ("casa" if i % 2 == 0 else "black_friday") for i, t in enumerate(termos)}
    pesos = {"casa": [15, 10, 65, 10], "black_friday": [40, 40, 10, 10]}
    perfis = [random.choices(["real", "maquiagem", "igual", "caro"], weights=pesos[grupos[banco.normalizar(p["termo"])]])[0]
              for p in produtos]
    for i in range((FIM - INICIO).days + 1):
        dia = INICIO + timedelta(days=i)
        if random.random() < 0.1:            # alguns dias sem busca (PC desligado)
            continue
        itens = {}
        for p, perfil in zip(produtos, perfis):
            fator = 1 + random.uniform(-0.02, 0.02)
            if dia >= date(2026, 11, 16) and perfil == "maquiagem":
                fator *= 1.18 if dia < date(2026, 11, 27) else 1.02
            if dia >= date(2026, 11, 27):
                fator *= {"real": 0.82, "caro": 1.10}.get(perfil, 1)
            info = itens.setdefault(p["termo"], {"recomendacoes_ia": [], "produtos": []})
            info["produtos"].append({**p, "preco": round(p["preco"] * fator, 2)})
        for info in itens.values():
            info["produtos"].sort(key=lambda x: x["preco"])
            info["recomendacoes_ia"] = [{"link": info["produtos"][0]["link"]}]
        banco.salvar_busca(itens, datetime.combine(dia, datetime.min.time()).replace(hour=11), destino)
    return destino, grupos


def main():
    demo = "--demo" in sys.argv
    arq, grupos = banco_demo() if demo else (None, None)
    prod = analise.analisar_produtos(arq, grupos)
    lista = analise.analisar_lista(arq)
    destino_html = PASTA / "docs" / ("black-friday-demo.html" if demo else "black-friday.html")
    destino_html.write_text(gerar_html(prod, lista, demo), encoding="utf-8")
    if not demo:
        resumo = {"gerado_em": datetime.now().isoformat(timespec="minutes"),
                  "regras": {"base": analise.JANELA_BASE, "pre": analise.JANELA_PRE, "black_friday": analise.JANELA_BF,
                             "limiar": analise.LIMIAR, "dias_min_base": analise.DIAS_MIN_BASE, "dias_min_bf": analise.DIAS_MIN_BF},
                  "contagem": dict(prod["contagem"]), "por_loja": prod["por_loja"], "por_grupo": prod["por_grupo"],
                  "variacao_mediana": prod["variacao_mediana"], "lista": lista}
        (PASTA / "docs" / "black-friday-resultados.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    validos = sum(v for k, v in prod["contagem"].items() if k != analise.INSUFICIENTE)
    print(f"\n{'PRÉVIA COM DADOS SIMULADOS' if demo else 'Análise com o historico.db'}")
    print(f"Produtos com dados suficientes: {validos} (insuficientes: {prod['contagem'].get(analise.INSUFICIENTE, 0)})")
    for k in analise.CLASSES:
        print(f"  {k:<24} {prod['contagem'].get(k, 0)}")
    for g, cont in prod["por_grupo"].items():
        n = sum(cont.values())
        print(f"  [{analise.NOMES_GRUPO.get(g, g)}] maquiagem: {cont.get(analise.MAQUIAGEM, 0) / n:.0%} de {n} produtos")
    print(f"Relatório: {destino_html}")


if __name__ == "__main__":
    main()
