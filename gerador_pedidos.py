import random
from datetime import datetime, timedelta
from supabase import create_client, Client
import uuid
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente
load_dotenv()
# Defina o caminho do arquivo .env
caminho_arquivo_env = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(caminho_arquivo_env):
    load_dotenv(caminho_arquivo_env)
else:
    print(f"Arquivo .env não encontrado em {caminho_arquivo_env}. Verifique o caminho.")
# CONFIGURAÇÃO
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) # type: ignore

# CONSTANTES
STATUSES = ["Pronto para entrega", "Quase pronta", "Impresso"]

def gerar_data_aleatoria():
    if random.random() < 0.5:
        return datetime.now() - timedelta(minutes=random.randint(5, 180))
    else:
        return datetime.now() - timedelta(days=random.randint(1, 3), minutes=random.randint(0, 59))

# Buscar dados existentes
usuarios = supabase.table("tb_user").select("uid").execute().data
enderecos = supabase.table("address").select("*").eq("cnpj", 1).execute().data
produtos = supabase.table("products").select("id, id_variation, name, description, price, variations(category)").execute().data

# Filtrar pizzas
pizzas = [p for p in produtos if "pizza" in p['variations']['category'].lower()]
if not pizzas:
    raise Exception("Nenhuma pizza encontrada nos produtos.")

def criar_pedido(i):
    usuario = random.choice(usuarios)
    uid = usuario['uid']
    endereco = next((e for e in enderecos if e["uid"] == uid), None)
    if not endereco:
        return

    datetime_pedido = gerar_data_aleatoria()
    status = random.choice(STATUSES)
    prioritary = (i == 0)
    password = str(random.randint(1000, 9999))

    pedido = {
        "cnpj": 1,
        "type": "entrega",
        "address": endereco["id"],
        "prioritaria": prioritary,
        "status": status,
        "password": password,
        "datetime": datetime_pedido.isoformat()
    }

    pedido_result = supabase.table("orders").insert(pedido).execute()
    pedido_id = pedido_result.data[0]["id"]

    supabase.table("user_order").insert({"uid": uid, "id_order": pedido_id}).execute()

    total = 0
    num_pizzas = random.randint(1, 4)

    for _ in range(num_pizzas):
        pizza = random.choice(pizzas)
        id_variation = pizza["id_variation"]
        id_produto = pizza["id"]

        # Adicionar variação
        supabase.table("items").insert({
            "id_order": pedido_id,
            "id_product": id_produto,
            "id_variation": id_variation,
            "qtd": 1
        }).execute()

        # Calcular total
        total += float(pizza["price"])

    supabase.table("orders").update({"total": total}).eq("id", pedido_id).execute()

# Gerar 20 pedidos
for i in range(20):
    try:
        criar_pedido(i)
        print(f"Pedido {i+1} criado com sucesso.")
    except Exception as e:
        print(f"Erro ao criar pedido {i+1}: {e}")