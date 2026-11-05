"""Amazon, via Chrome do robô (CDP)."""
from ..texto import preco_do_texto


def buscar(page, termo):
    """Busca na Amazon usando o Chrome do robô."""
    url = f"https://www.amazon.com.br/s?k={termo.replace(' ', '+')}"
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=15000)
        except Exception:
            return []
        resultados = []
        for card in page.query_selector_all('div[data-component-type="s-search-result"]')[:5]:
            try:
                preco = preco_do_texto(card.inner_text())
                if preco is None:
                    continue
                titulo_el = card.query_selector("h2")
                titulo = titulo_el.inner_text().strip() if titulo_el else "Sem título"
                link_el = card.query_selector("a.a-link-normal")
                href = link_el.get_attribute("href") if link_el else ""
                link = href if href.startswith("http") else "https://www.amazon.com.br" + href
                resultados.append({"loja": "Amazon", "titulo": titulo, "preco": preco, "link": link})
            except Exception:
                continue
        return resultados
    except Exception:
        return []

