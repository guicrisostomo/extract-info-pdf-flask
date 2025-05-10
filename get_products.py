import re
from typing import List, Dict

def parse_produtos(texto: str) -> List[Dict]:
    """
    Extrai produtos do texto seguindo o formato dos PDFs:
    QTD ITEM    PRECO
    ---
    01 PIZZA GRANDE    67,00
    1/2 - CALABRESA CATUPIRY
    1/2 - PORTUGUESA
    BORDA: >> CHOCOLATE
    """
    # Padrão para capturar cada bloco de produto
    produto_blocks = re.split(r'\n\s*---\n', texto)
    
    produtos = []
    
    for block in produto_blocks:
        if not block.strip():
            continue
            
        # Padrão para a linha principal do produto (quantidade, descrição e preço)
        main_line_match = re.search(r'(\d+)\s+(.+?)\s+(\d+,\d{2})\s*$', block, re.MULTILINE)
        if not main_line_match:
            continue
            
        qtd = main_line_match.group(1)
        descricao = main_line_match.group(2).strip()
        preco = main_line_match.group(3)
        
        # Extrair sabores e borda
        sabores = []
        borda = None
        
        # Padrão para sabores (1/2 - CALABRESA CATUPIRY)
        sabores_matches = re.finditer(r'(\d+/\d+\s*-\s*[^\n]+)', block)
        for match in sabores_matches:
            sabores.append(match.group(1))
            
        # Padrão para borda (BORDA: >> CHOCOLATE)
        borda_match = re.search(r'BORDA:\s*>>\s*([^\n]+)', block)
        if borda_match:
            borda = borda_match.group(1).strip()
        
        produto = {
            'quantidade': qtd,
            'descricao': descricao,
            'preco': preco,
            'sabores': sabores if sabores else None,
            'borda': borda
        }
        
        produtos.append(produto)
    
    return produtos