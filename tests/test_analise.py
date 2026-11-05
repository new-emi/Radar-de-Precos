# Testes da análise da Black Friday: cada classe do pré-registro com um caso feito à mão
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import analise, banco

BASE = ["2026-11-05", "2026-11-08", "2026-11-12"]
PRE = ["2026-11-18", "2026-11-24"]
BF = ["2026-11-27"]


def serie(base, pre, bf):
    return {**dict(zip(BASE, base)), **dict(zip(PRE, pre)), **dict(zip(BF, bf))}


def test_desconto_real():
    r = analise.classificar(serie([10, 10, 10], [10, 10], [8.9]))
    assert r["classe"] == analise.DESCONTO_REAL and round(r["variacao"], 2) == -0.11


def test_maquiagem_subiu_e_voltou():
    # 10 -> sobe para 13 antes -> "cai" para 10,20 na Black Friday: parece desconto, mas é o preço de antes
    assert analise.classificar(serie([10, 10, 10], [12, 13], [10.2]))["classe"] == analise.MAQUIAGEM


def test_maquiagem_mesmo_ainda_mais_caro():
    # subiu para 14 e "caiu" para 12: anúncio de desconto, mas 20% acima do normal
    assert analise.classificar(serie([10, 10, 10], [14, 14], [12]))["classe"] == analise.MAQUIAGEM


def test_ficou_mais_caro_sem_cair():
    assert analise.classificar(serie([10, 10, 10], [10, 10], [11]))["classe"] == analise.MAIS_CARO


def test_sem_mudanca():
    assert analise.classificar(serie([10, 10.2, 9.9], [10, 10.1], [9.8]))["classe"] == analise.SEM_MUDANCA


def test_mediana_ignora_dia_atipico():
    # um dia com erro de leitura (R$ 1,00) não derruba a referência
    r = analise.classificar(serie([10, 1, 10], [10, 10], [9]))
    assert r["p_base"] == 10 and r["classe"] == analise.DESCONTO_REAL


def test_dados_insuficientes():
    assert analise.classificar({"2026-11-05": 10, "2026-11-27": 8})["classe"] == analise.INSUFICIENTE


def test_chave_estavel_amazon_e_outras_lojas():
    a1 = "https://www.amazon.com.br/Comfort-Amaciante/dp/B07DTLS9M7/ref=sr_1_2?dib=AAA&keywords=x"
    a2 = "https://www.amazon.com.br/Comfort-Amaciante/dp/B07DTLS9M7/ref=sr_1_3?dib=BBB"
    assert analise.chave_produto(a1) == analise.chave_produto(a2) == "amazon:B07DTLS9M7"
    m1 = "https://www.magazineluiza.com.br/produto/p/abc123/?seller_id=loja1"
    m2 = "https://www.magazineluiza.com.br/produto/p/abc123/?seller_id=loja1&utm=zz"
    assert analise.chave_produto(m1) == analise.chave_produto(m2)


def test_chave_de_anuncio_patrocinado_da_amazon():
    """Caso real: 213 de 531 ofertas da Amazon vinham por /sspa/click, com o produto escondido no link."""
    pantene = ("https://www.amazon.com.br/sspa/click?ie=UTF8&spc=MTo0&url=%2FPantene-Miracles%2Fdp%2FB0CVXT2K1S"
               "%2Fref%3Dsr_1_1_sspa%3Fdib%3DeyJ2")
    outro = "https://www.amazon.com.br/sspa/click?ie=UTF8&spc=XYZ&url=%2FElseve%2Fdp%2FB07DTLS9M7%2Fref%3Dsr_1_2_sspa"
    assert analise.chave_produto(pantene) == "amazon:B0CVXT2K1S"
    assert analise.chave_produto(outro) == "amazon:B07DTLS9M7"


def test_ponta_a_ponta_com_banco(tmp_path):
    db = tmp_path / "t.db"
    precos = {"2026-11-05": 20.0, "2026-11-09": 20.0, "2026-11-13": 20.0, "2026-11-20": 26.0, "2026-11-27": 20.5}
    for dia, preco in precos.items():
        link = f"https://www.amazon.com.br/x/dp/B000000001/ref=sr_{dia}"     # link muda todo dia
        banco.salvar_busca({"amaciante": {"recomendacoes_ia": [{"link": link}],
                                          "produtos": [{"loja": "Amazon", "titulo": "Comfort 1L", "preco": preco, "link": link}]}},
                           datetime.fromisoformat(dia + " 11:00:00"), db)
    res = analise.analisar_produtos(db)
    assert len(res["produtos"]) == 1                       # o mesmo produto, apesar de 5 links diferentes
    assert res["produtos"][0]["classe"] == analise.MAQUIAGEM
    lista = analise.analisar_lista(db)
    assert lista["total_base"] == 20.0 and lista["total_bf"] == 20.5


def test_produtos_separados_por_grupo(tmp_path):
    db = tmp_path / "t.db"
    dias = ["2026-11-05", "2026-11-09", "2026-11-13", "2026-11-20", "2026-11-27"]
    for i, dia in enumerate(dias):
        itens = {}
        for termo, base, pre, bf in [("air fryer mondial 4l", 300, 360, 310), ("Café Pilão 500g", 20, 20, 20)]:
            preco = base if i < 3 else pre if i == 3 else bf
            link = f"https://loja.exemplo/{termo.replace(' ', '-')}/p"
            itens[termo] = {"recomendacoes_ia": [{"link": link}],
                            "produtos": [{"loja": "Magalu", "titulo": termo, "preco": preco, "link": link}]}
        banco.salvar_busca(itens, datetime.fromisoformat(dia + " 11:00:00"), db)
    grupos = {"air fryer mondial 4l": "black_friday", "cafe pilao 500g": "casa"}   # nomes já normalizados
    res = analise.analisar_produtos(db, grupos)
    assert res["por_grupo"]["black_friday"] == {analise.MAQUIAGEM: 1}
    assert res["por_grupo"]["casa"] == {analise.SEM_MUDANCA: 1}
