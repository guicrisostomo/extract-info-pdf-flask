
from typing import List, Optional

import openrouteservice

from models import RoterizacaoInput
import traceback

def get_coordenadas(endereco: str, data: RoterizacaoInput) -> Optional[List[float]]:
    try:
        if not isinstance(endereco, str):
            raise ValueError(f"O parâmetro 'endereco' deve ser uma string, mas recebeu: {type(endereco)} - {endereco}")
        if not endereco:
            raise ValueError("O parâmetro 'endereco' não pode ser vazio.")
        # Dividir o endereço em partes
        partes = endereco.split(',')
        print(f"Partes do endereço: {partes}")
        print(f"Endereço original: {endereco}")
        street = partes[0].strip() if len(partes) > 0 else ""
        number = partes[1].strip() if len(partes) > 1 else "S/N"  # Valor padrão "S/N" para sem número
        district = partes[2].strip() if len(partes) > 2 else ""  # Valor padrão vazio para distrito

        # Construir o endereço completo para consulta
        endereco_completo = f"{street}, {number}, {district}, Jardinópolis, SP"
        print(f"Consultando coordenadas para: {endereco_completo}")
        client = openrouteservice.Client(
            key=data.api_key,
            retry_over_query_limit=True,
            timeout=(10, 60)  # 10s para conectar, 60s para resposta
        )  # Certifique-se de que data.api_key é válido
        # Fazer a consulta de coordenadas
        response = client.pelias_search(text=endereco_completo)
        print(response)
        if response and "features" in response and len(response["features"]) > 0:
            coords = response["features"][0]["geometry"]["coordinates"]
            return coords  # Retorna [longitude, latitude]

        print(f"⚠️ Nenhuma coordenada encontrada para o endereço: {endereco_completo}")
        return None
    except Exception as e:
        print(f"Erro ao obter coordenadas para o endereço '{endereco}': {e}")
        print(traceback.format_exc())
        # Exibir o stack trace completo para depuração
        return None


def calcular_prioridade_por_tempo(tempo_espera_segundos: int, tempo_limite_segundos: int) -> int:
    """
    Calcula a prioridade com base no tempo de espera.
    Retorna um valor de 1 (muito novo) a 9 (muito antigo).
    """
    escala = 9  # Escala de prioridade de 1 a 9
    proporcao = min(tempo_espera_segundos / tempo_limite_segundos, 1)  # Limita a proporção a no máximo 1
    prioridade = int(proporcao * (escala - 1)) + 1  # Converte para escala de 1 a 9
    return prioridade

coordenadas_cache = {}

def get_coordenadas_com_cache(endereco: str, data: RoterizacaoInput) -> Optional[List[float]]:
    if endereco in coordenadas_cache:
        return coordenadas_cache[endereco]

    coordenadas = get_coordenadas(endereco, data)
    if coordenadas is None:
        print(f"⚠️ Coordenadas não encontradas para o endereço: {endereco}")
    coordenadas_cache[endereco] = coordenadas
    return coordenadas