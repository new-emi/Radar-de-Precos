"""Lojas feitas na plataforma VTEX: todas expõem a mesma API JSON de busca, sem navegador."""
from curl_cffi import requests   # imita a "assinatura" de um Chrome de verdade (TLS)

HEADERS_VTEX = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}



def buscar(nome_loja, base_url, termo):
    """Busca na API de busca da plataforma VTEX (Americanas, Atacadão, Muffato...)."""
    url = f"{base_url}/api/io/_v/api/intelligent-search/product_search"
    try:
        r = requests.get(url, params={"query": termo, "count": 5}, headers=HEADERS_VTEX,
                         impersonate="chrome110", timeout=10)
        if r.status_code not in (200, 206):
            return []
        resultados = []
        for p in r.json().get("products", []):
            try:
                oferta = p["items"][0]["sellers"][0]["commertialOffer"]
                preco = oferta.get("Price", 0)
                if preco > 0 and oferta.get("AvailableQuantity", 1) > 0:   # ignora sem estoque
                    resultados.append({"loja": nome_loja, "titulo": p.get("productName"), "preco": preco,
                                       "link": f"{base_url}/{p.get('linkText', '')}/p"})
            except Exception:
                continue
        return resultados
    except Exception:
        return []

