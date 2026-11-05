"""O Chrome do robô: um Chrome normal aberto com a porta de depuração 9222.

O Playwright "se conecta" nele (CDP = Chrome DevTools Protocol) e controla abas como uma pessoa,
com cookies e histórico de verdade. É isso que passa pelos anti-bots da Magalu e da Amazon.
"""
import os
import socket
import subprocess
import time

PORTA_CHROME = 9222

PERFIL_CHROME = r"C:\ChromePerfilTeste"



def chrome_aberto():
    try:
        with socket.create_connection(("127.0.0.1", PORTA_CHROME), timeout=0.5):
            return True
    except OSError:
        return False



def abrir_chrome():
    """Abre o Chrome do robô (porta 9222) se estiver fechado. Necessário na busca agendada."""
    if chrome_aberto():
        return True
    caminhos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    exe = next((c for c in caminhos if os.path.exists(c)), None)
    if not exe:
        return False
    subprocess.Popen([exe, f"--remote-debugging-port={PORTA_CHROME}", f"--user-data-dir={PERFIL_CHROME}"])
    for _ in range(30):
        if chrome_aberto():
            time.sleep(2)   # dá um respiro para o Chrome terminar de abrir
            return True
        time.sleep(0.5)
    return False

