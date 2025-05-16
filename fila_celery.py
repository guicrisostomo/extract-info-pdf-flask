import openrouteservice
from datetime import datetime, timezone, timedelta
from celery_app import celery_app
from models import RoterizacaoInput
from utils.geo import get_coordenadas_com_cache, calcular_prioridade_por_tempo
from tasks_helpers import buscar_enderecos_para_entrega
import traceback
from openrouteservice.optimization import Job, Vehicle


@celery_app.task
async def processar_roterizacao(dataParam: dict):
        # Verificar se os dados estão no formato correto
        if not isinstance(dataParam, dict):
            return {"error": "Os dados enviados para a tarefa não estão no formato correto"}

        data = RoterizacaoInput(
            api_key=dataParam["api_key"],
            capacidade_maxima=dataParam["capacidade_maxima"],
            usuario_uids=dataParam["usuario_uids"],
            pizzaria=dataParam["pizzaria"]
        )

        # Validar API Key
        if not data.api_key:
            return {"error": "API Key não fornecida ou inválida"}

        coord_pizzaria = get_coordenadas_com_cache(data.pizzaria, data=data)
        if not coord_pizzaria or len(coord_pizzaria) != 2:
            return {"error": "Coordenadas da pizzaria inválidas ou não encontradas"}

        # Buscar entregas restantes
        entregas_restantes = await buscar_enderecos_para_entrega(data)
        if not isinstance(entregas_restantes, list):
            print(f"⚠️ Erro: buscar_enderecos_para_entrega retornou {entregas_restantes}")
            return {"error": "Erro ao buscar entregas restantes"}
        if not entregas_restantes:
            return {"error": "Nenhuma entrega encontrada"}

        # Ordenar e selecionar as 6 entregas mais importantes
        entregas_restantes.sort(key=lambda x: (-x.prioridade, x.datetime))
        entregas_selecionadas = entregas_restantes[:6]

        jobs = []
        enderecos_sem_coordenadas = []  # Lista para registrar endereços sem coordenadas
        enderecos_ordenados = []  # Lista para registrar endereços ordenados com tempos estimados
        tempo_total = 0
        
        jobs.append(Job(
            id=0,
            location=[float(coord_pizzaria[0]), float(coord_pizzaria[1])],
            amount=[0],
            service=0,  # Sem tempo de serviço para a pizzaria
            priority=0
        ))
        
        for idx, entrega in enumerate(entregas_selecionadas):
            coord = get_coordenadas_com_cache(entrega.endereco_completo, data)
            if not coord:
                print(f"⚠️ Coordenadas não encontradas para o endereço: {entrega.endereco_completo}")
                enderecos_sem_coordenadas.append(entrega.endereco_completo)
                continue
            # tempo que  a pessoa está esperando pelo pedido
            tempo_passado_minutos = int((datetime.now(timezone.utc) - entrega.datetime).total_seconds() / 60)
            job = Job(
                id=idx + 1,
                location=[float(coord[0]), float(coord[1])],
                amount=[entrega.quantidade_pizzas or 0],
                service=300,
                priority=10 if entrega.prioridade else calcular_prioridade_por_tempo(tempo_passado_minutos, 3600),
            )
            jobs.append(job)

        jobs.append(Job(
            id=len(jobs) + 1,
            location=[float(coord_pizzaria[0]), float(coord_pizzaria[1])],
            amount=[0],
            service=0,  # Sem tempo de serviço para a pizzaria
            priority=0
        ))
        
        # Converte veículo para objeto Vehicle
        vehicles = [
            Vehicle(
                id=1,
                profile='driving-car',
                start=coord_pizzaria,
                end=coord_pizzaria,
                capacity=[data.capacidade_maxima]
            )
        ]

        if not jobs:
            print("⚠️ Nenhum job foi criado. Verifique os dados das entregas.")
            return {
                "error": "Nenhum job foi criado",
                "enderecos_sem_coordenadas": enderecos_sem_coordenadas
            }

        # Validar jobs e vehicles antes de enviar a requisição
        if not jobs or not vehicles:
            print(f"⚠️ Jobs ou vehicles estão vazios. Jobs: {jobs}, Vehicles: {vehicles}")
            return {"error": "Jobs ou vehicles estão vazios"}

        

        # Logar o conteúdo de post_json antes de enviar

        try:
            client = openrouteservice.Client(
                key=data.api_key,
                retry_over_query_limit=True,
                timeout=(10, 60)  # 10s para conectar, 60s para resposta
            )
            result = client.optimization(
                jobs=jobs,
                vehicles=vehicles,
            )

            
            if result is None:
                print("⚠️ Resultado da API é None — possível erro na requisição")
                return {
                    "error": "Resposta da API veio como None (falha ao obter resultado)",
                    "enderecos_sem_coordenadas": enderecos_sem_coordenadas
                }
            if "routes" not in result or not isinstance(result["routes"], list):
                print(f"⚠️ Resultado malformado ou inesperado: {result}")
                return {
                    "error": "Resposta da API malformada ou sem rotas",
                    "enderecos_sem_coordenadas": enderecos_sem_coordenadas
                }
                
            if result is None or "routes" not in result or not isinstance(result["routes"], list):
                print(f"⚠️ Resultado malformado ou inesperado: {result}")
                return {
                    "error": "Resposta da API malformada ou sem rotas",
                    "enderecos_sem_coordenadas": enderecos_sem_coordenadas
                }

            # Processar rotas e calcular tempo total
            rotas = result["routes"][0]["steps"]
            tempo_total = sum(step["duration"] for step in rotas) // 60  # Converter segundos para minutos
            # tempo_acumulado será inicializado com o valor do tempo que o entregador levará para chegar na primeira entrega
            tempo_acumulado = rotas[1]["duration"] // 60  # Converter segundos para minutos
            
            for step, entrega in zip(rotas, entregas_selecionadas):
                tempo_acumulado += step["duration"] // 60  # Converter segundos para minutos
                enderecos_ordenados.append({
                    "endereco": entrega.endereco_completo,
                    "tempo_entrega_minutos": tempo_acumulado,
                    "prioridade": entrega.prioridade,
                    "quantidade_pizzas": entrega.quantidade_pizzas,
                    "id_order": entrega.id_order,
                })
                
            # Gerar link para o Google Maps
            link_google_maps = "https://www.google.com/maps/dir/?api=1"
            for entrega in entregas_selecionadas:
                coord = get_coordenadas_com_cache(entrega.endereco_completo, data)
                if coord:
                    link_google_maps += f"&destination={coord[0]},{coord[1]}"
                else:
                    print(f"⚠️ Coordenadas não encontradas para o endereço: {entrega.endereco_completo}")
                    enderecos_sem_coordenadas.append(entrega.endereco_completo)

            return {
                "enderecos_sem_coordenadas": enderecos_sem_coordenadas,
                "enderecos_ordenados": enderecos_ordenados,
                "tempo_total_minutos": tempo_total,
                "link_google_maps": link_google_maps
            }

        except Exception as e:
          print(f"⚠️ Exceção ao chamar a API OpenRouteService: {e}")
          print(f"Endereços sem coordenadas: {enderecos_sem_coordenadas}")
          traceback.print_exc()  # Mostra o stack trace completo
          return {"error": f"Erro ao chamar a API OpenRouteService: {str(e)}"}
        finally:
            # Limpeza de recursos, se necessário
            pass