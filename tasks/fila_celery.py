from datetime import datetime, timezone
import logging
import uuid

from requests import RequestException
from load_files import supabase, logger
from celery_app import app as celery_app
from motoqueiros_ativos import motoboys_ociosos, obtem_motoboys
from utils.geo import get_coordenadas_com_cache, calcular_prioridade_por_tempo
from tasks_helpers import buscar_enderecos_para_entrega
import openrouteservice
from openrouteservice.optimization import Job, Vehicle
from models import RoterizacaoInput, Endereco

import uuid
  
@celery_app.task(
  bind=True,
  autoretry_for=(openrouteservice.exceptions.ApiError, RequestException),
  retry_backoff=True,
  retry_kwargs={"max_retries": 5},
  on_failure=logger.error
  
)
def reatribuir_entregas_para_motoboy_ocioso(self, api_key: str, pizzaria: str, capacidade_maxima: int):
    # Verifica se o entregador está ocioso
    todas_entregas = buscar_enderecos_para_entrega(RoterizacaoInput(api_key=api_key, pizzaria=pizzaria, capacidade_maxima=capacidade_maxima))

    todos_motoboys = obtem_motoboys()
    motoboys_disponiveis = motoboys_ociosos(todos_motoboys)
    if not motoboys_disponiveis:
        return {"error": "Nenhum entregador ocioso e ativo no momento"}

    
    entregas_disponiveis = []
    for ent in todas_entregas:
        rota = supabase.table("routes").select("*").eq("id_order", ent.id_order).execute().data
        if rota and any(r.get("in_progress") for r in rota):
            # Já existe rota em andamento para esse pedido, não incluir novamente
            continue

        endereco = supabase.table("address").select("*").eq("id", ent.id).execute().data[0]
        coordenadas = get_coordenadas_com_cache(
            f"{endereco['street']}, {endereco['number']}, {endereco['district']}, Jardinópolis, SP",
            api_key=api_key
        )
        if not coordenadas:
            continue
        entrega = Endereco(
            id=endereco["id"],
            id_order=ent.id_order,
            quantidade_pizzas=ent.quantidade_pizzas,
            prioridade=ent.prioridade,
            datetime=datetime.now(timezone.utc),
            latitude=coordenadas[0],
            longitude=coordenadas[1],
            rua=endereco["street"],
            numero=str(endereco["number"]),
            bairro=endereco["district"],
            cidade=endereco["city"],
            estado=endereco["state"],
        )
        entregas_disponiveis.append(entrega)

    if not entregas_disponiveis:
        return {"status": "sem entregas disponíveis"}

    entregas_disponiveis.sort(key=lambda x: (-x.prioridade, x.datetime))
    entregas_selecionadas = entregas_disponiveis[:capacidade_maxima * len(todos_motoboys)]
    
    print(f"Entregas selecionadas: {entregas_selecionadas}")
        
    coord_pizzaria = get_coordenadas_com_cache(pizzaria, api_key=api_key)
    if not coord_pizzaria:
        return {"error": "Coordenadas da pizzaria não encontradas"}

    for motoboy in todos_motoboys:
        supabase.table("routes").delete().eq("motoboy_uid", motoboy).eq("started", False).execute()
        
    jobs = []
    job_map = {}
    for idx, entrega in enumerate(entregas_disponiveis):
        prioridade = 10 if entrega.prioridade else calcular_prioridade_por_tempo(
            int((datetime.now(timezone.utc) - entrega.datetime).total_seconds() / 60), 3600
        )
        job = Job(
            id=idx + 1,
            location=[float(entrega.latitude), float(entrega.longitude)],
            amount=[entrega.quantidade_pizzas or 0],
            service=300,
            priority=prioridade
        )
        jobs.append(job)
        job_map[job.id] = entrega

    vehicles = []
    for idx, motoboy in enumerate(motoboys_disponiveis):
        vehicle = Vehicle(
            id=idx + 1,
            profile='driving-car',
            start=coord_pizzaria,
            end=coord_pizzaria,
            capacity=[capacidade_maxima]
        )
        vehicles.append(vehicle)

    client = openrouteservice.Client(key=api_key)
    result = client.optimization(jobs=jobs, vehicles=vehicles) # type: ignore
    
    for rota in result["routes"]:
        motoboy_id = motoboys_disponiveis[rota["vehicle"] - 1]
        tempo_acumulado = 0
        ordem_entrega = 1
        steps = rota["steps"]
        for step in steps[1:-1]:  # ignorando início e fim (pizzaria)
            job_id = step.get("job")
            entrega = job_map.get(job_id)
            if not entrega:
                continue
            tempo_step = step["duration"] // 60
            tempo_acumulado += tempo_step
            supabase.table("routes").insert({
                "motoboy_uid": str(motoboy_id),
                "start_time": datetime.utcnow().isoformat(),
                "tempo_total_minutos": tempo_acumulado,
                "cnpj": "1",
                "started": False,
                "id_order": entrega.id_order,
                "ordem": ordem_entrega
            }).execute()
            ordem_entrega += 1

    return {"status": "reatribuido", "motoboys": [str(m) for m in motoboys_disponiveis]}
