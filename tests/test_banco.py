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
    assert banco.variacao("papel toalha", 6.3, db) == -30.0          # média anterior 9,00 -> caiu 30%
    assert banco.menor_ja_visto("papel toalha", db)[0] == 6.3
    assert banco.precos_anteriores("papel toalha", db) == {"a": 8.0, "b": 12.0}
    assert banco.total_de_buscas(db) == 3


def test_sem_historico(tmp_path):
    db = tmp_path / "t.db"
    banco.salvar_busca(itens(10.0, 12.0), arq=db)
    assert banco.variacao("papel toalha", 10.0, db) is None           # só hoje: nada para comparar
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
    assert banco.variacao("barbeador eletrico", 129.0, db) == -7.9
    assert banco.menor_ja_visto("barbeador eletrico", db)[0] == 129.0


def test_formato_antigo_sem_link(tmp_path):
    db = tmp_path / "t.db"
    antigo = {"barbeador eletrico": {
        "recomendacoes_ia": [{"produto": "Barbeador Philips Série 3000", "loja": "Amazon", "preco": "R$ 129,00"}],
        "produtos": [{"loja": "Atacadão", "titulo": "Aparelho manual 7 un", "preco": 9.9, "link": "manual"},
                     {"loja": "Amazon", "titulo": "Barbeador Philips Série 3000", "preco": 129.0, "link": "eletrico"}]}}
    banco.salvar_busca(antigo, arq=db)
    assert banco.historico_diario("barbeador eletrico", arq=db)[0][1] == 129.0
