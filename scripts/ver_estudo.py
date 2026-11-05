# ver_estudo.py — como está a coleta do estudo da Black Friday (só leitura, não muda nada)
#
# Uso (na pasta do projeto, com a venv ligada):
#     python scripts\ver_estudo.py
#
# Mostra, para cada item da lista fixa (lista_estudo.txt): em quantos dias já tem preço,
# o dia mais recente e o preço da melhor escolha nesse dia. Serve para conferir se a coleta
# está andando (ex.: o PC ficou desligado e faltou algum dia), não para tirar conclusões:
# as conclusões só saem em 01/12, com as regras do pré-registro.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para achar o pacote radar/ na raiz

from radar import analise, banco  # noqa: E402
from radar.config import ler_lista_estudo  # noqa: E402


def janela(dia):
    for nome, (ini, fim) in [("Base", analise.JANELA_BASE), ("Pré-BF", analise.JANELA_PRE), ("Black Friday", analise.JANELA_BF)]:
        if ini <= dia <= fim:
            return nome
    return "fora das janelas"


def main():
    estudo = ler_lista_estudo()            # {termo: grupo}
    if not estudo:
        print("Não achei a lista do estudo (lista_estudo.txt).")
        return
    for grupo in ("casa", "black_friday"):
        print(f"\n=== {analise.NOMES_GRUPO.get(grupo, grupo)} ===")
        print(f"{'item':<45} {'dias':>4}  {'último dia':<11} {'melhor escolha':>15}")
        for termo, g in estudo.items():
            if g != grupo:
                continue
            hist = banco.escolhas_por_dia(termo, dias=3650)
            if not hist:
                print(f"{termo:<45} {0:>4}  {'—':<11} {'ainda sem dados':>15}")
                continue
            ult = hist[-1]
            dia = f"{ult['dia'][8:10]}/{ult['dia'][5:7]}"
            preco = f"R$ {ult['preco']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            print(f"{termo:<45} {len(hist):>4}  {dia:<11} {preco:>15}")
    dias = sorted({e["dia"] for t in estudo for e in banco.escolhas_por_dia(t, dias=3650)})
    print(f"\nDias com coleta: {len(dias)}", end="")
    if dias:
        por_janela = {}
        for d in dias:
            por_janela[janela(d)] = por_janela.get(janela(d), 0) + 1
        print(" — " + ", ".join(f"{n}: {q}" for n, q in por_janela.items()))
        print(f"Mínimo do pré-registro: {analise.DIAS_MIN_BASE} dias na Base (05 a 15/11) e 1 dia na Black Friday (27 a 30/11).")
    else:
        print()


if __name__ == "__main__":
    main()
