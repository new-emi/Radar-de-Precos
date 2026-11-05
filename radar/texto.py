"""Funções para limpar e entender o texto que vem das lojas (títulos e preços)."""
import re
from urllib.parse import unquote, urlparse

TITULOS_GENERICOS = {"", "sem título", "imagem do produto", "full", "produto"}



def titulo_ruim(titulo):
    return (titulo or "").strip().lower() in TITULOS_GENERICOS



def titulo_pela_url(link):
    """Magalu coloca o nome do produto na URL: /amaciante-comfort-500ml/p/xxxx/"""
    try:
        partes = [p for p in urlparse(link).path.split("/") if p]
        slug = partes[0] if partes else ""
        if not slug or slug == "p":
            return ""
        return " ".join(slug.split("-")).capitalize()
    except Exception:
        return ""



RUIDO_CARD = re.compile(r"R\$|%|\bx de\b|juros|frete|full|patrocinado|vendido|à vista|a vista|cupom|"
                        r"entrega|oferta do dia|mais vendido|^\(?\d+([.,]\d+)?\)?$|^\d+([.,]\d)? ?\(", re.I)



def titulo_do_texto(texto):
    """Acha o nome do produto no texto do card: a linha mais longa que não é preço, frete, nota etc."""
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    candidatas = [l for l in linhas if len(l) >= 12 and not RUIDO_CARD.search(l)]
    return max(candidatas, key=len) if candidatas else ""



def preco_do_texto(texto):
    m = re.search(r"R\$\s*([\d\.]+,\d{2})", texto or "")
    return float(m.group(1).replace(".", "").replace(",", ".")) if m else None


ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


def chave_produto(link, loja=""):
    """Identidade estável do produto, mesmo que o link mude entre buscas.
    Amazon: o código ASIN (o link muda o rastreamento 'ref=...?dib=...' a cada busca).
    Demais lojas: endereço sem os parâmetros depois do '?'."""
    link = link or ""
    # Anúncio patrocinado: o link é /sspa/click?...&url=%2FProduto%2Fdp%2FB0CVXT2K1S...
    # O endereço do produto vem "escondido" e codificado (%2F = "/"). unquote() decodifica,
    # e aí o ASIN aparece. Sem isso, todos os patrocinados viravam o mesmo produto.
    m = ASIN.search(unquote(link))
    if m:
        return f"amazon:{m.group(1)}"
    u = urlparse(link)
    return f"{u.netloc.lower()}{u.path.rstrip('/')}" or f"{loja}:{link}"
