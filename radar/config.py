"""Caminhos do projeto e leitura do arquivo .env (configurações e segredos)."""
import os
from pathlib import Path

# Raiz do projeto (a pasta acima de radar/): é lá que ficam lista.txt, .env e os dados gerados
PASTA = Path(__file__).resolve().parent.parent
ARQ_LISTA = PASTA / "lista.txt"
ARQ_ESTUDO = PASTA / "lista_estudo.txt"          # lista fixa do estudo da Black Friday (vai para o Git)
ARQ_DADOS = PASTA / "dados_black_friday.json"
ARQ_BANCO = PASTA / "historico.db"
ARQ_ENV = PASTA / ".env"


def ler_env():
    """Lê o .env AGORA e devolve um dicionário {CHAVE: valor}.
    Como relê o arquivo a cada chamada, mudanças no .env valem na hora, sem reiniciar nada."""
    valores = {}
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def carregar_env():
    """Copia o .env para as variáveis de ambiente (sem sobrescrever as que já existem)."""
    for chave, valor in ler_env().items():
        os.environ.setdefault(chave, valor)


def ml_ativo():
    """O Mercado Livre fica desligado, a não ser que o .env tenha ML_ATIVO=1 (ele pede captcha)."""
    valor = ler_env().get("ML_ATIVO") or os.environ.get("ML_ATIVO", "0")
    return valor.strip().lower() in ("1", "sim", "true")


def ler_lista_estudo():
    """{termo: grupo} da lista do estudo. Linhas '# grupo: nome' abrem um grupo; outras '#' são comentário."""
    grupos, atual = {}, "sem_grupo"
    if ARQ_ESTUDO.exists():
        for linha in ARQ_ESTUDO.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha.lower().startswith("# grupo:"):
                atual = linha.split(":", 1)[1].strip()
            elif linha and not linha.startswith("#"):
                grupos[linha] = atual
    return grupos
