from datetime import datetime
import openrouteservice
from load_files import supabase
from funcoes_supabase import contar_pizzas_no_supabase
from models import Endereco, RoterizacaoInput
from utils.geo import get_coordenadas_com_cache


async def buscar_enderecos_para_entrega(data: RoterizacaoInput) -> list[Endereco]:
    orders = supabase.table("orders") \
        .select("id, address, prioritaria, datetime") \
        .in_("status", ["Pronto para entrega", "Quase pronta"]) \
        .order("prioritaria", desc=True) \
        .order("datetime", desc=False) \
        .execute()
    print(f"Endereços encontrados: {orders.data}")
    address_ids = [o["address"] for o in orders.data if o.get("address")]

    if not address_ids:
        return []

    addresses = supabase.table("address") \
        .select("id, street, number, district, latitude, longitude") \
        .in_("id", address_ids) \
        .execute()

    entregas = []

    for order in orders.data:
      endereco = next((a for a in addresses.data if a["id"] == order["address"]), None)
      if not endereco:
          continue

      coordenadas_cliente = get_coordenadas_com_cache(f"{endereco['street']}, {endereco['number']}, {endereco['district']}, Jardinópolis, SP", data=data)
      if coordenadas_cliente and (endereco["latitude"] != coordenadas_cliente[0] or endereco["longitude"] != coordenadas_cliente[1]):
          # Atualizar coordenadas no banco de dados
          supabase.table("address").update({
              "latitude": coordenadas_cliente[0],
              "longitude": coordenadas_cliente[1]
          }).eq("id", endereco["id"]).execute()
          print(f"🔄 Coordenadas atualizadas para o endereço {endereco['street']}.")
      if not coordenadas_cliente:
          print(f"⚠️ Ignorando endereço '{endereco['street']}' devido à falta de coordenadas.")
          continue  # Ignorar este endereço e passar para o próximo

      order_datetime = datetime.fromisoformat(order["datetime"]) if order.get("datetime") else datetime.now()

      qtd_pizza = await contar_pizzas_no_supabase(id_order=order["id"])
      entregas.append(Endereco(
          id=endereco["id"],
          id_order=order["id"],
          rua=endereco["street"],
          numero=str(endereco["number"]),
          bairro=endereco["district"],
          cidade="Jardinópolis",
          estado="SP",
          quantidade_pizzas=qtd_pizza,
          prioridade=order["prioritaria"],
          endereco_completo=f"{endereco['street']}, {endereco['number']}, {endereco['district']}, Jardinópolis, SP",
          datetime=order_datetime,
          latitude=coordenadas_cliente[0],
          longitude=coordenadas_cliente[1]
      ))

    return entregas