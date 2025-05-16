from pydantic import BaseModel
from typing import List

class Entrega(BaseModel):
    street: str
    number: str
    district: str
    quantidade_pizzas: int
    endereco_id: int
    prioridade: int = 999

    @property
    def endereco_completo(self):
        return f"{self.street}, {self.number}, {self.district}, Jardinópolis, SP"

class RoterizacaoInput(BaseModel):
    pizzaria: str
    api_key: str
    usuario_uids: List[str]
    entregas: List[Entrega]
