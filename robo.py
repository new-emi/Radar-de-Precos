# robo.py — a BUSCA do Radar de Preços (rode: python robo.py)
#
# Este arquivo é só o "maestro": ele chama as peças que ficam no pacote radar/ na ordem certa.
#   1. lê a lista de compras (lista.txt) e a lista fixa do estudo da Black Friday (lista_estudo.txt)
#   2. busca cada item nas lojas: VTEX em paralelo (radar/lojas/vtex.py) e Magalu/Amazon
#      pelo Chrome do robô (radar/lojas/magalu.py, amazon.py)
#   3. a IA escolhe as melhores ofertas e tira o que não é o produto pedido (radar/ia.py)
#   4. salva o resultado do dia (dados_black_friday.json) e o histórico (historico.db)
#
# As linhas com ETAPA_ML, PAUSA_VERIFICACAO e [1/37] são lidas pelo painel para mostrar o progresso.
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from playwright.sync_api import sync_playwright

from radar import banco, navegador
from radar.config import ARQ_DADOS, ARQ_LISTA, ler_lista_estudo
from radar.ia import analisar_com_ia, criar_cliente_ia
from radar.lojas import LOJAS_VTEX, amazon, lojas_ativas, magalu, mercado_livre, ml_api, vtex


def main():
    if not ARQ_LISTA.exists():
        print("Erro: arquivo 'lista.txt' não encontrado.")
        return 1
    itens = [l.strip() for l in ARQ_LISTA.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Lista do estudo da Black Friday: buscada junto, mas só vai para o histórico (não para o painel)
    da_familia = {banco.normalizar(t) for t in itens}
    estudo = [t for t in ler_lista_estudo() if banco.normalizar(t) not in da_familia]
    todos = itens + estudo
    client = criar_cliente_ia()

    print("\n🤖 Iniciando varredura...\n")
    if estudo:
        print(f"📊 Lista do estudo: +{len(estudo)} itens (só para o histórico da Black Friday)\n")
    banco.importar_json_se_vazio(ARQ_DADOS)   # 1ª vez: a última busca do JSON vira o 1º dia do histórico
    navegador.abrir_chrome()
    pw, browser, page = None, None, None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://localhost:{navegador.PORTA_CHROME}")
        page = browser.contexts[0].new_page()
        print("✅ Chrome Robô conectado!\n")
    except Exception:
        print("⚠️ Chrome Robô não detectado. Magalu/Amazon ignoradas (e ML só pela via rápida).\n")

    resultado_itens = {}
    ativas = lojas_ativas()
    ml_ligado = "Mercado Livre" in ativas
    status_lojas = {loja: 0 for loja in ativas}

    # Fase 1: Mercado Livre para todos os itens de uma vez, logo no começo.
    # Se o ML pedir verificação, ela aparece no primeiro minuto (não espalhada pela busca inteira).
    ml = {}
    if ml_ligado:
        print("🔎 ETAPA_ML: Mercado Livre primeiro...")
    usar_api = ml_ligado and ml_api.configurado() and ml_api.obter_token() is not None
    if usar_api:
        print("   Mercado Livre pela API oficial (sem captcha).")
    for termo in (itens if ml_ligado else []):
        res = ml_api.buscar(termo) if usar_api else []
        if usar_api and not res and not ml:
            # A API falhou logo no primeiro item: volta para o navegador no resto da busca
            print("   API do ML não trouxe resultados: usando o navegador.")
            usar_api = False
        ml[termo] = res if usar_api else mercado_livre.buscar(termo, page)
    print("🔎 ETAPA_LOJAS: agora as outras lojas.\n")

    # Fase 2: as outras lojas.
    # As buscas VTEX são só pedidos HTTP: disparamos TODAS de uma vez em threads ("futures")
    # e elas vão respondendo enquanto o Chrome (que só faz uma coisa por vez) cuida de Magalu e Amazon.
    pool = ThreadPoolExecutor(max_workers=8)
    futuros_vtex = {(termo, nome): pool.submit(vtex.buscar, nome, url, termo)
                    for termo in todos for nome, url in LOJAS_VTEX.items()}
    futuros_ia = {}

    for i, termo in enumerate(todos, 1):
        print(f"[{i}/{len(todos)}] {termo}...")
        por_loja = {
            **({"Mercado Livre": ml.get(termo, [])} if ml_ligado else {}),
            "Magalu": magalu.buscar(page, termo) if page else [],
            "Amazon": amazon.buscar(page, termo) if page else [],
        }
        for nome in LOJAS_VTEX:   # .result() espera a thread terminar (quase sempre já terminou)
            por_loja[nome] = futuros_vtex[(termo, nome)].result()
        por_loja = {loja: por_loja[loja] for loja in ativas}   # mantém a ordem das lojas
        print("   " + " | ".join(f"{loja}: {len(r)}" for loja, r in por_loja.items()))

        vistos, unicos = set(), []
        for loja, res in por_loja.items():
            if banco.normalizar(termo) in da_familia:   # o painel mostra só a lista da família
                status_lojas[loja] += len(res)
            for r in res:
                chave = (r["titulo"], r["preco"], r["loja"])
                if chave not in vistos:
                    vistos.add(chave)
                    unicos.append(r)
        unicos.sort(key=lambda x: x["preco"])

        if not unicos:
            print("   -> Sem resultados.")
            continue
        resultado_itens[termo] = {"recomendacoes_ia": [], "produtos": unicos[:20]}
        # A IA também roda em paralelo: o robô já segue para o próximo item enquanto ela pensa
        futuros_ia[termo] = pool.submit(analisar_com_ia, client, termo, unicos)

    for termo, futuro in futuros_ia.items():
        resultado_itens[termo]["recomendacoes_ia"] = futuro.result()
    pool.shutdown()

    try:
        if page: page.close()
        if pw: pw.stop()   # não fecha o Chrome Robô, só desconecta
    except Exception:
        pass

    saida = {
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "lojas": status_lojas,
        # o arquivo do painel leva só a lista da família; o histórico (abaixo) guarda tudo
        "itens": {t: v for t, v in resultado_itens.items() if banco.normalizar(t) in da_familia},
    }
    ARQ_DADOS.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        banco.salvar_busca(resultado_itens)
        print(f"🗂️ Busca guardada no histórico ({banco.total_de_buscas()} buscas no total).")
    except Exception as e:
        print(f"⚠️ Não consegui guardar no histórico: {e}")
    print("\nResumo por loja:", ", ".join(f"{k}={v}" for k, v in status_lojas.items()))
    print("✅ Tudo pronto!")
    return 0



if __name__ == "__main__":
    sys.exit(main())
