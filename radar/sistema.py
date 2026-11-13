"""Cuidados com o computador durante a busca: não dormir no meio e esperar a internet voltar."""
import sys
import time
from contextlib import contextmanager

from curl_cffi import requests

# Constantes da API do Windows SetThreadExecutionState (valores da documentação da Microsoft)
ES_CONTINUOUS = 0x80000000        # o pedido vale até ser cancelado
ES_SYSTEM_REQUIRED = 0x00000001   # "o sistema está em uso": não entra em suspensão


@contextmanager
def manter_acordado():
    """Enquanto o bloco "with manter_acordado():" roda, o Windows não suspende o PC.

    É o mesmo pedido que um player de vídeo faz para a tela não apagar no meio do filme.
    Não liga o PC nem impede de desligar: só adia a suspensão por inatividade. Quando o
    bloco termina (mesmo com erro), o pedido é cancelado e o Windows volta ao normal.
    Em outro sistema (Linux, Mac) não faz nada."""
    windows = sys.platform == "win32"
    if windows:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        if windows:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def tem_internet(url="https://www.americanas.com.br"):
    try:
        requests.head(url, impersonate="chrome110", timeout=8)
        return True
    except Exception:
        return False


def esperar_internet(max_minutos=5, intervalo=15, testar=tem_internet):
    """Logo depois de o PC acordar, o Wi-Fi leva alguns segundos para reconectar.
    Espera a internet voltar (até max_minutos) antes de começar. Devolve True se voltou."""
    fim = time.monotonic() + max_minutos * 60
    avisou = False
    while True:
        if testar():
            if avisou:
                print("   Internet de volta.\n")
            return True
        if time.monotonic() >= fim:
            return False
        if not avisou:
            print("📶 Sem internet ainda. Esperando a conexão voltar...")
            avisou = True
        time.sleep(intervalo)
