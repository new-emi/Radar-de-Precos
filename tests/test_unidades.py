# Testes do preço por unidade. Rode com:  .venv\Scripts\python -m pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from radar.unidades import quantidade, texto_preco_unidade

CASOS = [
    ("Amaciante para Roupas Concentrado Comfort 500ml", (500, "ml")),
    ("Amaciante Concentrado Comfort Líquido Frescor Intenso 1,5L", (1500, "ml")),
    ("Comfort Amaciante Concentrado Frescor Intenso 1 L", (1000, "ml")),
    ("Creme Dental Colgate Máxima Proteção Anticáries 180g 3 un com Desconto", (540, "g")),
    ("Colgate Creme Dental Tripla Ação Menta, 180g, 1 Unidade", (180, "g")),
    ("Creme Dental Anti-Tártaro Colgate Total 12 180g", (180, "g")),
    ("Kit 3 Creme Dental Colgate 90g", (270, "g")),
    ("Creme Dental Colgate 2x180g", (360, "g")),
    ("Papel Toalha Scala Plus 3x120fls", (360, "folhas")),
    ("Toalha de Papel Snob 360 folhas 3 rolos", (360, "folhas")),
    ("Papel Toalha Scala Plus Multipicote, 2 Rolos", (2, "un")),
    ("Aparelho de Barbear Probak 7 un", (7, "un")),
    ("Toalha de Papel Shalon Interfolha Branco 1000 un", (1000, "folhas")),
    ("Kit Papel Toalha De Banheiro Para Mãos Folha Quadrupla 3 Pacotes 120 fls", (360, "folhas")),
    ("Philips Aparador e Barbeador Elétrico Série 3000 All-in-One 9 em 1", (None, None)),
    ("Imagem do produto", (None, None)),
    # rodada com a lista completa (04/11)
    ("Limpador Multiuso Veja Gold Original 500ml com 10% de Desconto", (500, "ml")),
    ("Saco para Lixo Embalixo Super econômico 50L 50un", (50, "un")),
    ("Saco para Lixo Embalixo Super econômico 15L 100un", (100, "un")),
    ("Utilix 50L Preto, Rolo com 30 Sacos para Lixo Dover-Roll", (30, "un")),
    ("Borrifador pet pulverizador spray 500ml nobre", (None, None)),
    ("Protetor diario intimus antibacteriana 80 unidades", (80, "un")),
    ("Fio Dental Limpeza Profunda Colgate Nylon 50m", (50, "m")),
    ("Papel Higiênico Folha Dupla Personal Vip Neutro 20m 12 Unidades", (240, "m")),
    ("Rolo papel manteiga bricoflex 30cm x 75m", (75, "m")),
    ("Folha de Alumínio Bulnez 0,30cm x 7,5m 1 rolo", (7.5, "m")),
    ("Guardanapo de Papel Coquetel 23cmx22cm 50 un", (50, "folhas")),
]


@pytest.mark.parametrize("titulo, esperado", CASOS)
def test_quantidade(titulo, esperado):
    assert quantidade(titulo) == esperado


def test_texto():
    assert texto_preco_unidade("Comfort 500ml", 7.59) == "R$ 15,18/L"
    assert texto_preco_unidade("Colgate 180g", 9.99) == "R$ 5,55/100g"
    assert texto_preco_unidade("Barbeador Série 3000", 129.0) == ""


def test_regua_por_item():
    from radar.unidades import item_pequeno
    protetores = ["Protetor Solar Facial FPS50 50ml", "Nivea Sun Facial 40ml", "Protetor 200ml"]
    amaciantes = ["Comfort 500ml", "Comfort 1,5L", "Comfort 5L"]
    assert item_pequeno(protetores) is True
    assert item_pequeno(amaciantes) is False
    assert texto_preco_unidade("Protetor Solar Facial FPS50 50ml", 26.99, pequeno=True) == "R$ 53,98/100ml"
