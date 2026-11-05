# Testes da IA (com uma IA de mentira) e da leitura de títulos — não precisam de internet
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import ia as modulo_ia
from radar import texto


def test_titulo_do_texto_card_magalu():
    card = """Patrocinado
Sabão em Pó Omo Lavagem Perfeita 1,4kg
4.8 (1.203)
R$ 22,90
R$ 19,20 no Pix
ou R$ 20,21 em 1x de R$ 20,21 sem juros
Full"""
    assert texto.titulo_do_texto(card) == "Sabão em Pó Omo Lavagem Perfeita 1,4kg"


class _IAFalsa:
    """Imita o cliente do DeepSeek devolvendo respostas prontas, uma por chamada."""
    def __init__(self, *respostas):
        self.respostas = iter(respostas)
        self.chat = self
        self.completions = self

    def create(self, **_):
        conteudo = next(self.respostas)
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": conteudo})})]})


def test_ia_marca_fora_do_pedido_e_tenta_de_novo(monkeypatch):
    monkeypatch.setattr(modulo_ia.time, "sleep", lambda s: None)
    produtos = [{"loja": "A", "titulo": "Absorvente 16 un", "preco": 6.5, "link": "a"},
                {"loja": "B", "titulo": "Protetor Solar FPS50 50ml", "preco": 26.99, "link": "b"}]
    ia = _IAFalsa("não é json",
                  json.dumps({"recomendacoes": [{"id": 1, "motivo": "ok"}], "fora_do_pedido": [0, 1]}))
    recs = modulo_ia.analisar_com_ia(ia, "protetor solar facial", produtos)
    assert recs[0]["link"] == "b"
    assert produtos[0].get("fora_do_pedido") is True
    assert "fora_do_pedido" not in produtos[1]     # o escolhido nunca fica marcado como fora
