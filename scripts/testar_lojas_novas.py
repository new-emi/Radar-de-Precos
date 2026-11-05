# testar_lojas_novas.py — descobre se uma loja candidata responde à API VTEX
#
# Como funciona: lojas feitas na plataforma VTEX expõem o mesmo endereço de busca
#   <site>/api/io/_v/api/intelligent-search/product_search?query=...
# Se a loja responder com produtos E preços, ela entra no robô com UMA linha (LOJAS_VTEX em radar/lojas/__init__.py).
#
# Rode no terminal:   .venv\Scripts\python scripts/testar_lojas_novas.py
# (O resultado da primeira rodada, com 14 lojas, está anotado no BACKLOG.md.)
from curl_cffi import requests

CANDIDATAS = {
    # A IA antiga recebeu "SSLError" na Nissei: o curl_cffi traz os próprios certificados, então vale tentar de novo
    "Nissei":      "https://www.farmaciasnissei.com.br",
    "Nissei (2)":  "https://farmaciasnissei.com.br",
}
TERMOS = ["creme dental colgate 180g", "papel toalha", "barbeador eletrico"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}


def testar(base, termo):
    url = f"{base}/api/io/_v/api/intelligent-search/product_search"
    try:
        r = requests.get(url, params={"query": termo, "count": 5}, headers=HEADERS,
                         impersonate="chrome110", timeout=15)
    except Exception as e:
        return f"erro de conexão ({type(e).__name__}: {str(e)[:80]})", 0, None
    if r.status_code not in (200, 206):
        return f"HTTP {r.status_code}", 0, None
    try:
        produtos = r.json().get("products", [])
    except Exception:
        return f"respondeu, mas não é JSON (não é VTEX). Início: {r.text[:80]!r}", 0, None
    com_preco = []
    for p in produtos:
        try:
            oferta = p["items"][0]["sellers"][0]["commertialOffer"]
            if oferta.get("Price", 0) > 0:
                com_preco.append((oferta["Price"], p.get("productName"), oferta.get("AvailableQuantity")))
        except Exception:
            pass
    exemplo = min(com_preco) if com_preco else None
    return f"{len(produtos)} produtos, {len(com_preco)} com preço", len(com_preco), exemplo


print("\nTestando lojas candidatas...\n")
aprovadas = []
for nome, base in CANDIDATAS.items():
    total = 0
    for termo in TERMOS:
        status, n, ex = testar(base, termo)
        total += n
        extra = f"  -> ex.: R$ {ex[0]:.2f} {ex[1][:45]} (estoque: {ex[2]})" if ex else ""
        print(f"{nome:<14} | {termo:<26} | {status}{extra}")
    if total:
        aprovadas.append(nome)
    print()

print("=" * 70)
print("FUNCIONARAM:", ", ".join(aprovadas) if aprovadas else "nenhuma")
print("Copie tudo e mande para o Claude.")
