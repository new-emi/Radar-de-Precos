"""Cadastro das lojas.

Lojas VTEX usam todas a mesma API aberta: para adicionar uma, basta UMA linha em LOJAS_VTEX
(teste antes com scripts/testar_lojas_novas.py). A cor de cada loja no painel fica em painel.py.
"""
from ..config import ml_ativo

# Lojas VTEX: todas usam a mesma API aberta. Para adicionar uma loja nova, basta UMA linha aqui
# (teste antes com testar_lojas_novas.py). A cor da loja no painel fica em painel.py -> COR_LOJA.
LOJAS_VTEX = {
    "Americanas": "https://www.americanas.com.br",
    "Atacadão":   "https://www.atacadao.com.br",
    "Muffato":    "https://www.supermuffato.com.br",
}

LOJAS_NAVEGADOR = ["Magalu", "Amazon"]          # precisam do Chrome do robô (anti-bot)
LOJAS = ["Mercado Livre", *LOJAS_VTEX, *LOJAS_NAVEGADOR]


def lojas_ativas():
    """Lojas que entram na busca, na ordem em que aparecem no painel."""
    return [l for l in LOJAS if ml_ativo() or l != "Mercado Livre"]
