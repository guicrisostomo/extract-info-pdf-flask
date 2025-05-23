import re
from typing import Dict, List
import logging

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_items(linhas: List[str]) -> List[Dict]:
    itens = []

    padrao_item = re.compile(
        r"^(\d+)\s+(PIZZA\s+GIGANTE|PIZZA\s+GRANDE|PIZZA\s+M[ÉE]DIA|PIZZA\s+PEQUENA|REFRIGERANTE|MARMITEX|AÇA[IÍ]|LANCHES|HAMB[ÚU]RGUER|SOBREMESA|SALGADO|POR[CÇ][AÃ]O|PRATO|COMBO)",
        re.IGNORECASE
    )
    padrao_preco = re.compile(r"\d+,\d{2}")
    padrao_sabor_fracionado = re.compile(r"^\s*(\d/\d)?\s*[-:]?\s*([A-Z0-9ÇÃÕÂÊÁÉÍÓÚ a-z\/]+)$", re.IGNORECASE)
    padrao_borda = re.compile(r'^>>\s*(.+)$', re.IGNORECASE)
    # padrao_acrescimo = exemplo: c/ cebola, c/ azeitona, c/ bacon
    padrao_acrescimo = re.compile(r'^\s*c/\s*([A-Z0-9ÇÃÕÂÊÁÉÍÓÚ a-z\/]+)$', re.IGNORECASE)
    # padrao_decrescimo = exemplo: s/ cebola, s/ azeitona, s/ bacon
    padrao_decrescimo = re.compile(r'^\s*s/\s*([A-Z0-9ÇÃÕÂÊÁÉÍÓÚ a-z\/]+)$', re.IGNORECASE)
    # padrao_observacao = exemplo: obs. cliente: sem cebola, obs. cliente: sem azeitona, obs. cliente: sem bacon
    padrao_observacao = re.compile(r'^\s*obs\.?\s*cliente:\s*(.+)$', re.IGNORECASE)

    item_atual = None

    aguardando_borda = False
    aguardando_observacao = False
    buffer_observacao = []

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        # Início de novo item
        match_item = padrao_item.match(linha)
        if match_item:
            if item_atual:
                # Salva observação acumulada, se houver
                if buffer_observacao:
                    item_atual["observacao"] = " ".join(buffer_observacao).strip()
                    buffer_observacao = []
                itens.append(item_atual)
            partes = linha.split()
            qtd = partes[0]
            descricao = " ".join(partes[1:-1])
            preco = partes[-1] if padrao_preco.match(partes[-1]) else None

            item_atual = {
                "quantidade": qtd,
                "descricao": descricao.title(),
                "sabores": [],
                "borda": None,
                "preco": preco,
                "tipo": "item",
                "observacao": None,
                "acrescimo": [],
                "decrescimo": [],
            }
            aguardando_borda = False
            aguardando_observacao = False
            buffer_observacao = []
            continue

        if not item_atual:
            continue

        # Se linha anterior era 'BORDA:', pega borda agora
        if aguardando_borda:
            match_borda = padrao_borda.match(linha)
            if match_borda:
                item_atual["borda"] = match_borda.group(1).strip().title()
            else:
                item_atual["borda"] = linha.title()
            aguardando_borda = False
            continue

        # Detecta se linha é só 'BORDA:'
        if linha.upper() == "BORDA:":
            aguardando_borda = True
            continue

        # Detecta se linha é só 'OBSERVAÇÕES:' ou 'OBSERVAÇÃO:'
        if linha.upper() in ("OBSERVAÇÕES:", "OBSERVAÇÃO:"):
            aguardando_observacao = True
            continue

        # Borda padrão (linha já vem com >>)
        match_borda = padrao_borda.match(linha)
        if match_borda:
            item_atual["borda"] = match_borda.group(1).strip().title()
            continue

        # Observação do cliente padrão (pode ser multiline)
        match_observacao = padrao_observacao.match(linha)
        if match_observacao:
            buffer_observacao = [match_observacao.group(1).strip()]
            aguardando_observacao = True
            continue

        # Acréscimo
        match_acrescimo = padrao_acrescimo.match(linha)
        if match_acrescimo:
            sabor = match_acrescimo.group(1).strip().title()
            item_atual["acrescimo"].append(sabor)
            continue

        # Decrescimo
        match_decrescimo = padrao_decrescimo.match(linha)
        if match_decrescimo:
            sabor = match_decrescimo.group(1).strip().title()
            item_atual["decrescimo"].append(sabor)
            continue

        # Sabores com ou sem fração
        match_sabor = padrao_sabor_fracionado.match(linha)
        if match_sabor:
            sabor = match_sabor.group(2).strip().title()
            item_atual["sabores"].append(sabor)
            continue

        # Preço separado
        if padrao_preco.match(linha):
            item_atual["preco"] = linha
            continue

        # Se está acumulando observação, adiciona linha
        if aguardando_observacao:
            # Se a linha indica início de outro campo, para de acumular observação
            if re.match(r"^(TOTAL ITENS:|TAXA DE ENTREGA:|VALOR DO PEDIDO:|FORMA DE PAGAMENTO:|BANDEIRA DO CARTÃO:|TEMPO P/ ENTREGA:)", linha, re.IGNORECASE):
                aguardando_observacao = False
                item_atual["observacao"] = " ".join(buffer_observacao).strip()
                buffer_observacao = []
                # continue para processar essa linha normalmente
            else:
                buffer_observacao.append(linha)
                continue

    # Salva último item
    if item_atual:
        if buffer_observacao:
            item_atual["observacao"] = " ".join(buffer_observacao).strip()
        itens.append(item_atual)

    return itens

# Exemplo de uso
if __name__ == "__main__":
    dados = [
        'LA PASTA', '(16) 9-9288-3809', 'ENTREGA', '08/05/2025 ÀS 18:53:01', 'ORIGEM: LOCAL', 'ATENDENTE: CAIXA',
        'CLIENTE: DAVID', 'TEL: (16) 9-9345-3444', '005', '00000206', 'ENDEREÇO: RIA FLÁVIO JOSÉ MARCHIORI,',
        '194, SANTO ANTONIO, JARDINÓPOLIS/SP', '** NOVO CLIENTE **',
        '01 PIZZA GRANDE', '1/2 - CALABRESA CATUPIRY', '1/2 - PORTUGUESA',
        'BORDA:', '>> CHOCOLATE',
        '01 REFRIGERANTE', 'COCA-COLA ORIGINAL 2L',
        'VALOR DO', 'PEDIDO:', 'FORMA DE', 'PAGAMENTO:', '85,00',
        'CARTÃO DE', 'DÉBITO',
        'TEMPO P/ ENTREGA: 40 MIN | 19:33:01'
    ]

    itens = parse_items(dados)
    from pprint import pprint
    pprint(itens)
