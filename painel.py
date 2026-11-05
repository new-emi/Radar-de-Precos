# painel.py — o SITE do Radar de Preços (rode: streamlit run painel.py)
#
# A lógica (lojas, IA, banco, preço por unidade) fica no pacote radar/; este arquivo cuida só da tela.
#
# Estrutura:
#   Faixa do topo        -> nome, quanto a lista custa hoje (etiqueta amarela) e lojas consultadas
#   Aba Ofertas          -> por item: etiqueta da melhor escolha + todas as ofertas em linhas
#   Aba Lista de compras -> adicionar/remover itens, ver o último melhor preço, sugestões da IA
#   Aba Buscar preços    -> um botão; progresso item por item; pausa amigável se o ML pedir verificação
#
# Detalhes técnicos (Chrome, porta 9222, log) ficam escondidos: quem usa o painel não precisa vê-los.
import hmac
import html
import json
import os
import re
import subprocess
import sys

import streamlit as st

from radar import banco                                     # histórico (SQLite)
from radar.config import ARQ_DADOS, ARQ_LISTA, PASTA, ler_env
from radar.ia import criar_cliente_ia as cliente_ia
from radar.lojas import lojas_ativas
from radar.navegador import abrir_chrome as preparar_navegador
from radar.texto import chave_produto, titulo_pela_url
from radar.unidades import item_pequeno, preco_por_unidade

COR_LOJA = {"Mercado Livre": "#E0B400", "Americanas": "#E3001B", "Atacadão": "#F26A10",
            "Magalu": "#0086FF", "Amazon": "#FF9900", "Muffato": "#8E1B2C"}

# Emoji por palavra-chave: só para dar cara a cada item da lista
EMOJIS = [("amaciante", "🧺"), ("sabão", "🧼"), ("sabao", "🧼"), ("detergente", "🧽"), ("esponja", "🧽"),
          ("barbeador", "🪒"), ("aparelho de barbear", "🪒"), ("creme dental", "🦷"), ("pasta de dente", "🦷"),
          ("escova", "🪥"), ("papel toalha", "🧻"), ("papel higi", "🧻"), ("guardanapo", "🧻"),
          ("shampoo", "🧴"), ("condicionador", "🧴"), ("sabonete", "🧴"), ("desodorante", "🧴"),
          ("café", "☕"), ("cafe", "☕"), ("arroz", "🍚"), ("feijão", "🫘"), ("feijao", "🫘"), ("leite", "🥛"),
          ("óleo", "🫒"), ("oleo", "🫒"), ("água sanitária", "🧪"), ("desinfetante", "🧪"), ("limpador", "🧪"),
          ("fralda", "👶"), ("barbear", "🪒"), ("ração", "🐾"), ("racao", "🐾")]


def emoji_do_item(nome):
    n = nome.lower()
    return next((e for chave, e in EMOJIS if chave in n), "🛒")


# =============================================================== utilidades
def esc(t):
    return html.escape(str(t or ""))


def preco_partes(v):
    """7.59 -> ('7', '59');  1234.5 -> ('1.234', '50')"""
    inteiro, cent = f"{v:,.2f}".split(".")
    return inteiro.replace(",", "."), cent


def preco_txt(v):
    i, c = preco_partes(v)
    return f"R$ {i},{c}"


def preco_de_texto(t):
    m = re.search(r"([\d\.]+,\d{2})", str(t or ""))
    return float(m.group(1).replace(".", "").replace(",", ".")) if m else None


def html_limpo(s):
    """Tira a indentação de cada linha. Sem isso, o Markdown do Streamlit entende linhas
    com 4+ espaços como BLOCO DE CÓDIGO (era o bug do HTML aparecendo cru na tela)."""
    return " ".join(linha.strip() for linha in s.splitlines() if linha.strip())


def mostrar(s):
    st.markdown(html_limpo(s), unsafe_allow_html=True)


ARQ_EXEMPLO = PASTA / "exemplos" / "dados_exemplo.json"


def carregar_dados():
    """Devolve (itens, data_da_coleta, status_lojas). Aceita o formato antigo e o novo do JSON.
    Sem nenhuma busca feita ainda (ex.: quem acabou de clonar o projeto), mostra os dados de exemplo."""
    arquivo = ARQ_DADOS if ARQ_DADOS.exists() else ARQ_EXEMPLO
    st.session_state["modo_exemplo"] = arquivo == ARQ_EXEMPLO
    if not arquivo.exists():
        return {}, None, {}
    bruto = json.loads(arquivo.read_text(encoding="utf-8"))
    if "itens" in bruto:
        itens, quando, lojas = bruto["itens"], bruto.get("atualizado_em"), bruto.get("lojas", {})
    else:
        itens, quando, lojas = bruto, None, {}
    for info in itens.values():
        for p in info.get("produtos", []):
            if (p.get("titulo") or "").strip().lower() in ("imagem do produto", "sem título", "full", ""):
                p["titulo"] = titulo_pela_url(p.get("link", "")) or "Produto sem nome"
        for r in info.get("recomendacoes_ia", []):
            if r.get("preco_num") is None:
                r["preco_num"] = preco_de_texto(r.get("preco"))
    return itens, quando, lojas


def melhor_do_item(info):
    """(preço, loja) da melhor escolha do item: a da IA, ou o menor preço se a IA não analisou."""
    recs = info.get("recomendacoes_ia") or []
    if recs and recs[0].get("preco_num") is not None:
        return recs[0]["preco_num"], recs[0].get("loja")
    if info.get("produtos"):
        p = info["produtos"][0]
        return p["preco"], p["loja"]
    return None, None


def ler_lista():
    if not ARQ_LISTA.exists():
        return []
    return [l.strip() for l in ARQ_LISTA.read_text(encoding="utf-8").splitlines() if l.strip()]


def salvar_lista(itens):
    ARQ_LISTA.write_text("".join(f"{str(i).strip()}\n" for i in itens if str(i).strip()), encoding="utf-8")


def na_loja(loja):
    """'no Mercado Livre', 'no Atacadão', 'na Amazon'..."""
    return f"no {loja}" if loja in ("Mercado Livre", "Atacadão") else f"na {loja}"


def ponto(loja):
    return f'<span class="ponto" style="background:{COR_LOJA.get(loja, "#999")}"></span>'


def chip_loja(loja):
    cor = COR_LOJA.get(loja, "#999999")
    return f'<span class="chip-loja" style="background:{cor}1F; color:#1C2B23">{ponto(loja)}{esc(loja)}</span>'


# =================================================================== estilo
st.set_page_config(page_title="Radar de Preços", page_icon="🏷️", layout="wide")

# O visual (CSS) fica em radar/estilo.css, separado do código
mostrar("<style>" + (PASTA / "radar" / "estilo.css").read_text(encoding="utf-8") + "</style>")


# ==================================================================== senha
# Se o .env tiver PAINEL_SENHA=..., o painel pede a senha antes de mostrar qualquer coisa,
# MAS só para quem acessa pela internet (o link do túnel). Quem abre no próprio PC (localhost)
# ou na rede de casa entra direto.
# Como o painel sabe? Todo pedido de página traz o cabeçalho "Host" com o endereço digitado:
# no seu PC é "localhost:8501"; pelo túnel é "algo.trycloudflare.com".
def acesso_local():
    try:
        host = (st.context.headers.get("Host") or "").split(":")[0].lower()
    except Exception:
        return False                       # sem como saber: na dúvida, pede a senha
    return host in ("localhost", "127.0.0.1") or host.startswith(("192.168.", "10."))


def pedir_senha():
    senha = ler_env().get("PAINEL_SENHA", "")
    if not senha or acesso_local() or st.session_state.get("liberado"):
        return
    mostrar("""
    <div class="faixa" style="max-width:520px; margin:3rem auto 1.2rem;">
      <h1 style="font-size:2.2rem">Radar de Preços</h1>
      <p class="sub">Digite a senha para ver as ofertas.</p>
    </div>""")
    _, meio, _ = st.columns([1, 2, 1])
    with meio:
        with st.form("senha", border=False):
            digitada = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", width="stretch"):
                # compare_digest compara sem "vazar" pelo tempo de resposta quantas letras acertaram
                if hmac.compare_digest(digitada.strip(), senha):
                    st.session_state["liberado"] = True
                    st.rerun()
                st.error("Senha errada. Tente de novo.")
    st.stop()   # nada abaixo daqui roda sem a senha


pedir_senha()


# ================================================================ faixa do topo
itens, atualizado_em, status_lojas = carregar_dados()
if st.session_state.get("modo_exemplo") and itens:
    st.info("Você está vendo **dados de exemplo**. Rode a primeira busca na aba *Buscar preços* "
            "para ver os preços da sua lista.", icon="🧪")

total, com_preco = 0.0, 0
for info in itens.values():
    v, _ = melhor_do_item(info)
    if v:
        total += v
        com_preco += 1

tag_total = ""
if com_preco:
    i, c = preco_partes(total)
    tag_total = f"""
    <div class="tag-total">
      <div class="rotulo">A lista toda sai por</div>
      <div class="valor"><span class="rs">R$</span><span class="int">{i}</span><span class="cent">,{c}</span></div>
    </div>"""

chips = []
if atualizado_em:
    chips.append(f'<span class="quando">Preços de {esc(atualizado_em)}</span>')
for loja in lojas_ativas():
    n = status_lojas.get(loja) if status_lojas else None
    falhou = status_lojas and not n
    chips.append(f'<span class="loja {"falhou" if falhou else ""}" title="{n or 0} ofertas">{ponto(loja)}{loja}</span>')

mostrar(f"""
<div class="faixa">
  <div class="linha-topo">
    <div>
      <h1>Radar de Preços</h1>
      <p class="sub">A lista de compras da casa, comparada em várias lojas para achar o melhor preço da Black Friday.</p>
    </div>
    {tag_total}
  </div>
  <div class="lojas">{"".join(chips)}</div>
</div>
""")

aba_ofertas, aba_lista, aba_buscar = st.tabs(["🏷️ Ofertas", "📝 Lista de compras", "🔎 Buscar preços"])


# ================================================================== ofertas
def etiqueta_html(rec, titulo="Melhor escolha"):
    v = rec.get("preco_num")
    i, c = preco_partes(v) if v is not None else ("?", "")
    cent = f'<span class="cent">,{c}</span>' if c else ""
    motivo = f'<p class="motivo">{esc(rec.get("motivo"))}</p>' if rec.get("motivo") else ""
    return f"""
    <div class="etiqueta">
      <div class="quem">{titulo}</div>
      <div class="preco"><span class="rs">R$</span><span class="int">{i}</span>{cent}</div>
      {f'<div class="unid">{rec["_pu"]}</div>' if rec.get("_pu") else ''}
      <div class="nome">{esc(rec.get('produto'))}</div>
      {chip_loja(rec.get('loja'))}
      {motivo}
      <a class="ir" href="{esc(rec.get('link') or '#')}" target="_blank" rel="noopener">Ver oferta na loja</a>
    </div>"""


def alternativa_html(rec):
    v = rec.get("preco_num")
    valor = preco_txt(v) if v is not None else esc(rec.get("preco"))
    return f"""
    <div class="alt">
      <div class="quem">Também vale a pena {chip_loja(rec.get('loja'))}</div>
      <div class="linha1"><a href="{esc(rec.get('link') or '#')}" target="_blank" rel="noopener">{esc(rec.get('produto'))}</a>
      <span class="v">{valor}</span></div>
      <div class="motivo">{esc(rec.get('motivo'))}</div>
    </div>"""


def link_da_rec(rec, produtos):
    """Recomendações do formato antigo não tinham link: tenta achar pelo título."""
    if rec.get("link"):
        return rec["link"]
    alvo = (rec.get("produto") or "").lower()
    for p in produtos:
        t = p["titulo"].lower()
        if t[:15] in alvo or alvo[:15] in t:
            return p["link"]
    return None


# Como dizer cada régua de comparação para quem está lendo
REGUA_TXT = {"L": "por litro", "100g": "por 100 g", "100 folhas": "por 100 folhas", "10m": "por 10 m",
             "un": "por unidade", "preco": ""}


def selo_historico(termo, info):
    """Selo ao lado do nome do item: quanto a melhor escolha de hoje mudou em relação aos dias anteriores.
    A comparação é pelo preço por unidade (a melhor escolha pode ser outro tamanho de embalagem);
    veja banco.variacao."""
    hoje, _ = melhor_do_item(info)
    try:
        var = banco.variacao(termo)
        menor = banco.menor_ja_visto(termo)
        n_dias = len(banco.historico_diario(termo, 15))
    except Exception:
        return ""
    if n_dias < 2:
        return '<span class="selo neutro">Primeiro dia de histórico</span>'
    if var is None:
        selo = ""          # a melhor escolha mudou para um produto que não dá para comparar
    else:
        pequeno = item_pequeno([p["titulo"] for p in info.get("produtos", []) if not p.get("titulo_aproximado")])
        # a % é a mesma por litro ou por 100 ml; o texto acompanha o que o painel mostra nas ofertas
        regua = "por 100 ml" if (var["regua"] == "L" and pequeno) else REGUA_TXT.get(var["regua"], "")
        extra = f" ({regua})" if regua else ""
        if var["pct"] <= -1:
            selo = f'<span class="selo caiu">↓ {abs(var["pct"]):.0f}% abaixo dos últimos dias{extra}</span>'
        elif var["pct"] >= 1:
            selo = f'<span class="selo subiu">↑ {var["pct"]:.0f}% acima dos últimos dias{extra}</span>'
        else:
            selo = '<span class="selo neutro">Preço estável</span>'
    if menor and hoje and menor[0] < hoje - 0.009:
        dia = f"{menor[1][8:10]}/{menor[1][5:7]}"
        selo += f' <span class="selo neutro">Este produto já custou {preco_txt(menor[0])} em {dia}</span>'
    return selo


def unidades_confiaveis(produtos):
    """{link: (valor, rótulo)} só com preços por unidade plausíveis.
    Descarta os absurdamente baratos (menos de 1/4 da mediana do item na mesma unidade):
    quase sempre é título sem vírgula, tipo '15l' que na verdade era '1,5l'."""
    pequeno = item_pequeno([p["titulo"] for p in produtos if not p.get("titulo_aproximado")])
    brutos = {p["link"]: preco_por_unidade(p["titulo"], p["preco"], pequeno) for p in produtos
              if not p.get("titulo_aproximado")}   # título vindo da URL perde a vírgula: não confiar
    por_rot = {}
    for v, rot in brutos.values():
        if v is not None:
            por_rot.setdefault(rot, []).append(v)
    mediana = {rot: sorted(vs)[len(vs) // 2] for rot, vs in por_rot.items()}
    return {link: (v, rot) for link, (v, rot) in brutos.items()
            if v is not None and (len(por_rot[rot]) < 3 or v >= mediana[rot] / 4)}


def texto_unidade(v, rot):
    return f"{preco_txt(v)}/{rot}" if v is not None else ""


def ordenar(produtos, modo):
    if modo != "Preço por unidade":
        return produtos
    conf = unidades_confiaveis(produtos)
    rotulos = [conf.get(p["link"], (None, None))[1] for p in produtos]
    comum = max(set(r for r in rotulos if r), key=rotulos.count, default=None)

    def chave(p):
        pu, rot = conf.get(p["link"], (None, None))
        # primeiro os que usam a unidade mais comum do item (para comparar laranja com laranja)
        return (0 if rot == comum else 1 if pu else 2, pu if pu is not None else 0, p["preco"])
    return sorted(produtos, key=chave)


def serie_do_grafico(termo, pequeno=False):
    """Os pontos do gráfico: [(dia, valor, dica)], o rótulo da régua e a explicação embaixo.
    Usa o preço por unidade quando dá (a embalagem da melhor escolha muda entre os dias);
    senão, o preço dos dias em que a comparação faz sentido (veja banco.comparaveis)."""
    hist = banco.escolhas_por_dia(termo, 30)
    if not hist:
        return [], "", ""
    hoje = hist[-1]
    regua, pares = banco.comparaveis(hoje, hist[:-1])
    pares.append((hoje["dia"], hoje["pu"] if regua != "preco" else hoje["preco"]))
    por_dia = {e["dia"]: e for e in hist}
    fator, rot = 1, regua
    if regua == "L" and pequeno:           # frasco pequeno: o painel mostra por 100 ml
        fator, rot = 10, "100ml"
    pontos = []
    for dia, v in pares:
        e = por_dia[dia]
        dica = f"{e['titulo']} · {preco_txt(e['preco'])} {na_loja(e['loja'])}"
        pontos.append((dia, v / fator, dica))
    if regua == "preco":
        nota = "Preço da melhor escolha em cada dia."
    else:
        nota = (f"Preço {REGUA_TXT.get(regua, '')} da melhor escolha em cada dia" if rot != "100ml"
                else "Preço por 100 ml da melhor escolha em cada dia")
        nota += ". A melhor escolha pode ser outro tamanho de embalagem de um dia para o outro, por isso a comparação é por unidade."
    return pontos, ("" if regua == "preco" else rot), nota


def grafico_historico(termo, pequeno=False):
    try:
        pontos, rot, nota = serie_do_grafico(termo, pequeno)
        n_dias = len(banco.historico_diario(termo, 30))
    except Exception:
        pontos, rot, nota, n_dias = [], "", "", 0
    if len(pontos) < 2:
        if n_dias == 1:
            dia = f"{pontos[0][0][8:10]}/{pontos[0][0][5:7]}"
            st.caption(f"Por enquanto este item só tem preço de **um dia** ({dia}). O gráfico aparece a partir do "
                       "segundo dia, e a busca automática diária enche o histórico sozinha. "
                       "Se o nome do item mudar (ex.: “shampoo dove” → “shampoo dove 400ml”), o histórico começa de novo.")
        elif n_dias > 1:
            st.caption("A melhor escolha de hoje é um produto diferente dos outros dias, e o título não diz a quantidade "
                       "para comparar por unidade. O gráfico volta quando houver mais dias comparáveis.")
        else:
            st.caption("Este item ainda não tem histórico de preço.")
        return
    # No Markdown do Streamlit, texto entre dois "$" vira fórmula matemática (LaTeX).
    # Trocando "$" pelo código HTML "&#36;", o navegador mostra o cifrão e o Markdown não monta fórmula.
    mostrar(svg_historico(pontos, rot).replace("$", "&#36;"))
    st.caption(nota)


def svg_historico(pontos, rot=""):
    """Desenha o gráfico de linha em SVG, à mão (sem pandas): o Controle Inteligente de Aplicativos
    do Windows bloqueia as partes compiladas do pandas. SVG é só texto, então nada é bloqueado.

    pontos = [(dia, valor, dica)]; rot = a unidade do eixo ("L", "100g"...) ou "" para preço.
    Ideia: cada dia vira um ponto (x = posição do dia, y = valor). O SVG desenha a linha ligando
    os pontos; o eixo y vai do menor ao maior valor (com folga), para a variação ficar visível."""
    larg, alt, esq, dir_, topo, base = 640, 200, 92 if rot else 64, 24, 22, 34
    valores = [v for _, v, _ in pontos]
    lo, hi = min(valores), max(valores)
    folga = (hi - lo) * 0.15 or hi * 0.05 or 1
    lo, hi = max(0, lo - folga), hi + folga
    sufixo = f"/{rot}" if rot else ""

    def x(i):
        return esq + (larg - esq - dir_) * (i / (len(pontos) - 1))

    def y(v):
        return topo + (alt - topo - base) * (1 - (v - lo) / (hi - lo))

    linha = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v, _) in enumerate(pontos))
    area = f"{x(0):.1f},{alt - base} {linha} {x(len(pontos) - 1):.1f},{alt - base}"
    # 4 linhas de grade; se duas caem no mesmo valor em centavos (ex.: R$ 0,40/un e R$ 0,40/un), só uma fica
    marcas = {}
    for v in (lo + (hi - lo) * k / 3 for k in range(4)):
        marcas.setdefault(preco_txt(v), v)
    grade = "".join(
        f'<line x1="{esq}" x2="{larg - dir_}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#DCE3DC" stroke-width="1"/>'
        f'<text x="{esq - 8}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#5F6C64" font-size="12" font-family="Instrument Sans, sans-serif">{txt}{esc(sufixo)}</text>'
        for txt, v in marcas.items())
    dias = "".join(
        f'<text x="{x(i):.1f}" y="{alt - 10}" text-anchor="middle" fill="#5F6C64" font-size="12" font-family="Instrument Sans, sans-serif">{d[8:10]}/{d[5:7]}</text>'
        for i, (d, _, _) in enumerate(pontos) if len(pontos) <= 8 or i in (0, len(pontos) - 1) or i % 5 == 0)
    bolinhas = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="{5 if i == len(pontos) - 1 else 3.2}" fill="#FFFFFF" stroke="#17804A" stroke-width="2">'
        f'<title>{d[8:10]}/{d[5:7]}: {preco_txt(v)}{esc(sufixo)} · {esc(dica)}</title></circle>'
        for i, (d, v, dica) in enumerate(pontos))
    ultimo = pontos[-1][1]
    return (f'<svg class="grafico" style="width:100%;height:auto;display:block" viewBox="0 0 {larg} {alt}" role="img" '
            f'aria-label="Preço da melhor escolha nos últimos {len(pontos)} dias; hoje {preco_txt(ultimo)}{esc(sufixo)}">'
            f'{grade}<polygon points="{area}" fill="#DDF0E3" opacity="0.6"/><polyline points="{linha}" fill="none" stroke="#17804A" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            f'{bolinhas}{dias}</svg>')


def mostrar_item(termo, info, modo="Menor preço"):
    todos = ordenar(info.get("produtos", []), modo)
    produtos = [p for p in todos if not p.get("fora_do_pedido")]       # o que é o produto pedido
    fora = [p for p in todos if p.get("fora_do_pedido")]               # a IA disse que não é
    recs = info.get("recomendacoes_ia") or []
    for r in recs:
        r["link"] = link_da_rec(r, produtos)
    escolhidos = {r["link"] for r in recs if r.get("link")}
    n_lojas = len({p["loja"] for p in produtos})
    conf_item = unidades_confiaveis(produtos)          # mesma régua (R$/L ou R$/100ml) no item todo
    for r in recs:
        r["_pu"] = texto_unidade(*conf_item.get(r.get("link"), (None, None)))

    mostrar(f"""
    <div class="item-titulo"><span class="emoji">{emoji_do_item(termo)}</span>
    <div class="nome-item" role="heading" aria-level="2">{esc(termo.capitalize())}</div>
    <span class="conta">{len(produtos)} ofertas em {n_lojas} {'loja' if n_lojas == 1 else 'lojas'}</span>
    {selo_historico(termo, info)}</div>
    """)
    try:
        antes = banco.precos_anteriores(termo)
    except Exception:
        antes = {}

    esq, dir_ = st.columns([5, 7], gap="large")
    with esq:
        if recs:
            mostrar(etiqueta_html(recs[0]) + "".join(alternativa_html(r) for r in recs[1:]))
        elif produtos:
            p = produtos[0]
            mostrar(etiqueta_html({"produto": p["titulo"], "loja": p["loja"], "preco_num": p["preco"], "link": p["link"],
                                   "_pu": texto_unidade(*conf_item.get(p["link"], (None, None)))},
                                  titulo="Menor preço encontrado"))
        else:
            mostrar('<div class="vazio">Nenhuma oferta encontrada para este item.</div>')
    with dir_:
        def delta(p):
            ant = antes.get(chave_produto(p["link"], p["loja"]))
            if ant is None or abs(ant - p["preco"]) < 0.01:
                return ""
            caiu = p["preco"] < ant
            return f'<span class="delta {"caiu" if caiu else "subiu"}">{"↓" if caiu else "↑"} {preco_txt(abs(ant - p["preco"]))}</span>'

        conf = unidades_confiaveis(produtos)

        def linha(p):
            pu = texto_unidade(*conf.get(p["link"], (None, None)))
            return f"""
            <li class="{'escolhida' if p['link'] in escolhidos else ''}">
              {chip_loja(p['loja'])}
              <div class="meio"><a href="{esc(p['link'])}" target="_blank" rel="noopener" title="{esc(p['titulo'])}">{esc(p['titulo'])}</a>
              {f'<span class="pu">{pu}</span>' if pu else ''}</div>
              <div class="dir"><span class="valor">{preco_txt(p['preco'])}</span>{delta(p)}</div>
            </li>"""
        bloco_fora = ""
        if fora:
            bloco_fora = (f'<details class="fora"><summary>As lojas também mostraram {len(fora)} '
                          f'{"produto" if len(fora) == 1 else "produtos"} que não {"é" if len(fora) == 1 else "são"} '
                          f'“{esc(termo)}” (a IA tirou da comparação)</summary>'
                          f'<ol class="ofertas">{"".join(linha(p) for p in fora)}</ol></details>')
        mostrar(f'<ol class="ofertas">{"".join(linha(p) for p in produtos)}</ol>{bloco_fora}')
        with st.expander("📈 Histórico de preço"):
            grafico_historico(termo, item_pequeno([p["titulo"] for p in produtos if not p.get("titulo_aproximado")]))


with aba_ofertas:
    if not itens:
        mostrar('<div class="vazio" style="margin-top:1.2rem">Ainda não há preços. '
                'Abra a aba <b>Buscar preços</b> para fazer a primeira busca.</div>')
    else:
        nomes = list(itens.keys())
        c_itens, c_ordem = st.columns([3, 1.2], vertical_alignment="bottom")
        opcoes = ["Todos os itens"] + [f"{emoji_do_item(n)} {n.capitalize()}" for n in nomes]
        with c_itens:
            # caixa de escolha (dá para digitar e procurar): ocupa pouco espaço com qualquer tamanho de lista
            escolha = st.selectbox("Mostrar item", opcoes, index=0, help="Digite para procurar um item da lista")
        with c_ordem:
            modo = st.segmented_control("Ordenar ofertas por", ["Menor preço", "Preço por unidade"],
                                        default="Menor preço") or "Menor preço"
        for termo in nomes:
            if escolha in (None, "Todos os itens") or escolha == f"{emoji_do_item(termo)} {termo.capitalize()}":
                mostrar_item(termo, itens[termo], modo)


# ========================================================= lista de compras
# As ações da lista usam CALLBACKS (on_change / on_click): funções que o Streamlit roda ANTES de
# redesenhar a página. Assim o item é salvo no instante em que a pessoa aperta Enter, toca fora do
# campo ou aperta "Adicionar" — não dá para "digitar e esquecer de salvar".
def adicionar_item():
    novo = (st.session_state.get("novo_item") or "").strip()
    if not novo:
        return
    atual = ler_lista()                       # sempre relê o arquivo: outra pessoa pode ter mexido
    if novo.lower() in (x.lower() for x in atual):
        st.session_state["aviso_lista"] = f"“{novo}” já está na lista."
    else:
        salvar_lista(atual + [novo])
        st.session_state["aviso_lista"] = f"“{novo}” entrou na lista."
    st.session_state["novo_item"] = ""       # limpa o campo


def remover_item(item):
    atual = ler_lista()
    if item in atual:
        st.session_state["desfazer"] = (atual.index(item), item)   # guarda para poder desfazer
        salvar_lista([x for x in atual if x != item])


def desfazer_remocao():
    pos, item = st.session_state.pop("desfazer", (None, None))
    if item:
        atual = ler_lista()
        if item not in atual:
            atual.insert(min(pos, len(atual)), item)
            salvar_lista(atual)


with aba_lista:
    lista = ler_lista()
    mostrar(f"""
    <div class="titulo-aba">Lista de compras</div>
    <p class="desc-aba">{len(lista)} {'item' if len(lista) == 1 else 'itens'} na lista.
    Tudo o que estiver aqui entra na próxima busca de preços.</p>""")

    col_lista, col_dicas = st.columns([7, 4], gap="large")

    with col_lista:
        c_in, c_bt = st.columns([5, 1.4], vertical_alignment="bottom")
        c_in.text_input("Adicionar item", placeholder="Ex.: sabão em pó omo 1,6kg",
                        key="novo_item", on_change=adicionar_item)
        c_bt.button("Adicionar", type="primary", width="stretch", on_click=adicionar_item)
        if st.session_state.get("aviso_lista"):
            st.toast(st.session_state.pop("aviso_lista"))
        if st.session_state.get("desfazer"):
            d1, d2 = st.columns([5, 1.4], vertical_alignment="center")
            d1.caption(f"“{st.session_state['desfazer'][1]}” saiu da lista.")
            d2.button("Desfazer", width="stretch", on_click=desfazer_remocao)

        if not lista:
            mostrar('<div class="vazio">A lista está vazia. Escreva o primeiro item acima.</div>')
        for idx, item in enumerate(lista):
            with st.container(border=True):
                c_txt, c_rm = st.columns([8, 1], vertical_alignment="center")
                info = itens.get(item)
                if info:
                    v, loja = melhor_do_item(info)
                    ultimo = f'Melhor preço na última busca: <b>{preco_txt(v)}</b> {esc(na_loja(loja))}' if v else "Sem ofertas na última busca"
                else:
                    ultimo = "Ainda não buscado"
                c_txt.markdown(html_limpo(f"""
                <div class="linha-item"><span class="emoji">{emoji_do_item(item)}</span>
                <div><div class="nome">{esc(item)}</div><div class="ultimo">{ultimo}</div></div></div>"""),
                               unsafe_allow_html=True)
                c_rm.button("✕", key=f"rm_{item}", help=f"Tirar {item} da lista",
                            on_click=remover_item, args=(item,))

    with col_dicas:
        mostrar("""
        <div class="dicas"><div class="t">Para a busca achar o produto certo</div>
        <ul><li>Diga a marca: <i>amaciante comfort</i></li>
        <li>Diga o tamanho: <i>creme dental 180g</i></li>
        <li>Evite nomes muito curtos, como só <i>sabão</i></li></ul></div>""")

        if st.button("✨ Pedir à IA nomes melhores", width="stretch", disabled=not lista):
            client = cliente_ia()
            if client is None:
                st.error("A IA não está configurada: falta a chave no arquivo .env.")
            else:
                with st.spinner("Pensando em nomes melhores..."):
                    prompt = f"""Reescreva os itens de compras abaixo para aumentar a chance de encontrar o produto certo
em lojas online brasileiras, sem mudar o que a pessoa quer (mantenha marca e tamanho quando houver).
Exemplo: "amaciante" -> "amaciante concentrado"; "shampoo dove" -> "shampoo dove 400ml".
Responda APENAS com JSON, na mesma ordem e com o mesmo número de itens: {{"lista": ["item 1", "item 2"]}}
Lista atual: {lista}"""
                    try:
                        resp = client.chat.completions.create(
                            model="deepseek-chat", response_format={"type": "json_object"},
                            messages=[{"role": "system", "content": "Assistente de e-commerce."},
                                      {"role": "user", "content": prompt}])
                        sug_ia = json.loads(resp.choices[0].message.content)["lista"]
                        # guarda como "de -> para", para aplicar só nos itens que existiam quando a IA respondeu
                        st.session_state["sugestao"] = dict(zip(lista, sug_ia))
                    except Exception as e:
                        st.error(f"A IA não respondeu agora. Tente de novo em instantes. ({e})")

        sug = st.session_state.get("sugestao")
        if isinstance(sug, dict) and sug:
            pares = "".join(f'<div class="par"><span class="de">{esc(a)}</span><span>→</span><span class="para">{esc(b)}</span></div>'
                            for a, b in sug.items() if a != b)
            mostrar(f'<div class="sugestao">{pares or "A IA não sugeriu mudanças."}</div>')
            s1, s2 = st.columns(2)
            if s1.button("Usar estes nomes", type="primary", width="stretch"):
                # troca só os nomes sugeridos; itens adicionados depois continuam na lista
                salvar_lista([sug.get(x, x) for x in ler_lista()])
                st.session_state.pop("sugestao")
                st.rerun()
            if s2.button("Manter os meus", width="stretch"):
                st.session_state.pop("sugestao")
                st.rerun()


# ============================================================ buscar preços
with aba_buscar:
    lista = ler_lista()
    chips_lojas = "".join(chip_loja(l) for l in lojas_ativas())
    quando = (f'<div class="quando">Última busca<b>{esc(atualizado_em)}</b></div>' if atualizado_em
              else '<div class="quando">Nenhuma busca feita ainda</div>')
    mostrar(f"""
    <div class="busca-card">
      <div>
        <div class="t">Atualizar os preços</div>
        <div class="d">Vamos procurar os {len(lista)} itens da sua lista nestas lojas, e a IA escolhe o melhor
        custo-benefício de cada um. Leva alguns minutos: pode deixar rodando.</div>
        <div class="lojas-mini">{chips_lojas}</div>
      </div>
      {quando}
    </div>""")

    if st.session_state.pop("busca_ok", False):
        st.success("Preços atualizados! Veja na aba Ofertas.")

    st.write("")
    clicou = st.button("🔎 Buscar preços agora", type="primary", disabled=not lista)

    if clicou:
        area_aviso, area_lista = st.empty(), st.empty()
        estado = {t: ("espera", "Na fila") for t in lista}

        def desenhar(fase):
            linhas = []
            for t in lista:
                classe, txt = estado.get(t, ("espera", ""))
                linhas.append(f'<li class="{classe}"><span>{emoji_do_item(t)}</span><span>{esc(t)}</span>'
                              f'<span class="estado">{esc(txt)}</span></li>')
            area_lista.markdown(html_limpo(f'<div class="desc-aba" style="margin-top:1rem">{esc(fase)}</div>'
                                           f'<ul class="progresso">{"".join(linhas)}</ul>'), unsafe_allow_html=True)

        desenhar("Preparando...")
        preparar_navegador()   # abre o navegador do robô sozinho, se precisar

        log, atual = [], None
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        # -u = sem buffer: cada print do robô chega aqui na hora, e o progresso anda ao vivo
        proc = subprocess.Popen([sys.executable, "-u", str(PASTA / "robo.py")], cwd=PASTA, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        fase = "Começando..."
        for linha in proc.stdout:
            log.append(linha.rstrip())
            l = linha.strip()
            if "ETAPA_ML" in l:
                fase = "Olhando o Mercado Livre primeiro..."
            elif "ETAPA_LOJAS" in l:
                fase = "Agora as outras lojas, item por item..."
            elif "PAUSA_VERIFICACAO" in l:
                area_aviso.markdown(html_limpo("""<div class="aviso-verif"><b>O Mercado Livre quer saber se você é uma pessoa</b>
                Abriu uma janela do navegador com uma verificação. Clique nela para confirmar.
                Assim que terminar, a busca continua sozinha.</div>"""), unsafe_allow_html=True)
            elif "VERIFICACAO_OK" in l or "pulando o Mercado Livre" in l:
                area_aviso.empty()
            m = re.match(r"\[(\d+)/(\d+)\]\s+(.+?)\.\.\.", l)
            if m:
                atual = m.group(3)
                estado[atual] = ("agora", "Procurando...")
            elif atual and "Americanas:" in l:
                n = sum(int(x) for x in re.findall(r":\s*(\d+)", l))
                estado[atual] = ("feito", f"✓ {n} ofertas")
            desenhar(fase)
        proc.wait()
        area_aviso.empty()
        st.session_state["ultimo_log"] = "\n".join(log)
        if proc.returncode == 0:
            st.session_state["busca_ok"] = True
            st.rerun()   # recarrega a página inteira com os preços novos
        st.error("A busca parou no meio por um erro. Tente de novo; se continuar, veja os detalhes técnicos abaixo.")

    if st.session_state.get("ultimo_log"):
        with st.expander("Detalhes técnicos da última busca"):
            st.code(st.session_state["ultimo_log"], language=None)
