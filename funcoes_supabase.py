from load_files import supabase

def contar_pizzas_no_supabase(id_order: int | None = None):
    # 1. Buscar todos os itens válidos (com relation_id nulo) dos pedidos com status correto
    query = supabase.table("items") \
        .select("id_product, qtd") \
        .is_("relation_id", None)

    if id_order:
        query = query.eq("id_order", id_order)
    else:
        query = query.in_("id_order", supabase.table("orders")
                          .select("id")
                          .in_("status", ["Pronto para entrega", "Quase pronta"])
                          .execute()
                          .data)

    items_result = query.execute()

    if not items_result.data:
        print("Nenhum item encontrado.")
        return 0

    # 2. Coletar todos os id_product usados
    produtos_ativos = {}
    for item in items_result.data:
        id_prod = item["id_product"]
        qtd = item.get("qtd", 1)
        if id_prod:
            produtos_ativos[id_prod] = produtos_ativos.get(id_prod, 0) + qtd
    print(f"Produtos ativos: {produtos_ativos}")
    if not produtos_ativos:
        return 0

    # 3. Verificar se esses produtos são variações do tipo pizza
    # a tabela products tem o id_variation (que é o id da tabela variations que possui a coluna category)
    for id_prod, qtd in produtos_ativos.items():
        produto = supabase.rpc("get_product_by_id", {"product_id_input": id_prod, "uid_input": "efa9a9b6-bdd2-4199-8e51-4e37ae147fc2"}).execute()
        # se dentro dos resultados, variation, category, inclui palavra pizza
        if produto.data and "pizza" in produto.data[0]["variation"]["category"].lower():
            produtos_ativos[id_prod] = qtd
        else:
            produtos_ativos[id_prod] = 0
            
    # 4. Somar as quantidades de pizzas
    total_pizzas = sum(produtos_ativos.values())
    print(f"Total de pizzas: {total_pizzas}")
    return total_pizzas