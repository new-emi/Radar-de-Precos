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
