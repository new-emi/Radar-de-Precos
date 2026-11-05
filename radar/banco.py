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
from datetime import datetime, timedelta
from pathlib import Path

from .unidades import preco_por_unidade

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


def conectar(arq=None):
    con = sqlite3.connect(arq or ARQ_BANCO)
    con.row_factory = sqlite3.Row          # permite ler colunas pelo nome: linha["preco"]
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
                pu, un = preco_por_unidade(p.get("titulo"), p["preco"])
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
def historico_diario(termo, dias=30, arq=None):
    """[(dia, preço, loja)] — o preço da MELHOR ESCOLHA da IA em cada dia.
    Se num dia a IA não escolheu nada, usa o menor preço daquele dia.
    (Comparar o menor preço de QUALQUER produto engana: no 'barbeador elétrico', o mais barato
    costuma ser um aparelho manual que a IA descartou.)"""
    con = conectar(arq)
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    linhas = con.execute("""
        SELECT substr(b.data, 1, 10) AS dia,
               COALESCE(MIN(CASE WHEN p.escolhido_ia = 1 THEN p.preco END), MIN(p.preco)) AS menor
        FROM precos p JOIN buscas b ON b.id = p.busca_id
        WHERE p.termo = ? AND b.data >= ?
        GROUP BY dia ORDER BY dia
    """, (termo, desde)).fetchall()
    res = []
    for l in linhas:   # qual loja tinha o menor preço naquele dia
        loja = con.execute("""
            SELECT p.loja FROM precos p JOIN buscas b ON b.id = p.busca_id
            WHERE p.termo = ? AND substr(b.data, 1, 10) = ? AND p.preco = ? LIMIT 1
        """, (termo, l["dia"], l["menor"])).fetchone()
        res.append((l["dia"], l["menor"], loja["loja"] if loja else ""))
    con.close()
    return res


def variacao(termo, preco_hoje, arq=None):
    """Compara o menor preço de hoje com a MÉDIA dos menores preços dos dias anteriores (até 14 dias).
    Devolve a variação em % (ex.: -12.5 = caiu 12,5%) ou None se ainda não há dias anteriores."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    anteriores = [m for dia, m, _ in historico_diario(termo, 14, arq) if dia < hoje]
    if not anteriores or not preco_hoje:
        return None
    media = sum(anteriores) / len(anteriores)
    return round((preco_hoje - media) / media * 100, 1)


def menor_ja_visto(termo, arq=None):
    """(preço, dia, loja) do menor preço da melhor escolha já registrado (mesma régua do histórico)."""
    hist = historico_diario(termo, dias=3650, arq=arq)
    if not hist:
        return None
    dia, preco, loja = min(hist, key=lambda h: (h[1], h[0]))
    return preco, dia, loja


def precos_anteriores(termo, arq=None):
    """{link: preço} da busca ANTERIOR à última (para mostrar 'caiu R$ 1,20' em cada oferta)."""
    con = conectar(arq)
    ids = [r["busca_id"] for r in con.execute("""
        SELECT DISTINCT busca_id FROM precos WHERE termo = ? ORDER BY busca_id DESC LIMIT 2
    """, (termo,))]
    res = {}
    if len(ids) == 2:
        res = {r["link"]: r["preco"] for r in con.execute(
            "SELECT link, preco FROM precos WHERE termo = ? AND busca_id = ?", (termo, ids[1]))}
    con.close()
    return res


def total_de_buscas(arq=None):
    con = conectar(arq)
    n = con.execute("SELECT COUNT(*) FROM buscas").fetchone()[0]
    con.close()
    return n
