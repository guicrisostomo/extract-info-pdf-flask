import re
from typing import Dict, List
import logging

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_bebidas(texto: str) -> List[Dict]:
    bebidas = []
    linhas = [linha.strip() for linha in texto.splitlines()]
    linhas = [linha for linha in linhas if linha]  # Remove linhas vazias
    # remove linhas com apenas espaços ou string vazio
    linhas = [linha for linha in linhas if linha.strip()]
    
    # Padrão para identificar linhas de bebidas (quantidade + nome + preço opcional)
    padrao_linha_principal = re.compile(
        r'^(\d+)\s+'
        r'(REFRIGERANTE|SUCO|ÁGUA|AGUA|ENERGÉTICO|ENERGETICO|CERVEJA|ÁGUA\s+MINERAL|CERVEJA\s+ARTESANAL)'
        r'(\s+\d+,\d{2})?$',
        re.IGNORECASE
    )
    
    # obtem bebidas mesmo em que não estejam no padrão
    padrao_linha_bebida = re.compile(
        r'^(REFRIGERANTE|SUCO|ÁGUA|AGUA|ENERGÉTICO|ENERGETICO|CERVEJA|ÁGUA\s+MINERAL|CERVEJA\s+ARTESANAL)'
        r'(\s+\d+,\d{2})?$',
        re.IGNORECASE
    )
    # Padrão para identificar linhas de sabores
    padrao_linha_sabor = re.compile(
        r'^\s*(\d+/\d+)\s*-\s*([A-Z\s]+)\s*$',
        re.IGNORECASE
    )

    categorias = [
        "REFRIGERANTE", "SUCO", "ÁGUA", "AGUA", "ENERGÉTICO", "ENERGETICO",
        "CERVEJA", "ÁGUA MINERAL", "CERVEJA ARTESANAL"
    ]
    # padrão de texto que chegam:
    # O1I REFRIGERANTE
    # COCA-COLA ORIGINAL 2L

    for linha in linhas:
        linha = linha.strip()
        
        if padrao_linha_principal.match(linha):
            partes = padrao_linha_principal.findall(linha)[0]
            quantidade = partes[0].strip()
            descricao = partes[1].strip()
            preco = partes[2].strip() if partes[2] else None
            
            bebida = {
                "quantidade": quantidade,
                "descricao": descricao,
                "sabores": [],
                "borda": None,
                "preco": preco,
                "tipo": "bebida"
            }
            
            bebidas.append(bebida)
        
        elif padrao_linha_bebida.match(linha):
            partes = padrao_linha_bebida.findall(linha)[0]
            descricao = partes[0].strip()
            preco = partes[1].strip() if partes[1] else None
            
            bebida = {
                "quantidade": None,
                "descricao": descricao,
                "sabores": [],
                "borda": None,
                "preco": preco,
                "tipo": "bebida"
            }
            
            bebidas.append(bebida)
        
        elif padrao_linha_sabor.match(linha):
            partes = padrao_linha_sabor.findall(linha)[0]
            sabor = partes[1].strip()
            
            if bebidas:
                bebidas[-1]["sabores"].append(sabor)
    
    # verifica se realmente não tem bebidas a partir das categorias fazendo uma busca no texto pelos textos
    # que não estão no padrão ou que estão, se encontrar, pegar informação a esquerda (quantidade) INDEPENDENTE DO QUE TIVER e na proxima linha q tenha texto (sabores) INDEPENDENTE DO QUE TIVER
    # se não encontrar nada, verifica se tem bebida no texto
    if not bebidas:
        for linha in linhas:
            for categoria in categorias:
                if re.search(rf'\b{categoria}\b', linha, re.IGNORECASE):
                    # remove non-digit characters from quantidade and price
                    partes = linha.split()
                    quantidade = re.sub(r'\D', '', partes[0].strip()) if partes else None
                    descricao = ' '.join(partes[1:]).strip()
                    # Check if there's a price at the end of the line
                    # If there is, remove non-digit characters
                    # If there is no price, set it to None
                    preco = None
                    if len(partes) > 2:
                        preco = re.sub(r'\D', '', partes[-1].strip())
                    else:
                        preco = None
                    # Initialize sabores as an empty list
                    sabores = []
                    # Check for flavors in the next line
                    if linhas.index(linha) + 1 < len(linhas):
                        linha_sabor = linhas[linhas.index(linha) + 1].strip()
                        sabores.append(linha_sabor)
                    bebida = {
                        "quantidade": quantidade,
                        "descricao": descricao,
                        "sabores": sabores,
                        "borda": None,
                        "preco": preco,
                        "tipo": "bebida"
                    }
                    bebidas.append(bebida)
                    break
    

    return bebidas
