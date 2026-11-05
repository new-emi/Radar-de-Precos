"""Análise "O desconto da Black Friday foi real?" — segue as regras de docs/METODOLOGIA_BLACK_FRIDAY.md.

Tudo aqui é Python puro + sqlite3 (sem pandas: o Controle Inteligente de Aplicativos do Windows bloqueia
as partes compiladas dele). As regras (janelas, limiar, dias mínimos) ficam em constantes no topo,
iguais às do pré-registro, para qualquer pessoa conferir que o código mede o que foi prometido.
"""
import statistics
from collections import Counter, defaultdict

from . import banco
from .config import ler_lista_estudo
from .texto import chave_produto  # noqa: F401  (usada aqui e reexportada para os testes)

# ---- regras do pré-registro (05/11/2026) ----
JANELA_BASE = ("2026-11-05", "2026-11-15")
JANELA_PRE = ("2026-11-16", "2026-11-26")
JANELA_BF = ("2026-11-27", "2026-11-30")
LIMIAR = 0.05            # 5%
DIAS_MIN_BASE = 3
DIAS_MIN_BF = 1

DESCONTO_REAL = "Desconto real"
MAQUIAGEM = "Maquiagem de desconto"
MAIS_CARO = "Ficou mais caro"
SEM_MUDANCA = "Sem mudança"
INSUFICIENTE = "Dados insuficientes"
CLASSES = [DESCONTO_REAL, MAQUIAGEM, SEM_MUDANCA, MAIS_CARO]

# Grupos: os da lista do estudo (lista_estudo.txt) e, para o resto, a lista de compras da família
GRUPO_FAMILIA = "lista_da_familia"
NOMES_GRUPO = {"casa": "Casa (controle)", "black_friday": "Típicos de Black Friday", GRUPO_FAMILIA: "Lista da família"}


def grupos_por_termo():
    """{termo normalizado: grupo} da lista do estudo."""
    return {banco.normalizar(t): g for t, g in ler_lista_estudo().items()}

def _na_janela(dia, janela):
    return janela[0] <= dia <= janela[1]


def series_por_produto(arq=None):
    """{chave: {"loja", "titulo", "termo", "dias": {dia: menor_preço_do_dia}}} a partir do historico.db."""
    con = banco.conectar(arq)
    series = {}
    for r in con.execute("""
        SELECT substr(b.data, 1, 10) AS dia, p.termo, p.loja, p.titulo, p.link, p.preco
        FROM precos p JOIN buscas b ON b.id = p.busca_id
    """):
        chave = chave_produto(r["link"], r["loja"])
        s = series.setdefault(chave, {"loja": r["loja"], "titulo": r["titulo"], "termo": r["termo"], "dias": {}})
        s["dias"][r["dia"]] = min(r["preco"], s["dias"].get(r["dia"], float("inf")))
    con.close()
    return series


def classificar(dias):
    """Recebe {dia: preço} de UM produto e devolve as métricas + a classe, pelas regras do pré-registro."""
    base = [p for d, p in dias.items() if _na_janela(d, JANELA_BASE)]
    pre = [p for d, p in dias.items() if _na_janela(d, JANELA_PRE)]
    bf = [p for d, p in dias.items() if _na_janela(d, JANELA_BF)]
    if len(base) < DIAS_MIN_BASE or len(bf) < DIAS_MIN_BF:
        return {"classe": INSUFICIENTE, "dias_base": len(base), "dias_bf": len(bf)}
    p_base = statistics.median(base)
    p_pre = max(pre) if pre else None
    p_bf = min(bf)
    if p_bf <= p_base * (1 - LIMIAR):
        classe = DESCONTO_REAL
    elif p_pre is not None and p_pre >= p_base * (1 + LIMIAR) and p_bf < p_pre:
        classe = MAQUIAGEM
    elif p_bf >= p_base * (1 + LIMIAR):
        classe = MAIS_CARO
    else:
        classe = SEM_MUDANCA
    return {"classe": classe, "p_base": p_base, "p_pre": p_pre, "p_bf": p_bf,
            "variacao": (p_bf - p_base) / p_base, "dias_base": len(base), "dias_bf": len(bf)}


def analisar_produtos(arq=None, grupos=None):
    grupos = grupos_por_termo() if grupos is None else grupos
    produtos = []
    for chave, s in series_por_produto(arq).items():
        r = classificar(s["dias"])
        produtos.append({"chave": chave, "loja": s["loja"], "titulo": s["titulo"], "termo": s["termo"],
                         "grupo": grupos.get(banco.normalizar(s["termo"]), GRUPO_FAMILIA),
                         "dias": dict(sorted(s["dias"].items())), **r})
    validos = [p for p in produtos if p["classe"] != INSUFICIENTE]
    por_loja, por_grupo = defaultdict(Counter), defaultdict(Counter)
    for p in validos:
        por_loja[p["loja"]][p["classe"]] += 1
        por_grupo[p["grupo"]][p["classe"]] += 1
    return {
        "produtos": produtos,
        "contagem": Counter(p["classe"] for p in produtos),
        "por_loja": {loja: dict(c) for loja, c in sorted(por_loja.items())},
        "por_grupo": {g: dict(c) for g, c in sorted(por_grupo.items())},
        "variacao_mediana": statistics.median([p["variacao"] for p in validos]) if validos else None,
    }


def analisar_lista(arq=None):
    """Para cada item da lista: a melhor escolha da IA, mediana da Base × menor valor da Black Friday.

    A melhor escolha muda de produto entre os dias (pacote de 16 num dia, de 48 no outro), então a
    comparação é feita pelo PREÇO POR UNIDADE (R$/L, R$/100 g...) na unidade mais comum do item.
    Item sem quantidade no título (ex.: barbeador) é comparado pelo preço.
    O total da lista é o da "mesma compra": o preço normal de cada item, corrigido pela variação dele.
    Ex.: amaciante normal R$ 20,00 e o litro 10% mais barato na Black Friday -> R$ 18,00."""
    con = banco.conectar(arq)
    termos = {}
    for (t,) in con.execute("SELECT DISTINCT termo FROM precos"):
        termos.setdefault(banco.normalizar(t), t)        # um nome por item (ignora acento/maiúscula)
    con.close()
    itens = []
    for termo in sorted(termos.values()):
        hist = banco.escolhas_por_dia(termo, dias=3650, arq=arq)
        base_dias = [e for e in hist if _na_janela(e["dia"], JANELA_BASE)]
        unidades = [e["un"] for e in base_dias if e["un"]]
        regua = max(set(unidades), key=unidades.count) if unidades else "preco"
        def valor(e):
            return e["pu"] if regua != "preco" else e["preco"]
        def usa(e):
            return e["un"] == regua if regua != "preco" else not e["un"]
        base = [e for e in base_dias if usa(e)]
        bf = [e for e in hist if _na_janela(e["dia"], JANELA_BF) and usa(e)]
        if len(base) < DIAS_MIN_BASE or not bf:
            continue
        v_base = statistics.median(valor(e) for e in base)
        melhor_bf = min(bf, key=valor)
        var = (valor(melhor_bf) - v_base) / v_base
        p_base = statistics.median(e["preco"] for e in base)   # quanto custava a compra normal do item
        p_bf = p_base * (1 + var)                               # a mesma compra, no preço da Black Friday
        itens.append({"termo": termo, "regua": regua, "p_base": p_base, "p_bf": p_bf,
                      "loja_bf": melhor_bf["loja"], "economia": p_base - p_bf, "variacao": var})
    total_base = sum(i["p_base"] for i in itens)
    total_bf = sum(i["p_bf"] for i in itens)
    return {"itens": itens, "total_base": total_base, "total_bf": total_bf,
            "economia": total_base - total_bf,
            "economia_pct": (total_base - total_bf) / total_base if total_base else None}
