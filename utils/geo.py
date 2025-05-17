
from typing import List, Optional

import openrouteservice
from load_files import supabase
from models import RoterizacaoInput
import traceback

def get_coordenadas(endereco: str, api_key: str) -> Optional[List[float]]:
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
            key=api_key,
            retry_over_query_limit=True,
            timeout=(10, 60)  # 10s para conectar, 60s para resposta # type: ignore
        )  # Certifique-se de que data.api_key é válido
        # Fazer a consulta de coordenadas
        response = client.pelias_search(text=endereco_completo) # type: ignore
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

def buscar_coordenadas_supabase_por_componentes(endereco: str):
    try:
        partes = endereco.split(',')
        street = partes[0].strip().lower() if len(partes) > 0 else None
        number = partes[1].strip() if len(partes) > 1 else None
        district = partes[2].strip().lower() if len(partes) > 2 else None
        city = "Jardinópolis"
        state = "SP"

        print(f"[Supabase] Buscando coordenadas para street='{street}', number='{number}', district='{district}', city='{city}', state='{state}'")

        response = supabase.table("address") \
            .select("latitude, longitude") \
            .eq("street", street) \
            .eq("number", int(number) if number is not None and number.isdigit() else 0) \
            .eq("district", district) \
            .eq("city", city) \
            .eq("state", state) \
            .execute()

        if not response:
            print("[Supabase] Resposta vazia da consulta")
            return None

        # Não tem data
        if response and hasattr(response, "data"):
            if response.data and len(response.data) > 0:
                coordenadas = response.data[0]
                print(f"[Supabase] Coordenadas encontradas: {coordenadas}")
                return [coordenadas["longitude"], coordenadas["latitude"]]
            else:
                print("[Supabase] Nenhum registro encontrado")
        else:
            if len(response) > 0: # type: ignore
                coordenadas = response[0] # type: ignore
                print(f"[Supabase] Coordenadas encontradas: {coordenadas}")
                return [coordenadas["longitude"], coordenadas["latitude"]]
            print(f"[Supabase] Resposta inesperada: {response}")
        return None
    except Exception as e:
        print(f"[Supabase] Erro ao consultar coordenadas: {e}")
        import traceback
        print(traceback.format_exc())
        return None



def get_coordenadas_com_cache(endereco: str, api_key: str) -> Optional[List[float]]:
    if endereco in coordenadas_cache:
        return coordenadas_cache[endereco]

    # Busca no banco usando colunas separadas
    coordenadas = buscar_coordenadas_supabase_por_componentes(endereco)
    if coordenadas:
        coordenadas_cache[endereco] = coordenadas
        return coordenadas

    # Se não encontrado, chama a API
    coordenadas = get_coordenadas(endereco, api_key=api_key)

    # Se a API respondeu, salva no banco (precisa salvar com os componentes, não só string)
    if coordenadas:
        partes = endereco.split(',')
        street = partes[0].strip().lower() if len(partes) > 0 else ""
        number = partes[1].strip() if len(partes) > 1 else "S/N"
        district = partes[2].strip().lower() if len(partes) > 2 else ""
        city = "Jardinópolis"
        state = "SP"

        supabase.table("address").insert({
            "street": street,
            "number": int(number) if number.isdigit() else 0,
            "district": district,
            "city": city,
            "state": state,
            "latitude": coordenadas[1],
            "longitude": coordenadas[0]
        }).execute()

    coordenadas_cache[endereco] = coordenadas
    return coordenadas
