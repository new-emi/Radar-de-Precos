# unidades.py — descobre a quantidade no título do produto e calcula o preço por unidade
#
# Exemplos:
#   "Amaciante Comfort 1,5L"                 -> 1500 ml   -> R$ x / litro
#   "Creme Dental Colgate 180g 3 un"         -> 540 g     -> R$ x / 100 g
#   "Papel Toalha Scala Plus 3x120fls"       -> 360 folhas-> R$ x / 100 folhas
#   "Fio Dental Colgate 50m"                 -> 50 m      -> R$ x / 10 metros
#   "Aparelho de Barbear Probak 7 un"        -> 7 un      -> R$ x / unidade
#
# A técnica usada é EXPRESSÃO REGULAR (regex): um "padrão de texto" que acha trechos como
# "número + espaço opcional + unidade" em qualquer lugar do título.
import re

NUM = r"(\d+(?:[.,]\d+)?)"   # 180 | 1,5 | 1.5

# Padrões (compilados uma vez só, para ficar rápido)
RE_VOLUME = re.compile(NUM + r"\s*(ml|l|lt|litros?)\b", re.I)
RE_PESO = re.compile(NUM + r"\s*(mg|g|gr|gramas?|kg|quilos?)\b", re.I)
RE_FOLHAS_MULT = re.compile(r"(\d+)\s*x\s*(\d+)\s*(?:fls?|folhas|toalhas)\b", re.I)    # 3x120fls
RE_FOLHAS = re.compile(r"(\d+)\s*(?:fls?|folhas|toalhas)\b", re.I)                     # 360 folhas
RE_MULT_X = re.compile(r"\b(\d+)\s*x\s*\d+(?:[.,]\d+)?\s*(?:ml|l|g|gr|kg)\b", re.I)   # 2x180g / 3 x 1L
RE_METRO = re.compile(NUM + r"\s*(?:m|mt|mts|metros?)\b", re.I)                       # 50m / 7,5 m / 75mts
RE_CONTAGEM = re.compile(
    # kit 3 / leve 3 / c/ 2  — o (?!\s*%) evita ler "com 10% de desconto" como 10 unidades
    r"(?:\b(?:kit|leve|c/|com|pack|pacote|caixa)\s*(?:com\s*)?(\d+)\b(?!\s*%))"
    r"|(?:\b(\d+)\s*(?:un|und|unid|unidades?|undiades|rolos?|pacotes?|pcts?|refis|cargas?|sacos)\b)",  # 3 un / 2 rolos
    re.I)


def _num(txt):
    return float(txt.replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}(\.\d{3})+", txt) \
        else float(txt.replace(",", "."))


def _contagem(titulo):
    """Quantas embalagens vêm no anúncio e qual palavra indicou isso. (1, '') se não disser."""
    m = RE_MULT_X.search(titulo)
    if m:
        return int(m.group(1)), "x"
    for m in RE_CONTAGEM.finditer(titulo):
        n = int(m.group(1) or m.group(2))
        # "kit 3" aceita até 48; com palavra de unidade explícita ("80 unidades") aceita até 500.
        limite = 48 if m.group(1) else 500
        if 1 < n <= limite:
            return n, m.group(0).lower()
    return 1, ""


# Produtos em que "50L" / "500ml" é a CAPACIDADE (cabe), não o conteúdo: compara por unidade
RE_CAPACIDADE = re.compile(r"\b(saco|sacos|lixeira|balde|borrifador|pulverizador|pote|garrafa|galão vazio|frasco vazio)\b", re.I)

RE_UN_GRANDE = re.compile(r"\b(\d{2,5})\s*(?:un|unid|unidades)\b", re.I)   # "1000 un" de papel interfolhado


def quantidade(titulo):
    """Devolve (quantidade_total, tipo) com tipo em 'ml', 'g', 'folhas', 'un'; ou (None, None)."""
    t = titulo or ""
    n, palavra = _contagem(t)

    m = None if RE_CAPACIDADE.search(t) else RE_VOLUME.search(t)
    if m:
        v = _num(m.group(1))
        ml = v * 1000 if m.group(2).lower().startswith("l") else v
        if 5 <= ml <= 20000:
            return ml * n, "ml"

    m = RE_PESO.search(t)
    if m:
        v, u = _num(m.group(1)), m.group(2).lower()
        g = v * 1000 if u.startswith(("kg", "quilo")) else v / 1000 if u == "mg" else v
        if 5 <= g <= 50000:
            return g * n, "g"

    m = RE_FOLHAS_MULT.search(t)
    if m:
        return int(m.group(1)) * int(m.group(2)), "folhas"
    m = RE_FOLHAS.search(t)
    if m and int(m.group(1)) >= 10:
        folhas = int(m.group(1))
        # "3 rolos 360 folhas": no Brasil o número costuma ser o TOTAL.
        # "3 pacotes 120 fls" / "kit 3": aí é por pacote, então multiplica.
        if any(w in palavra for w in ("pacote", "pct", "kit", "caixa", "leve")):
            folhas *= n
        return folhas, "folhas"
    m = RE_UN_GRANDE.search(t)
    if m and int(m.group(1)) >= 50 and re.search(r"papel|toalha|guardanapo|len[çc]o", t, re.I) \
            and not re.search(r"higi[eê]nico", t, re.I):
        return int(m.group(1)), "folhas"

    m = RE_METRO.search(t)
    if m:
        metros = _num(m.group(1))
        if 1 <= metros <= 2000:
            return metros * n, "m"     # "20m 12 rolos" de papel higiênico -> 240 m

    if n > 1:
        return n, "un"
    return None, None


# Como mostrar cada tipo: (divisor, rótulo). Ex.: ml -> preço por 1000 ml = "/L"
BASE = {"ml": (1000, "L"), "g": (100, "100g"), "folhas": (100, "100 folhas"), "m": (10, "10m"), "un": (1, "un")}


def item_pequeno(titulos):
    """True se os produtos de um item costumam vir em frasco pequeno (mediana abaixo de 1 litro).
    Aí o preço é mostrado por 100 ml (protetor solar, óleo capilar), e não por litro (amaciante).
    Vale para o ITEM inteiro, para todos os produtos dele ficarem na mesma régua."""
    vols = sorted(q for q, tipo in map(quantidade, titulos) if tipo == "ml")
    return bool(vols) and vols[len(vols) // 2] < 1000


def preco_por_unidade(titulo, preco, pequeno=False):
    """Devolve (valor, rótulo) — ex.: (15.18, 'L') — ou (None, None) se o título não disser a quantidade.
    pequeno=True troca a régua dos líquidos de 'por litro' para 'por 100 ml'."""
    q, tipo = quantidade(titulo)
    if not q or not preco:
        return None, None
    divisor, rotulo = (100, "100ml") if (tipo == "ml" and pequeno) else BASE[tipo]
    return round(preco / q * divisor, 2), rotulo


def texto_preco_unidade(titulo, preco, pequeno=False):
    """'R$ 15,18/L' ou '' — pronto para mostrar na tela."""
    v, rot = preco_por_unidade(titulo, preco, pequeno)
    if v is None:
        return ""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + f"/{rot}"
