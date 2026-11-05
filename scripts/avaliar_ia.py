# avaliar_ia.py — testa as instruções da IA SEM refazer a busca nas lojas
#
# Pega os produtos que já estão no dados_black_friday.json, manda de novo para a IA com o prompt
# atual de radar/ia.py e mostra o que ela escolheu e o que ela tirou da comparação.
# Serve para ajustar o prompt rápido: rodar a busca inteira leva minutos; isto leva segundos.
#
# Uso:
#   .venv\Scripts\python scripts/avaliar_ia.py                       -> todos os itens
#   .venv\Scripts\python scripts/avaliar_ia.py "desodorante aerossol rexona" "protetor solar facial"
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para achar o pacote radar/ na raiz

from radar.config import ARQ_DADOS  # noqa: E402
from radar.ia import analisar_com_ia, criar_cliente_ia  # noqa: E402

dados = json.loads(ARQ_DADOS.read_text(encoding="utf-8"))
itens = dados.get("itens", dados)
escolhidos = sys.argv[1:] or list(itens)
client = criar_cliente_ia()
if client is None:
    sys.exit("Sem chave do DeepSeek no .env.")


def avaliar(termo):
    produtos = copy.deepcopy(itens[termo]["produtos"])
    for p in produtos:
        p.pop("fora_do_pedido", None)          # começa do zero, sem a marcação antiga
    recs = analisar_com_ia(client, termo, produtos)
    return termo, produtos, recs


with ThreadPoolExecutor(max_workers=6) as pool:
    resultados = list(pool.map(avaliar, [t for t in escolhidos if t in itens]))

for termo, produtos, recs in resultados:
    fora = [p for p in produtos if p.get("fora_do_pedido")]
    print(f"\n=== {termo} ===")
    for r in recs:
        print(f"  ESCOLHA  R$ {r['preco_num']:>7.2f} | {r['loja']:<10} | {r['produto'][:60]}")
        print(f"           motivo: {r['motivo']}")
    print(f"  Tirou da comparação ({len(fora)}):")
    for p in fora:
        print(f"    - {p['loja']:<10} | {p['titulo'][:70]}")
print("\n(Nada foi salvo: isto é só um teste.)")
