"""Lojas feitas na plataforma VTEX: todas expõem a mesma API JSON de busca, sem navegador."""
import time

from curl_cffi import requests   # imita a "assinatura" de um Chrome de verdade (TLS)

ESPERAS = (5, 20)   # segundos de espera antes da 2ª e da 3ª tentativa


class FalhaDeConexao(Exception):
    """A loja não respondeu (sem internet, PC acordando, loja fora do ar).
    É diferente de "a loja não tem esse produto": quem chamou precisa saber a diferença."""

HEADERS_VTEX = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}



def buscar(nome_loja, base_url, termo, esperas=ESPERAS):
    """Busca na API de busca da plataforma VTEX (Americanas, Atacadão, Muffato...).

    Se a conexão falhar, tenta de novo até 3 vezes, esperando um pouco mais a cada vez
    ("backoff"). Se as 3 falharem, levanta FalhaDeConexao em vez de devolver [] calado:
    lista vazia quer dizer "a loja não tem", e falha quer dizer "não deu para perguntar"."""
    url = f"{base_url}/api/io/_v/api/intelligent-search/product_search"
    for tentativa in range(len(esperas) + 1):
        try:
            r = requests.get(url, params={"query": termo, "count": 5}, headers=HEADERS_VTEX,
                             impersonate="chrome110", timeout=10)
            if r.status_code >= 500:
                raise FalhaDeConexao(f"{nome_loja} respondeu {r.status_code}")
            break
        except Exception as e:
            if tentativa == len(esperas):
                raise FalhaDeConexao(f"{nome_loja}: {e}") from e
            time.sleep(esperas[tentativa])
    if r.status_code not in (200, 206):
        return []
    resultados = []
    try:
        produtos = r.json().get("products", [])
    except Exception:
        return []
    for p in produtos:
        try:
            oferta = p["items"][0]["sellers"][0]["commertialOffer"]
            preco = oferta.get("Price", 0)
            if preco > 0 and oferta.get("AvailableQuantity", 1) > 0:   # ignora sem estoque
                resultados.append({"loja": nome_loja, "titulo": p.get("productName"), "preco": preco,
                                   "link": f"{base_url}/{p.get('linkText', '')}/p"})
        except Exception:
            continue
    return resultados
