from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ItemPedido(BaseModel):
    quantidade: str
    descricao: str
    sabores: Optional[List[str]] = None
    borda: Optional[str] = None
    preco: str

class Endereco(BaseModel):
    rua: str
    numero: str
    bairro: str
    cidade: str
    estado: str
    complemento: Optional[str] = None
    cep: Optional[str] = None

class PedidoResponse(BaseModel):
    tipo_venda: str
    senha: Optional[str] = None
    data_hora: datetime
    cliente: str
    telefone: str
    novo_cliente: bool
    origem: Optional[str] = None
    atendente: Optional[str] = None
    endereco: Optional[Endereco] = None
    itens: List[ItemPedido]
    total_itens: str
    taxa_entrega: Optional[str] = None
    valor_total: str
    forma_pagamento: str
    tempo_entrega: Optional[str] = None
    observacoes: Optional[str] = None