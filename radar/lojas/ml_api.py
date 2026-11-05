# ml_api.py — Mercado Livre pela API oficial (sem captcha)
#
# Por que este arquivo existe:
#   O site do ML pede captcha para robôs. A API oficial não, mas exige um token (OAuth).
#   O endpoint de busca "clássico" (/sites/MLB/search) está devolvendo 403 até COM token
#   para apps comuns. Por isso aqui usamos a BUSCA DE CATÁLOGO (/products/search) e depois
#   pegamos o preço de cada produto do catálogo.
#
# Como usar (no terminal, dentro da pasta do projeto):
#   .venv\Scripts\python -m radar.lojas.ml_api login        -> faz o login uma vez e guarda o token
#   .venv\Scripts\python -m radar.lojas.ml_api diagnostico  -> testa os endpoints e mostra o que o ML respondeu
#   .venv\Scripts\python -m radar.lojas.ml_api "papel toalha" -> busca de teste
#
# Precisa no .env:
#   ML_CLIENT_ID=...        (o "ID do aplicativo" no developers)
#   ML_CLIENT_SECRET=...    (a "Chave secreta")
#   ML_REDIRECT_URI=...     (EXATAMENTE a "URI de redirect" cadastrada no app, ex.: https://www.google.com)
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests as req   # requests "normal": a API não precisa do disfarce do curl_cffi

from ..config import PASTA, carregar_env

ARQ_TOKEN = PASTA / "ml_token.json"   # fica fora do Git (.gitignore)
API = "https://api.mercadolibre.com"
AUTH = "https://auth.mercadolivre.com.br/authorization"


# ------------------------------------------------------------------ config
def credenciais():
    carregar_env()
    cid, sec = os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")
    uri = os.environ.get("ML_REDIRECT_URI", "")
    return cid, sec, uri


def configurado():
    cid, sec, _ = credenciais()
    return bool(cid and sec)


# ------------------------------------------------------------------- token
def _salvar_token(dados):
    dados["expira_em"] = time.time() + int(dados.get("expires_in", 21600)) - 300  # 5 min de folga
    ARQ_TOKEN.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return dados


def _pedir_token(campos):
    r = req.post(f"{API}/oauth/token", data=campos, timeout=20,
                 headers={"accept": "application/json", "content-type": "application/x-www-form-urlencoded"})
    return r


def token_por_app():
    """Token só do aplicativo (client_credentials): não precisa de login. Nem todo app recebe."""
    cid, sec, _ = credenciais()
    r = _pedir_token({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec})
    if r.ok and "access_token" in r.json():
        return _salvar_token(r.json())
    return None


def renovar(dados):
    """O access_token dura 6h; o refresh_token troca por um novo sem precisar logar de novo."""
    if not dados.get("refresh_token"):
        return token_por_app()
    cid, sec, _ = credenciais()
    r = _pedir_token({"grant_type": "refresh_token", "client_id": cid, "client_secret": sec,
                      "refresh_token": dados["refresh_token"]})
    if r.ok and "access_token" in r.json():
        return _salvar_token(r.json())
    return None


def obter_token():
    """Devolve um access_token válido, renovando se precisar. None se não houver como."""
    if not configurado():
        return None
    if ARQ_TOKEN.exists():
        dados = json.loads(ARQ_TOKEN.read_text(encoding="utf-8"))
        if time.time() < dados.get("expira_em", 0):
            return dados["access_token"]
        novo = renovar(dados)
        if novo:
            return novo["access_token"]
    novo = token_por_app()
    return novo["access_token"] if novo else None


def login_interativo():
    """Fluxo 'authorization_code': você autoriza o app UMA vez no navegador; depois o refresh_token cuida."""
    cid, sec, uri = credenciais()
    if not (cid and sec and uri):
        print("Falta ML_CLIENT_ID, ML_CLIENT_SECRET ou ML_REDIRECT_URI no .env.")
        return False
    url = f"{AUTH}?{urlencode({'response_type': 'code', 'client_id': cid, 'redirect_uri': uri})}"
    print("\n1) Abra este link no navegador, faça login e clique em 'Permitir':\n")
    print("   " + url + "\n")
    print("2) O navegador vai para a sua URI de redirect com '?code=...' no endereço.")
    colado = input("3) Cole aqui o endereço INTEIRO (ou só o código): ").strip()
    code = parse_qs(urlparse(colado).query).get("code", [colado])[0]
    r = _pedir_token({"grant_type": "authorization_code", "client_id": cid, "client_secret": sec,
                      "code": code, "redirect_uri": uri})
    if r.ok and "access_token" in r.json():
        _salvar_token(r.json())
        print("\n✅ Login feito! Token salvo em ml_token.json (renova sozinho).")
        return True
    print(f"\n❌ O ML recusou ({r.status_code}): {r.text[:400]}")
    return False


# ------------------------------------------------------------------- busca
def _get(caminho, token, **params):
    return req.get(f"{API}{caminho}", params=params, timeout=20,
                   headers={"Authorization": f"Bearer {token}", "accept": "application/json"})


def preco_do_produto(prod_id, token):
    """Menor preço entre os anúncios ativos de um produto do catálogo (ou o 'buy box', se vier)."""
    r = _get(f"/products/{prod_id}/items", token)
    if r.ok:
        precos = [(i.get("price"), i.get("item_id")) for i in r.json().get("results", []) if i.get("price")]
        if precos:
            return min(precos)
    r = _get(f"/products/{prod_id}", token)
    if r.ok:
        bb = r.json().get("buy_box_winner") or {}
        if bb.get("price"):
            return bb["price"], bb.get("item_id")
    return None, None


def buscar(termo, limite=5):
    """Lista no mesmo formato das outras lojas: [{loja, titulo, preco, link}]. Vazia se não der."""
    token = obter_token()
    if not token:
        return []
    r = _get("/products/search", token, status="active", site_id="MLB", q=termo, limit=limite * 2)
    if not r.ok:
        print(f"   ⚠️ API do ML (catálogo) respondeu {r.status_code}: {r.text[:150]}")
        return []
    resultados = []
    for p in r.json().get("results", []):
        preco, item_id = preco_do_produto(p["id"], token)
        if not preco:
            continue
        link = (f"https://produto.mercadolivre.com.br/{item_id[:3]}-{item_id[3:]}" if item_id
                else f"https://www.mercadolivre.com.br/p/{p['id']}")
        resultados.append({"loja": "Mercado Livre", "titulo": p.get("name", "Sem título"),
                           "preco": float(preco), "link": link})
        if len(resultados) >= limite:
            break
    return resultados


# ------------------------------------------------------------- diagnóstico
def diagnostico(termo="papel toalha"):
    print("\n=== Diagnóstico da API do Mercado Livre ===\n")
    cid, sec, uri = credenciais()
    print(f"ML_CLIENT_ID:     {'ok' if cid else 'FALTANDO'}")
    print(f"ML_CLIENT_SECRET: {'ok' if sec else 'FALTANDO'}")
    print(f"ML_REDIRECT_URI:  {uri or '(vazio: necessário só para o login)'}")
    if not (cid and sec):
        return

    r = _pedir_token({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec})
    print(f"\n[1] Token só do app (client_credentials): {r.status_code} {r.text[:200]}")

    token = obter_token()
    if not token:
        print("\nSem token. Rode:  .venv\\Scripts\\python -m radar.lojas.ml_api login")
        return
    print("\nToken: ok")

    testes = [
        ("[2] Busca clássica /sites/MLB/search", "/sites/MLB/search", {"q": termo, "limit": 2}),
        ("[3] Busca de catálogo /products/search", "/products/search", {"status": "active", "site_id": "MLB", "q": termo, "limit": 2}),
    ]
    prod_id = None
    for nome, caminho, params in testes:
        r = _get(caminho, token, **params)
        print(f"\n{nome}: {r.status_code}\n    {r.text[:300]}")
        if caminho == "/products/search" and r.ok and r.json().get("results"):
            prod_id = r.json()["results"][0]["id"]
    if prod_id:
        r = _get(f"/products/{prod_id}/items", token)
        print(f"\n[4] Preços do produto {prod_id} (/products/{{id}}/items): {r.status_code}\n    {r.text[:300]}")
        print(f"\n[5] Busca completa de teste:\n    {buscar(termo, 3)}")
    print("\n=== Fim. Copie tudo acima e mande para o Claude. ===")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "diagnostico"
    if arg == "login":
        login_interativo()
    elif arg == "diagnostico":
        diagnostico()
    else:
        for x in buscar(arg):
            print(f"R$ {x['preco']:>8.2f} | {x['titulo']} | {x['link']}")
