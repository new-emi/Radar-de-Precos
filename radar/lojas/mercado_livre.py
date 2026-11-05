"""Mercado Livre pelo SITE (desligado por padrão: o ML pede captcha para robôs).

Quando pede verificação, o robô NÃO tenta resolver sozinho: pausa e espera uma pessoa resolver.
A API oficial está em ml_api.py (bloqueada pelo ML para apps comuns; ver README).
"""
import time

from bs4 import BeautifulSoup
from curl_cffi import requests

from .. import config


def extrair_cards_ml(html, url_busca):
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("li.ui-search-layout__item") or soup.select("div.poly-card")
    resultados = []
    for card in cards[:5]:
        try:
            titulo_el = card.select_one(".poly-component__title") or card.select_one("h2") or card.select_one("h3")
            titulo = titulo_el.get_text(strip=True) if titulo_el else "Sem título"
            inteiro = card.select_one(".andes-money-amount__fraction")
            if not inteiro:
                continue
            centavos = card.select_one(".andes-money-amount__cents")
            preco = float(f"{inteiro.text.replace('.', '')}.{centavos.text if centavos else '00'}")
            link_el = card.select_one("a.poly-component__title") or card.select_one("a")
            link = link_el["href"] if link_el and link_el.has_attr("href") else url_busca
            resultados.append({"loja": "Mercado Livre", "titulo": titulo, "preco": preco, "link": link})
        except Exception:
            continue
    return resultados


def ml_bloqueado(html):
    h = html.lower()
    return "complete esta etapa" in h or "<title>segurança" in h or "account-verification" in h


SELETOR_CARDS_ML = "li.ui-search-layout__item, div.poly-card"


ESPERA_VERIFICACAO = 120      # segundos que o robô espera a pessoa resolver a verificação


PAUSA_ENTRE_BUSCAS_ML = 4     # segundos entre uma busca e outra no ML (para não sobrecarregar o site)


ESTADO_ML = {"ultima": 0.0, "desistiu": False}


def conteudo_seguro(page, tentativas=4):
    """page.content() falha se a página estiver no meio de um redirecionamento: espera e tenta de novo."""
    for _ in range(tentativas):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            return page.content()
        except Exception:
            page.wait_for_timeout(1500)
    return ""


def em_verificacao(page, html):
    return "/captcha" in page.url or ml_bloqueado(html)


def esperar_pessoa_resolver(page):
    """Traz a aba para a frente e espera um humano resolver a verificação.
    O robô NÃO resolve captcha sozinho: só pausa e continua quando a pessoa terminar."""
    try:
        page.bring_to_front()
    except Exception:
        pass
    print(f"   ⏸️ PAUSA_VERIFICACAO: o Mercado Livre quer confirmar que é uma pessoa. "
          f"Resolva na janela do navegador (espero até {ESPERA_VERIFICACAO}s).")
    limite = time.time() + ESPERA_VERIFICACAO
    while time.time() < limite:
        page.wait_for_timeout(2000)
        if not em_verificacao(page, conteudo_seguro(page, 1)):
            print("   ▶️ VERIFICACAO_OK: obrigado! Continuando.")
            return True
    return False


def buscar(termo, page=None):
    url = f"https://lista.mercadolivre.com.br/{termo.replace(' ', '-')}"

    # Sem navegador: só a via rápida (costuma cair no captcha, mas não custa tentar)
    if page is None:
        try:
            r = requests.get(url, impersonate="chrome110", timeout=15)
            if r.status_code == 200 and not ml_bloqueado(r.text):
                return extrair_cards_ml(r.text, url)
        except Exception:
            pass
        return []

    # Com navegador: vai direto pelo Chrome. (Antes o robô tentava primeiro sem navegador;
    # essa visita extra, sem cookies, só aumentava a desconfiança do ML.)
    if ESTADO_ML["desistiu"]:
        return []
    espera = PAUSA_ENTRE_BUSCAS_ML - (time.time() - ESTADO_ML["ultima"])
    if espera > 0:
        time.sleep(espera)
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        ESTADO_ML["ultima"] = time.time()
        html = conteudo_seguro(page)
        if em_verificacao(page, html):
            if not esperar_pessoa_resolver(page):
                ESTADO_ML["desistiu"] = True
                print("   ⏭️ Ninguém resolveu a verificação: pulando o Mercado Livre no resto desta busca.")
                return []
            if "lista.mercadolivre" not in page.url:   # o ML às vezes não volta sozinho para a busca
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector(SELETOR_CARDS_ML, timeout=10000)  # espera os produtos aparecerem
        except Exception:
            pass
        html = conteudo_seguro(page)
        # Primeiro tenta extrair: se achou produto, ótimo, independente de qualquer texto na página
        res = extrair_cards_ml(html, url)
        if res:
            return res
        # Não achou nada: guarda o que o robô viu, para a gente descobrir o motivo
        try:
            (config.PASTA / "debug_ml.html").write_text(html, encoding="utf-8")
            page.screenshot(path=str(config.PASTA / "debug_ml.png"), full_page=False)
        except Exception:
            pass
        motivo = "pediu verificação (captcha)" if ml_bloqueado(html) else "abriu, mas não achei os produtos"
        print(f"   ⚠️ Mercado Livre {motivo}. Página salva em debug_ml.png / debug_ml.html  | URL final: {page.url}")
        return []
    except Exception as e:
        print(f"   ⚠️ Mercado Livre deu erro no Chrome: {e}")
        return []

