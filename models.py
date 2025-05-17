from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel


class ItemPedido(BaseModel):
    quantidade: str
    descricao: str
    sabores: Optional[List[str]] = None
    borda: Optional[str] = None
    preco: str
    tipo: Optional[str] = None

class Endereco(BaseModel):
    id: Optional[int] = None
    id_order: Optional[int] = None
    rua: str
    numero: str
    bairro: Optional[str] = None
    cidade: str
    estado: str
    complemento: Optional[str] = None
    cep: Optional[str] = None
    prioridade: Optional[bool | int] = 0
    referencia: Optional[str] = None
    datetime: Optional[datetime]
    quantidade_pizzas: Optional[int] = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    @property
    def endereco_completo(self):
        return f"{self.rua}, {self.numero}, {self.bairro}".strip(", ")

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
    tem_bebida: bool
    lista_bebidas: Optional[List[ItemPedido]] = None
    total_itens: str
    taxa_entrega: Optional[str] = None
    valor_total: str
    forma_pagamento: str
    tempo_entrega: Optional[str] = None
    observacoes: Optional[str] = None

class Entrega(BaseModel):
    street: str
    number: str
    district: str
    quantidade_pizzas: int
    prioridade: Optional[int] = 1

    @property
    def endereco_completo(self):
        return f"{self.street}, {self.number}, {self.district}, Jardinópolis, SP"

class RoterizacaoInput(BaseModel):
    pizzaria: str
    api_key: str
    usuario_uids: Optional[List[uuid.UUID]] = []  # Lista de UUIDs dos motoboys
    capacidade_maxima: int = 4

    def to_dict(self):
        """Converte o objeto para um dicionário serializável em JSON."""
        return {
            "api_key": self.api_key,
            "pizzaria": self.pizzaria,
            "capacidade_maxima": self.capacidade_maxima,
            "usuario_uids": self.usuario_uids,
        }

class TempoEstimadoInput(BaseModel):
    api_key: str
    pizzaria: str
    tipo: Optional[str] = None  # "retirada", "entrega" ou None

