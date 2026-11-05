# Testes do histórico (usa um banco temporário, não mexe no historico.db de verdade)
import sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import banco


def itens(preco_a, preco_b):
    return {"papel toalha": {
        "recomendacoes_ia": [{"link": "a"}],
        "produtos": [{"loja": "Atacadão", "titulo": "Papel Snob 2 rolos", "preco": preco_a, "link": "a"},
                     {"loja": "Amazon", "titulo": "Papel Scala 3x120fls", "preco": preco_b, "link": "b"}]}}


def test_historico_e_variacao(tmp_path):
    db = tmp_path / "t.db"
    hoje = datetime.now()
    banco.salvar_busca(itens(10.0, 12.0), hoje - timedelta(days=2), db)
    banco.salvar_busca(itens(8.0, 12.0), hoje - timedelta(days=1), db)
    banco.salvar_busca(itens(6.3, 11.0), hoje, db)

    hist = banco.historico_diario("papel toalha", arq=db)
    assert [m for _, m, _ in hist] == [10.0, 8.0, 6.3]
    assert hist[-1][2] == "Atacadão"
    # "Papel Snob 2 rolos" -> preço por rolo: média anterior R$ 4,50/un, hoje R$ 3,15/un -> caiu 30%
    assert banco.variacao("papel toalha", db) == {"pct": -30.0, "regua": "un"}
    assert banco.menor_ja_visto("papel toalha", db)[0] == 8.0          # menor ANTES de hoje (o painel só mostra se for < hoje)
    assert banco.precos_anteriores("papel toalha", db) == {"a": 8.0, "b": 12.0}
    assert banco.total_de_buscas(db) == 3


def test_sem_historico(tmp_path):
    db = tmp_path / "t.db"
    banco.salvar_busca(itens(10.0, 12.0), arq=db)
    assert banco.variacao("papel toalha", db) is None                 # só hoje: nada para comparar
    assert banco.precos_anteriores("papel toalha", db) == {}


def test_compara_melhor_escolha_e_nao_o_mais_barato(tmp_path):
    """Barbeador elétrico: o mais barato é um aparelho manual que a IA descartou. Não pode virar a régua."""
    db = tmp_path / "t.db"
    def busca(preco_eletrico):
        return {"barbeador eletrico": {
            "recomendacoes_ia": [{"link": "eletrico"}],
            "produtos": [{"loja": "Atacadão", "titulo": "Aparelho manual 7 un", "preco": 9.9, "link": "manual"},
                         {"loja": "Amazon", "titulo": "Barbeador Philips", "preco": preco_eletrico, "link": "eletrico"}]}}
    hoje = datetime.now()
    banco.salvar_busca(busca(140.0), hoje - timedelta(days=1), db)
    banco.salvar_busca(busca(129.0), hoje, db)
    # o título não diz quantidade, mas é o mesmo produto: compara o preço
    assert banco.variacao("barbeador eletrico", db) == {"pct": -7.9, "regua": "preco"}
    assert banco.menor_ja_visto("barbeador eletrico", db)[0] == 140.0  # o elétrico, nunca o manual de R$ 9,90


def test_formato_antigo_sem_link(tmp_path):
    db = tmp_path / "t.db"
    antigo = {"barbeador eletrico": {
        "recomendacoes_ia": [{"produto": "Barbeador Philips Série 3000", "loja": "Amazon", "preco": "R$ 129,00"}],
        "produtos": [{"loja": "Atacadão", "titulo": "Aparelho manual 7 un", "preco": 9.9, "link": "manual"},
                     {"loja": "Amazon", "titulo": "Barbeador Philips Série 3000", "preco": 129.0, "link": "eletrico"}]}}
    banco.salvar_busca(antigo, arq=db)
    assert banco.historico_diario("barbeador eletrico", arq=db)[0][1] == 129.0


def test_nome_com_acento_e_maiuscula_e_o_mesmo_item(tmp_path):
    db = tmp_path / "t.db"
    hoje = datetime.now()
    banco.salvar_busca({"oleo capilar elseve": itens(10.0, 12.0)["papel toalha"]}, hoje - timedelta(days=1), db)
    banco.salvar_busca({"Óleo  Capilar ELSEVE": itens(9.0, 12.0)["papel toalha"]}, hoje, db)
    assert [p for _, p, _ in banco.historico_diario("óleo capilar elseve", arq=db)] == [10.0, 9.0]
    assert banco.normalizar("Sabão  em Pó") == "sabao em po"


def test_embalagem_diferente_compara_por_unidade(tmp_path):
    """Caso real (04 -> 05/11): a melhor escolha mudou do pacote de 16 para o de 48.
    Pelo preço da compra seria "subiu 190%"; por unidade, ficou 5% mais barato."""
    db = tmp_path / "t.db"
    def busca(titulo, preco, link):
        return {"absorvente com abas": {"recomendacoes_ia": [{"link": link}],
                                        "produtos": [{"loja": "Amazon", "titulo": titulo, "preco": preco, "link": link}]}}
    hoje = datetime.now()
    banco.salvar_busca(busca("Absorvente Diana Suave com abas 16 un", 6.5, "a16"), hoje - timedelta(days=1), db)
    banco.salvar_busca(busca("Always Absorvente com Abas, 48 Unidades", 18.87, "a48"), hoje, db)
    assert banco.variacao("absorvente com abas", db) == {"pct": -3.2, "regua": "un"}
    assert banco.menor_ja_visto("absorvente com abas", db) is None    # produto diferente: nada a dizer


def test_produto_diferente_sem_quantidade_nao_compara(tmp_path):
    db = tmp_path / "t.db"
    def busca(titulo, preco, link):
        return {"lustra moveis": {"recomendacoes_ia": [{"link": link}],
                                  "produtos": [{"loja": "Amazon", "titulo": titulo, "preco": preco, "link": link}]}}
    hoje = datetime.now()
    banco.salvar_busca(busca("Kit Lustra Móveis Poliflor", 12.0, "x"), hoje - timedelta(days=1), db)
    banco.salvar_busca(busca("Lustra Móveis Lavanda 500ml", 24.0, "y"), hoje, db)
    assert banco.variacao("lustra moveis", db) is None


def test_titulo_da_url_da_magalu_nao_entra_por_unidade(tmp_path):
    """"Omo 1,4kg" lido pela URL vira "14kg" (R$ 0,14/100 g): não pode virar a régua."""
    link = "https://www.magazineluiza.com.br/sabao-em-po-omo-lavanda-14kg/p/abc/"
    assert banco.unidade_confiavel("Sabao em po omo lavanda 14kg", 19.2, "Magalu", link) == (None, None)
    assert banco.unidade_confiavel("Sabão em Pó Omo 1,4kg", 19.2, "Magalu", link)[1] == "100g"


def test_variacao_absurda_nao_aparece(tmp_path):
    """Mais de 60% de um dia para o outro é quase sempre erro de leitura do título."""
    db = tmp_path / "t.db"
    hoje = datetime.now()
    banco.salvar_busca(itens(4.0, 12.0), hoje - timedelta(days=1), db)
    banco.salvar_busca(itens(12.0, 12.0), hoje, db)
    assert banco.variacao("papel toalha", db) is None
