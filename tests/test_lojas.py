# Testes do cadastro de lojas e das lojas VTEX (com respostas de mentira, sem internet)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import lojas
from radar.lojas import vtex


def test_ml_desligado_por_padrao(monkeypatch):
    monkeypatch.setattr(lojas, "ml_ativo", lambda: False)
    assert "Mercado Livre" not in lojas.lojas_ativas()
    assert lojas.lojas_ativas()[:len(lojas.LOJAS_VTEX)] == list(lojas.LOJAS_VTEX)


class _Resposta:
    status_code = 200

    def json(self):
        def produto(nome, preco, estoque):
            return {"productName": nome, "linkText": nome.lower().replace(" ", "-"),
                    "items": [{"sellers": [{"commertialOffer": {"Price": preco, "AvailableQuantity": estoque}}]}]}
        return {"products": [produto("Papel Toalha 2 rolos", 6.2, 10), produto("Esgotado 2 rolos", 3.0, 0),
                             produto("Sem preço", 0, 5)]}


def test_vtex_ignora_sem_estoque_e_sem_preco(monkeypatch):
    monkeypatch.setattr(vtex.requests, "get", lambda *a, **k: _Resposta())
    res = vtex.buscar("Muffato", "https://loja.exemplo", "papel toalha")
    assert [r["titulo"] for r in res] == ["Papel Toalha 2 rolos"]
    assert res[0]["link"] == "https://loja.exemplo/papel-toalha-2-rolos/p"


def test_lista_do_estudo_tem_dois_grupos_de_10():
    from collections import Counter
    from radar.config import ler_lista_estudo
    assert Counter(ler_lista_estudo().values()) == {"casa": 10, "black_friday": 10}


def test_vtex_tenta_de_novo_e_avisa_quando_nao_conecta(monkeypatch):
    """Caso real de 12/11: o PC acordando, sem internet, e as lojas VTEX voltavam [] em silêncio."""
    import pytest
    tentativas = []

    def cai_duas_vezes(*a, **k):
        tentativas.append(1)
        if len(tentativas) < 3:
            raise ConnectionError("sem internet")
        return _Resposta()
    monkeypatch.setattr(vtex.requests, "get", cai_duas_vezes)
    assert len(vtex.buscar("Muffato", "https://loja.exemplo", "papel toalha", esperas=(0, 0))) == 1
    assert len(tentativas) == 3                       # a 3ª tentativa deu certo

    def sempre_cai(*a, **k):
        raise ConnectionError("sem internet")
    monkeypatch.setattr(vtex.requests, "get", sempre_cai)
    with pytest.raises(vtex.FalhaDeConexao):           # falha não vira "a loja não tem"
        vtex.buscar("Muffato", "https://loja.exemplo", "papel toalha", esperas=(0, 0))


def test_esperar_internet(monkeypatch):
    from radar import sistema
    respostas = iter([False, False, True])
    assert sistema.esperar_internet(max_minutos=1, intervalo=0, testar=lambda: next(respostas))
    assert not sistema.esperar_internet(max_minutos=0, intervalo=0, testar=lambda: False)
