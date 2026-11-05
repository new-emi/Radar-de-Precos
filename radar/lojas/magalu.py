"""Magalu, via Chrome do robô (CDP)."""
from ..texto import preco_do_texto, titulo_do_texto, titulo_pela_url, titulo_ruim


def buscar(page, termo):
    """Busca na Magalu usando o Chrome do robô (o site bloqueia pedidos sem navegador)."""
    url = f"https://www.magazineluiza.com.br/busca/{termo.replace(' ', '+')}/"
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        try:   # espera o 1º produto aparecer (no máx. 15 s), em vez de sempre esperar um tempo fixo
            page.wait_for_selector('[data-testid="product-card-container"]', timeout=15000)
        except Exception:
            return []
        resultados = []
        for card in page.query_selector_all('[data-testid="product-card-container"]')[:5]:
            try:
                preco = preco_do_texto(card.inner_text())
                if preco is None:
                    continue
                link_el = card.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                link = href if href.startswith("http") else "https://www.magazineluiza.com.br" + href

                # Título: 1) campo de título  2) texto do card  3) alt da imagem  4) nome que vem na URL.
                # O da URL é o último recurso: perde acentos e vírgulas ("1,4kg" vira "14kg").
                titulo, aproximado = "", False
                titulo_el = card.query_selector('[data-testid="product-title"]') or card.query_selector("h2, h3")
                if titulo_el:
                    titulo = titulo_el.inner_text().strip()
                if titulo_ruim(titulo):
                    titulo = titulo_do_texto(card.inner_text())
                if titulo_ruim(titulo):
                    img = card.query_selector("img")
                    titulo = (img.get_attribute("alt") or "").strip() if img else ""
                if titulo_ruim(titulo):
                    titulo, aproximado = titulo_pela_url(link) or "Sem título", True

                item = {"loja": "Magalu", "titulo": titulo, "preco": preco, "link": link}
                if aproximado:
                    item["titulo_aproximado"] = True   # painel e IA não confiam no preço por unidade
                resultados.append(item)
            except Exception:
                continue
        return resultados
    except Exception:
        return []

