# banco.py — histórico de preços em SQLite
#
# O SQLite é um banco de dados que mora num ÚNICO ARQUIVO (historico.db), sem servidor.
# Vem junto com o Python (módulo sqlite3): não precisa instalar nada.
#
# Duas tabelas:
#   buscas  -> uma linha por vez que o robô rodou            (id, data)
#   precos  -> uma linha por produto encontrado em cada busca (busca_id, termo, loja, titulo, preco, ...)
#
# "busca_id" liga cada preço à busca em que ele foi visto: isso é uma CHAVE ESTRANGEIRA.
# Com isso dá para perguntar ao banco coisas como "qual era o menor preço do papel toalha em cada dia?".
import json
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from .texto import chave_produto, titulo_pela_url
from .unidades import BASE, preco_por_unidade, quantidade

from .config import ARQ_BANCO

ESQUEMA = """
CREATE TABLE IF NOT EXISTS buscas (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL                        -- '2026-11-04 14:05:00'
);
CREATE TABLE IF NOT EXISTS precos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    busca_id      INTEGER NOT NULL REFERENCES buscas(id),
    termo         TEXT NOT NULL,              -- item da lista: 'papel toalha'
    loja          TEXT NOT NULL,
    titulo        TEXT,
    preco         REAL NOT NULL,
    link          TEXT,
    preco_unidade REAL,                       -- ex.: 15.18
    unidade       TEXT,                       -- ex.: 'L'
    escolhido_ia  INTEGER DEFAULT 0           -- 1 se foi a 1ª recomendação da IA
);
CREATE INDEX IF NOT EXISTS idx_precos_termo ON precos(termo);
CREATE INDEX IF NOT EXISTS idx_precos_link  ON precos(link);
"""


def normalizar(termo):
    """'Óleo  capilar ELSEVE' -> 'oleo capilar elseve': sem acento, minúsculo, espaços simples.
    Assim, mudar só maiúscula/acento do nome do item não começa o histórico do zero."""
    sem_acento = unicodedata.normalize("NFKD", termo or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def conectar(arq=None):
    con = sqlite3.connect(arq or ARQ_BANCO)
    con.row_factory = sqlite3.Row          # permite ler colunas pelo nome: linha["preco"]
    # Registra a função Python acima DENTRO do SQLite: o SQL passa a poder usar normalizar(...)
    con.create_function("normalizar", 1, normalizar, deterministic=True)
    con.executescript(ESQUEMA)             # cria as tabelas na primeira vez (IF NOT EXISTS)
    return con


def _link_escolhido(info):
    """Link da 1ª recomendação da IA. No formato antigo do JSON a recomendação não tinha link:
    aí acha o produto pelo nome."""
    recs = info.get("recomendacoes_ia") or []
    if not recs:
        return None
    if recs[0].get("link"):
        return recs[0]["link"]
    alvo = (recs[0].get("produto") or "").lower()
    for p in info.get("produtos", []):
        t = (p.get("titulo") or "").lower()
        if t == alvo or (t[:15] and (t[:15] in alvo or alvo[:15] in t)):
            return p.get("link")
    return None


def salvar_busca(itens, quando=None, arq=None):
    """Grava uma busca inteira. 'itens' é o mesmo dicionário que vai para o JSON."""
    quando = quando or datetime.now()
    con = conectar(arq)
    with con:                              # 'with' = transação: ou grava tudo, ou nada
        cur = con.execute("INSERT INTO buscas (data) VALUES (?)", (quando.strftime("%Y-%m-%d %H:%M:%S"),))
        busca_id = cur.lastrowid
        linhas = []
        for termo, info in itens.items():
            link_ia = _link_escolhido(info)
            for p in info.get("produtos", []):
                pu, un = (None, None) if p.get("titulo_aproximado") else preco_por_unidade(p.get("titulo"), p["preco"])
                linhas.append((busca_id, termo, p["loja"], p.get("titulo"), p["preco"], p.get("link"),
                               pu, un, int(bool(link_ia) and p.get("link") == link_ia)))
        # Os "?" são preenchidos pelo sqlite3 com segurança (nunca monte SQL juntando texto!)
        con.executemany("""INSERT INTO precos (busca_id, termo, loja, titulo, preco, link,
                           preco_unidade, unidade, escolhido_ia) VALUES (?,?,?,?,?,?,?,?,?)""", linhas)
    con.close()
    return busca_id


def importar_json_se_vazio(arq_json, arq=None):
    """Na primeira vez, aproveita a última busca do JSON como o 1º dia do histórico."""
    con = conectar(arq)
    vazio = con.execute("SELECT COUNT(*) FROM buscas").fetchone()[0] == 0
    con.close()
    if not vazio or not Path(arq_json).exists():
        return False
    bruto = json.loads(Path(arq_json).read_text(encoding="utf-8"))
    itens = bruto.get("itens", bruto)
    try:
        quando = datetime.strptime(bruto.get("atualizado_em", ""), "%d/%m/%Y %H:%M")
    except ValueError:
        quando = datetime.fromtimestamp(Path(arq_json).stat().st_mtime)
    salvar_busca(itens, quando, arq)
    return True


# ------------------------------------------------------------------ consultas
def unidade_confiavel(titulo, preco, loja, link):
    """(preço por unidade, unidade) lido do título, ou (None, None).
    Título que a Magalu só deu pela URL perde a vírgula ("1,4kg" vira "14kg"): não dá para confiar."""
    if loja == "Magalu" and titulo and titulo == titulo_pela_url(link):
        return None, None
    q, tipo = quantidade(titulo)
    if not q or not preco:
        return None, None
    # SEM arredondar: R$ 0,406/un e R$ 0,393/un viram 0,41 e 0,39 em centavos, e a diferença
    # de 3,2% viraria 4,9%. Arredondar é só para mostrar na tela, nunca antes de fazer conta.
    divisor, rotulo = BASE[tipo]
    return preco / q * divisor, rotulo


def escolhas_por_dia(termo, dias=30, arq=None):
    """Uma linha por dia: a MELHOR ESCOLHA da IA na última busca daquele dia
    (se a IA não escolheu nada, o produto mais barato da busca).
    Cada linha é um dicionário: dia, preco, loja, titulo, chave, pu (preço por unidade) e un (a unidade).

    Por que guardar o produto e não só o preço? Porque a melhor escolha muda de produto entre os dias:
    no absorvente, um dia foi o pacote de 16 e no outro o de 48. Comparar R$ 6,50 com R$ 18,87
    daria "subiu 190%", quando por unidade ficou 5% mais barato."""
    con = conectar(arq)
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    linhas = con.execute("""
        SELECT substr(b.data, 1, 10) AS dia, b.id AS busca, p.loja, p.titulo, p.preco, p.link, p.escolhido_ia
        FROM precos p JOIN buscas b ON b.id = p.busca_id
        WHERE normalizar(p.termo) = normalizar(?) AND b.data >= ?
        ORDER BY b.id
    """, (termo, desde)).fetchall()
    con.close()
    ultima_do_dia = {}
    for l in linhas:                       # buscas em ordem: a última de cada dia fica por último
        ultima_do_dia[l["dia"]] = l["busca"]
    res = []
    for dia, busca in sorted(ultima_do_dia.items()):
        da_busca = [l for l in linhas if l["busca"] == busca]
        escolhidos = [l for l in da_busca if l["escolhido_ia"]] or da_busca
        l = min(escolhidos, key=lambda l: l["preco"])
        pu, un = unidade_confiavel(l["titulo"], l["preco"], l["loja"], l["link"])
        res.append({"dia": dia, "preco": l["preco"], "loja": l["loja"], "titulo": l["titulo"],
                    "chave": chave_produto(l["link"], l["loja"]), "pu": pu, "un": un})
    return res


def historico_diario(termo, dias=30, arq=None):
    """[(dia, preço, loja)] — o preço da melhor escolha da IA em cada dia (atalho de escolhas_por_dia)."""
    return [(e["dia"], e["preco"], e["loja"]) for e in escolhas_por_dia(termo, dias, arq)]


def comparaveis(hoje, outros):
    """Quais dias de 'outros' dá para comparar com 'hoje', e por qual régua:
      1. preço por unidade, se os dois têm a MESMA unidade (R$/L com R$/L);
      2. senão, o preço, se é o MESMO produto;
      3. senão, o preço, se nenhum dos dois diz a quantidade (ex.: barbeador, escova).
    Devolve (régua, [(dia, valor)]) — régua é a unidade ('L', '100g'...) ou 'preco'."""
    if hoje["un"]:
        mesma_un = [(o["dia"], o["pu"]) for o in outros if o["un"] == hoje["un"]]
        if mesma_un:
            return hoje["un"], mesma_un
    return "preco", [(o["dia"], o["preco"]) for o in outros
                     if o["chave"] == hoje["chave"] or (not hoje["un"] and not o["un"])]


def variacao(termo, arq=None):
    """Compara a melhor escolha da última busca com a MÉDIA dos dias anteriores (até 14 dias),
    na régua certa (veja comparaveis). Devolve {"pct": -12.5, "regua": "L"} ou None.

    Variação de mais de 60% para cima ou para baixo de um dia para o outro, em produto de casa,
    quase sempre é erro de leitura do título (ex.: "8 unidades" lido como 1 unidade), então não é mostrada."""
    hist = escolhas_por_dia(termo, 15, arq)
    if len(hist) < 2:
        return None
    hoje, anteriores = hist[-1], hist[:-1]
    regua, pares = comparaveis(hoje, anteriores)
    if not pares:
        return None
    media = sum(v for _, v in pares) / len(pares)
    atual = hoje["pu"] if regua != "preco" else hoje["preco"]
    if not media or not 0.4 <= atual / media <= 1.6:
        return None
    return {"pct": round((atual - media) / media * 100, 1), "regua": regua}


def menor_ja_visto(termo, arq=None):
    """(preço, dia, loja) do menor preço já visto para o MESMO produto da melhor escolha de hoje,
    em qualquer busca anterior — ou None. Assim "já esteve R$ X" fala sempre do mesmo produto."""
    hist = escolhas_por_dia(termo, 3650, arq)
    if not hist:
        return None
    hoje = hist[-1]
    con = conectar(arq)
    linhas = con.execute("""
        SELECT substr(b.data, 1, 10) AS dia, p.preco, p.loja, p.link
        FROM precos p JOIN buscas b ON b.id = p.busca_id
        WHERE normalizar(p.termo) = normalizar(?) AND substr(b.data, 1, 10) < ?
    """, (termo, hoje["dia"])).fetchall()
    con.close()
    mesmos = [(l["preco"], l["dia"], l["loja"]) for l in linhas if chave_produto(l["link"], l["loja"]) == hoje["chave"]]
    return min(mesmos, key=lambda m: (m[0], m[1])) if mesmos else None


def precos_anteriores(termo, arq=None):
    """{chave do produto: preço} da busca ANTERIOR à última (para mostrar 'caiu R$ 1,20' em cada oferta)."""
    con = conectar(arq)
    ids = [r["busca_id"] for r in con.execute("""
        SELECT DISTINCT busca_id FROM precos WHERE normalizar(termo) = normalizar(?) ORDER BY busca_id DESC LIMIT 2
    """, (termo,))]
    res = {}
    if len(ids) == 2:
        # chave estável: na Amazon o link muda a cada busca, mas o código do produto (ASIN) não
        res = {chave_produto(r["link"], r["loja"]): r["preco"] for r in con.execute(
            "SELECT link, loja, preco FROM precos WHERE normalizar(termo) = normalizar(?) AND busca_id = ?", (termo, ids[1]))}
    con.close()
    return res


def total_de_buscas(arq=None):
    con = conectar(arq)
    n = con.execute("SELECT COUNT(*) FROM buscas").fetchone()[0]
    con.close()
    return n
