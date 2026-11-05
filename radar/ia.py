"""A IA (DeepSeek): escolhe as melhores ofertas de cada item e tira o que não é o produto pedido."""
import json
import os
import time

from openai import OpenAI   # o DeepSeek usa o mesmo formato de API da OpenAI

from .config import carregar_env
from .unidades import item_pequeno, texto_preco_unidade


def criar_cliente_ia():
    carregar_env()
    chave = os.environ.get("DEEPSEEK_API_KEY")
    if not chave:
        print("⚠️ DEEPSEEK_API_KEY não encontrada no .env — a análise da IA será pulada.")
        return None
    return OpenAI(api_key=chave, base_url="https://api.deepseek.com")



# As instruções da IA ficam separadas do código para ficarem fáceis de ler e ajustar.
# Técnica: "prompt com regras + exemplos". Modelos de linguagem seguem muito melhor exemplos
# concretos do que ordens genéricas como "descarte o que não é o produto".
INSTRUCOES_SISTEMA = """Você ajuda uma família brasileira a comparar preços da lista de compras de casa.
Você é cuidadosa: na dúvida, MANTÉM o produto na comparação. Escrever "fora do pedido" sem certeza
esconde uma oferta boa da pessoa. Responde sempre em JSON válido."""


MODELO_PROMPT = """Item da lista de compras: "{termo}"

Ofertas encontradas nas lojas (o número entre colchetes é o id; entre parênteses, o preço por unidade
calculado a partir do título, quando dá):
{opcoes}
TAREFA 1 — "fora_do_pedido": marque SOMENTE os ids que com certeza NÃO servem para o item pedido.
Marque quando for:
  a) OUTRO TIPO DE PRODUTO. Ex.: pediu "protetor solar facial" e veio absorvente, sabonete facial ou
     sandália; pediu "barbeador eletrico" e veio repelente elétrico ou espuma de barbear; pediu
     "alcool etilico 70" e veio bebida alcoólica.
  b) OUTRA MARCA, quando o item cita uma marca. Ex.: pediu "sabonete dove" e veio Nivea.
  c) OUTRO FORMATO, quando o item cita o formato. Ex.: pediu "desodorante aerossol" e veio roll-on;
     pediu "sabonete liquido" e veio sabonete em barra.
NÃO marque (são o mesmo produto, só que outra versão):
  - outra fragrância, linha ou versão da mesma marca e tipo: Men, Feminino, Clinical, Cotton, Active,
    Powder, Invisible, Original, Sensitive...;
  - outro tamanho, kit, pack, refil ou "leve mais pague menos";
  - versões com algum benefício extra (72h, antibacteriano, sem álcool...).
NÃO suponha quem vai usar o produto (gênero, idade, tipo de pele) se o item não disser.

TAREFA 2 — "recomendacoes": entre os que NÃO marcou como fora, escolha as 2 melhores compras.
  - Compare pelo preço por unidade (R$/L, R$/100g, R$/10m, R$/un). Se faltar, compare tamanho e preço.
  - Prefira um tamanho que uma casa usa normalmente; um pacote enorme só vale se o preço por unidade
    for MUITO melhor.
  - No "motivo", escreva para uma pessoa leiga, numa frase curta, citando o preço por unidade.
    Ex.: "Sai a R$ 13,98 o litro, o mais barato entre os Comfort."

Responda APENAS com este JSON:
{{"recomendacoes": [{{"id": 0, "motivo": "..."}}, {{"id": 5, "motivo": "..."}}],
  "fora_do_pedido": [3, 7]}}"""



def analisar_com_ia(client, termo, produtos):
    """Manda os produtos numerados para a IA; ela devolve o número (id) dos 2 melhores."""
    if not client or not produtos:
        return []
    candidatos = produtos[:20]
    pequeno = item_pequeno([p["titulo"] for p in candidatos if not p.get("titulo_aproximado")])

    def linha(i, p):
        pu = "" if p.get("titulo_aproximado") else texto_preco_unidade(p["titulo"], p["preco"], pequeno)
        return f"[{i}] R$ {p['preco']:.2f}{f' ({pu})' if pu else ''} | {p['loja']} | {p['titulo']}\n"
    opcoes = "".join(linha(i, p) for i, p in enumerate(candidatos))
    prompt = MODELO_PROMPT.format(termo=termo, opcoes=opcoes)
    # Até 3 tentativas: às vezes a IA demora, cai a conexão ou vem um JSON com id inválido
    brutas = []
    for tentativa in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": INSTRUCOES_SISTEMA},
                          {"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=60,
            )
            for c in candidatos:
                c.pop("fora_do_pedido", None)   # limpa marcas de uma tentativa anterior
            resposta = json.loads(resp.choices[0].message.content)
            brutas = resposta.get("recomendacoes", [])
            for x in resposta.get("fora_do_pedido", []) or []:
                # marca no próprio produto: o painel esconde esses numa linha "não são o produto pedido"
                if str(x).strip().isdigit() and int(x) < len(candidatos):
                    candidatos[int(x)]["fora_do_pedido"] = True
            validas = [r for r in brutas if str(r.get("id", "")).strip().isdigit()
                       and int(r["id"]) < len(candidatos)]
            if validas:
                brutas = validas
                break
            print(f"   IA ({termo}): resposta sem recomendação válida (tentativa {tentativa}/3)")
        except Exception as e:
            print(f"   IA ({termo}): erro na tentativa {tentativa}/3: {e}")
        brutas = []
        time.sleep(2 * tentativa)   # espera um pouco mais a cada tentativa ("backoff")

    # Monta a recomendação a partir do produto REAL (nome, loja, preço e link nunca vêm "inventados" pela IA)
    recomendacoes = []
    for rec in brutas:
        try:
            p = candidatos[int(rec["id"])]
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        p.pop("fora_do_pedido", None)   # se a IA escolheu, não pode estar marcado como "fora"
        recomendacoes.append({
            "produto": p["titulo"], "loja": p["loja"],
            "preco": f"R$ {p['preco']:.2f}".replace(".", ","), "preco_num": p["preco"],
            "link": p["link"], "motivo": rec.get("motivo", ""),
        })
    return recomendacoes[:2]

