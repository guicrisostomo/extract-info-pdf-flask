import asyncio
from io import BytesIO
import json
import os
import threading
import time
from urllib.parse import quote_plus
import uuid
import ocrmypdf
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket
from typing import Optional, Dict
from datetime import datetime, timezone

from fastapi.responses import JSONResponse
import websocket
from tasks.fila_celery import reatribuir_entregas_para_motoboy_ocioso
from parse_items import parse_items
from pdf2image import convert_from_bytes
import pytesseract
import re
import urllib
from models import Endereco, RoterizacaoInput,  TempoEstimadoInput
from dotenv import load_dotenv
from datetime import datetime
from utils.geo import get_coordenadas
from celery_app import app as celery_app
from load_files import SUPABASE_KEY, SUPABASE_URL, supabase, logger
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
def verify_tesseract() -> bool:
    try:
        langs = pytesseract.get_languages(config='')
        if 'por' not in langs:
            raise RuntimeError("Portuguese language data not found")
        return True
    except Exception as e:
        logger.error(f"Tesseract verification failed: {e}")
        return False


from tempfile import NamedTemporaryFile
import fitz  # PyMuPDF

import asyncio

STATUS_VALIDOS = {"Pronto para entrega", "Quase pronta", "Entregador definido", "Saiu para entrega", "Entregue"}

clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except:
        clients.remove(websocket)

def broadcast_to_clients(message):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    coros = [client.send_text(message) for client in clients]
    loop.run_until_complete(asyncio.gather(*coros))

def on_message(ws, message):
    data = json.loads(message)
    print(f"Mensagem recebida: {data}")
    logger.info(f"Mensagem recebida: {data}")
    if data.get("event") == "postgres_changes":
        payload = data["payload"]
        # Corrigido para acessar o novo registro
        record = payload["data"]["record"]
        status = record.get("status")
        order_id = record.get("id")
        broadcast_to_clients(f"Pedido {order_id} atualizado para {status}")
        if status in STATUS_VALIDOS:
            reatribuir_entregas_para_motoboy_ocioso.delay(
                api_key=os.getenv("OPENROUTE_API_KEY"),
                pizzaria="Avenida Belarmino Pereira de Oliveira, 429, Vila Oliveira",
                capacidade_maxima=4
            )
        else:
            print(f"Status inválido recebido: {status}")

def on_open(ws):
    print("Conectado ao Realtime Supabase")
    logger.info("Conectado ao Realtime Supabase")
    ws.send(json.dumps({
        "event": "phx_join",
        "topic": "realtime:public:orders",
        "payload": {
            "config": {
                "broadcast": {"self": False},
                "presence": {},
                "postgres_changes": [
                    {
                        "event": "UPDATE",
                        "schema": "public",
                        "table": "orders",
                        "filter": "status=neq.null"
                    }
                ],
            }
        },
        "ref": "1"
    }))

def start_realtime():
    if SUPABASE_KEY is None or SUPABASE_URL is None:
        logger.error("SUPABASE_KEY or SUPABASE_URL not set in environment variables.")
        return
    realtime_url = f"wss://{SUPABASE_URL.replace('https://', '')}/realtime/v1/websocket?apikey={SUPABASE_KEY}"
    logger.info(f"Conectando ao websocket: {realtime_url}")
    while True:
        try:
            ws = websocket.WebSocketApp(
                realtime_url,
                on_open=on_open,
                on_message=on_message
            )
            ws.run_forever()
        except Exception as e:
            logger.error(f"Erro no websocket: {e}")
        # Aguarda 10 segundos antes de tentar reconectar
        time.sleep(10)
# ... (restante dos imports e código)

# Dicionário para guardar o último estado das rotas por motoboy
last_routes_state = {}


# Inicie o listener no startup do FastAPI

def parse_endereco(texto: str) -> Optional[Endereco]:
    padrao_endereco = re.compile(
        r"ENDEREÇO:\s*([^,]+),\s*(\d+)(?:\s*\(([^)]+)\))?,\s*([^,]+),\s*([^/]+)/([A-Z]{2})",
        flags=re.IGNORECASE
    )

    match = padrao_endereco.search(texto)
    if not match:
        return None

    rua = match.group(1).replace(",", "").strip()
    numero = match.group(2).strip()
    referencia = match.group(3).strip() if match.group(3) else None
    bairro = match.group(4).strip()
    cidade = match.group(5).strip()
    estado = match.group(6).strip()

    complemento = f"Referência: {referencia}" if referencia else None

    return Endereco(
        rua=rua,
        numero=numero,
        bairro=bairro,
        cidade=cidade,
        estado=estado,
        complemento=complemento,
        datetime=datetime.now(timezone.utc),
    )

def extrair_telefone(texto: str) -> str:
    """
    Extrai o segundo telefone brasileiro do texto com correção de erros comuns de OCR.
    Ignora números que não seguem o padrão de telefone válido.
    Se não encontrar um segundo número, retorna o primeiro.
    Exemplo: (16) -0737-3515 → 16997373515
    """
    print(f"Texto para extrair telefone: {texto}")
    padrao_telefone = re.compile(
        r"(?:(?:TEL|TELEFONE|WHATSAPP|CELULAR|FONE)\s*:\s*)?"
        r"\(?(\d{2})\)?\s*[-]?(\d{1,2})?[-]?(\d{4,5})[-]?(\d{4})",
        re.IGNORECASE
    )

    # Encontrar todos os números no texto
    matches = padrao_telefone.findall(texto)
    print(f"Números encontrados: {matches}")

    if not matches:
        return "Número não encontrado"

    # Formatar os números encontrados
    numeros = []
    for match in matches:
        ddd = match[0]
        numero = (match[1] or "") + match[2] + match[3]
        telefone = f"{ddd}{numero}"

        # Verificar se o número tem 10 ou 11 dígitos (padrão de telefone brasileiro)
        if len(telefone) in [10, 11]:
            numeros.append(telefone)

    # Retornar o segundo número válido, se existir, ou o primeiro
    if len(numeros) > 1:
        return numeros[len(numeros) - 1]
    elif numeros:
        return numeros[0]

    return "Número não encontrado"
  
def extract_clean_payment(text: str) -> str:
    pattern = r'(?i)(?:CART[\u00c3A]O\s*(?:DE\s*)?(?:D[\u00c9E]BITO|CRÉDITO)|PIX|DINHEIRO|PAGAR\s*NO\s*LOCAL)'
    try:
        match = re.search(pattern, text)
        if match:
            payment = match.group(0).title()
            payment = (payment.replace("Cartao", "Cartão")
                              .replace("Debito", "Débito")
                              .replace("Credito", "Crédito"))
            return payment
    except Exception as e:
        logger.error(f"Payment extraction error: {e}")

    return "Não Especificado"
  
def parse_campos(texto: str) -> Dict:
    texto = texto.upper()
    resultado = {}

    tipo_match = re.search(r"(ENTREGA|RETIRAR|BALCAO|MESA)\s*(\d{1,5})?", texto)
    if tipo_match:
        resultado["tipo_venda"] = tipo_match.group(1).capitalize()
        if tipo_match.group(2):
            resultado["senha"] = tipo_match.group(2)

    data_match = re.search(r"(\d{2}/\d{2}/\d{4})\s*ÀS\s*(\d{2}:\d{2}:\d{2})", texto)
    if data_match:
        resultado["data_hora"] = datetime.strptime(
            f"{data_match.group(1)} {data_match.group(2)}",
            "%d/%m/%Y %H:%M:%S"
        )

    cliente_match = re.search(r"CLIENTE:\s*(.+?)(?:\n|$)", texto)
    if cliente_match:
        resultado["cliente"] = cliente_match.group(1).strip().title()

    email_match = re.search(r"EMAIL:\s*([^\n]+)", texto)
    if email_match:
        resultado["email"] = email_match.group(1).strip()

    resultado["telefone"] = extrair_telefone(texto)

    resultado["novo_cliente"] = "NOVO CLIENTE" in texto

    origem_match = re.search(r"ORIGEM:\s*(.+?)(?:\n|$)", texto)
    if origem_match:
        resultado["origem"] = origem_match.group(1).strip()

    atendente_match = re.search(r"ATENDENTE:\s*(.+?)(?:\n|$)", texto)
    if atendente_match:
        resultado["atendente"] = atendente_match.group(1).strip()

    resultado["endereco"] = parse_endereco(texto)

    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    resultado["items"] = parse_items(linhas)

    total_itens_match = re.search(r"TOTAL ITENS:\s*([\d.,]+)", texto)
    if total_itens_match:
        resultado["total_itens"] = total_itens_match.group(1)

    taxa_match = re.search(r"TAXA DE ENTREGA:\s*\+?\s*([\d.,]+)", texto)
    if taxa_match:
        resultado["taxa_entrega"] = taxa_match.group(1)

    valor_total_match = re.search(r"VALOR\s*DO\s*PEDIDO:\s*(R\$)?\s*([^\n]+)", texto)
    
    if valor_total_match:
        resultado["valor_total"] = valor_total_match.group(2).strip()
    else:
        for linha in reversed(linhas):
            if re.search(r"\d+,\d{2}", linha):
                resultado["valor_total"] = re.search(r"(\d+,\d{2})", linha).group(1) # type: ignore
                break

    payment_match = re.search(r'(?:FORMA\s*DE\s*PAGAMENTO|PAGAMENTO)\s*:\s*([^\n]+)', texto)
    if payment_match:
        raw_payment = ' '.join(payment_match.group(1).split())
        resultado["forma_pagamento"] = extract_clean_payment(raw_payment)
    else:
        resultado["forma_pagamento"] = "Não Especificado"

    tempo_match = re.search(r"TEMPO P/ ENTREGA:\s*(\d+)\s*MIN\s*\|\s*(\d{2}:\d{2}:\d{2})", texto)
    if tempo_match:
        resultado["tempo_entrega"] = f"{tempo_match.group(1)} min | {tempo_match.group(2)}"

    observacoes_match = re.search(r"OBSERVAÇÕES:\s*(.+?)(?:\n|$)", texto)
    if observacoes_match:
        resultado["observacoes"] = observacoes_match.group(1).strip()

    return resultado


import fitz  # PyMuPDF

def extrair_texto_ocr(pdf_bytes: bytes) -> str:
    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_output:
            temp_output_path = temp_output.name

        ocrmypdf.ocr(
            input_file=temp_pdf_path,
            output_file=temp_output_path,
            language='por',
            force_ocr=True,
            rotate_pages=True,
            deskew=True,
            optimize=3,
            skip_text=False,
            clean=True,
            clean_final=True
        )

        texto_final = ""
        with fitz.open(temp_output_path) as doc:
            for page in doc:
                texto_final += page.get_text("text") # type: ignore

        if not texto_final.strip():
            print("[Fallback OCR] Extraindo diretamente com pytesseract...")

            imagens = convert_from_bytes(pdf_bytes, dpi=400)
            custom_config = r'--oem 3 --psm 6 -l por'
            textos = [
                pytesseract.image_to_string(img, config=custom_config)
                for img in imagens
            ]
            texto_final = "\n".join(textos)

        return texto_final

    except Exception as e:
        logger.error(f"Erro no OCR: {e}")
        raise


@app.post("/analisar-pedido/")
async def analisar_pdf(file: UploadFile = File(...)):
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(400, "Only PDF files are accepted")

        contents = await file.read()
        if not contents:
            raise HTTPException(400, "Empty PDF file")

        try:
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: extrair_texto_ocr(contents)),
                timeout=60.0  # Aumentado o tempo limite para 60 segundos
            )
        except asyncio.TimeoutError:
            raise HTTPException(408, "OCR processing timed out")

        data = parse_campos(text)
        if not data:
            raise HTTPException(422, "No valid data extracted")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to process PDF")
        raise HTTPException(500, f"Processing failed: {e}")
    
@app.get("/")
async def root():
    return {"message": "API is running. Use /docs for Swagger UI."}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/verify-tesseract")
async def verify_tesseract_endpoint():
    try:
        langs = pytesseract.get_languages(config='')
        if 'por' not in langs:
            raise RuntimeError("Portuguese language data not found")
        return True
    except Exception as e:
        logger.error(f"Tesseract verification failed: {e}")
        return False

@app.get("/extrair-coordenadas")
def get_coordenadas_route(client, endereco):
    return get_coordenadas(client, endereco)

def gerar_link_google_maps(paradas):
    """
    Gera um link para o Google Maps com as paradas formatadas corretamente.
    """
    paradas_validas = [
        f"{p.latitude},{p.longitude}"
        for p in paradas if p and isinstance(p, Endereco)
    ]
    paradas_formatadas = [urllib.parse.quote_plus(p) for p in paradas_validas] # type: ignore
    return "https://www.google.com/maps/dir/" + "/".join(paradas_formatadas)

def gerar_link_waze(paradas):
    """
    Gera um array de links para o Waze com as paradas formatadas corretamente.
    """
    links = []
    for p in paradas:
        if p and isinstance(p, Endereco):
            latitude = str(p.latitude)  # Converter latitude para string
            longitude = str(p.longitude)  # Converter longitude para string
            links.append(f"https://waze.com/ul?ll={quote_plus(latitude)},{quote_plus(longitude)}&navigate=yes&z=10&to=ll.{quote_plus(latitude)},{quote_plus(longitude)}")
    return links



  
@app.post("/tempo-estimado")
def tempo_estimado(data: TempoEstimadoInput):
    pass
    # try:
    #     num_pizzas = contar_pizzas_no_supabase()
    #     tempo_preparo = max(15, num_pizzas * 2 + 7)

    #     tipo = data.tipo.lower() if data.tipo else None
    #     resultados = {}

    #     if tipo == "retirada":
    #         tempo = tempo_preparo se num_pizzas > 0 else 20
    #         return {
    #             "tipo": "retirada",
    #             "tempo_preparo_min": tempo,
    #             "tempo_total_min": tempo
    #         }

    #     enderecos = buscar_enderecos_para_entrega(data=data)
    #     tempo_entrega_min = 0

    #     if enderecos:
            
    #         coord_pizzaria = get_coordenadas_com_cache(data.pizzaria, data)
    #         if not coord_pizzaria:
    #             raise HTTPException(404, detail="Coordenadas da pizzaria não encontradas")

    #         for endereco in enderecos:
    #             if not coord_cliente:
    #               coord_cliente = get_coordenadas_com_cache(data.pizzaria, data)
    #             if not coord_cliente:
    #                 raise HTTPException(404, detail=f"Coordenadas do cliente {endereco.id} não encontradas")

    #             matrix = client.distance_matrix(
    #                 locations=[coord_pizzaria, coord_cliente],
    #                 profile='driving-car',
    #                 metrics=['duration'],
    #                 units='km'
    #             )
    #             duracao = matrix['durations'][0][1] / 60 + matrix['durations'][1][0] / 60 + 5
    #             tempo_entrega_min += duracao

    #     tempo_entrega_total = (
    #         round(tempo_preparo + tempo_entrega_min, 1)
    #         se num_pizzas > 0 else 40
    #     )

    #     se tipo == "entrega":
    #         return {
    #             "tipo": "entrega",
    #             "tempo_preparo_min": tempo_preparo se num_pizzas > 0 else 0,
    #             "tempo_entrega_min": round(tempo_entrega_min, 1) se num_pizzas > 0 else 40,
    #             "tempo_total_min": tempo_entrega_total
    #         }

    #     # Se tipo não foi enviado, retorna os dois
    #     resultados["retirada"] = {
    #         "tempo_preparo_min": tempo_preparo se num_pizzas > 0 else 20,
    #         "tempo_total_min": tempo_preparo se num_pizzas > 0 else 20
    #     }

    #     resultados["entrega"] = {
    #         "tempo_preparo_min": tempo_preparo se num_pizzas > 0 else 0,
    #         "tempo_entrega_min": round(tempo_entrega_min, 1) se num_pizzas > 0 else 40,
    #         "tempo_total_min": tempo_entrega_total
    #     }

    #     return resultados

    # except Exception as e:
    #     import traceback
    #     traceback.print_exc()
    #     raise HTTPException(500, detail=f"Erro interno: {str(e)}")



# Atualização completa da rota /roterizacao: distribuir entre vários usuario_uids

# Atualização completa da rota /roterizacao: distribuir entre vários usuario_uids
def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False

  
@app.post("/roterizacao")
def roterizacao(data: RoterizacaoInput):
    print(f"Dados recebidos: {data}")
    try:
        # Verificar se os dados estão no formato correto
        if not isinstance(data, RoterizacaoInput):
            raise HTTPException(400, "Dados de entrada inválidos")
        if not data.api_key:
            raise HTTPException(400, "API key não fornecida")
        if not data.usuario_uids or len(data.usuario_uids) == 0:
            raise HTTPException(400, "Nenhum motoboy fornecido")  
        if not data.pizzaria:
            raise HTTPException(400, "Informe o endereço da pizzaria")  

        task = reatribuir_entregas_para_motoboy_ocioso.delay(
          api_key=data.api_key,
            pizzaria=data.pizzaria,
            capacidade_maxima=data.capacidade_maxima
        )
        return {"task_id": task.id}
    except Exception as e:
        print(f"Erro ao processar roteirização: {e}")
        logger.error(f"Erro ao processar roteirização: {e}")
        return {"error": str(e)}

@app.post("/roterizacao/inicio_entrega/{motoboy_uid}")
def iniciar_entrega(motoboy_uid: str):
    if not motoboy_uid:
        raise HTTPException(status_code=400, detail="Motoboy UID não enviado")

    supabase.table("routes").update({"started": True, "in_progress": True}) \
        .eq("motoboy_uid", motoboy_uid).execute()

    return {"status": "ok", "message": "Entrega iniciada com sucesso"}

@app.post("/roterizacao/finalizar_entrega/{motoboy_uid}")
def finalizar_entrega(motoboy_uid: str):
    if not motoboy_uid:
        raise HTTPException(status_code=400, detail="Motoboy UID não enviado")

    supabase.table("routes").delete().eq("motoboy_uid", motoboy_uid).eq("in_progress", True).execute()

    return {"status": "ok", "message": "Entrega finalizada com sucesso"}
  
@app.get("/roterizacao/status/{task_id}")
def verificar_status(task_id: str):
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "PENDING":
        return {"status": "PENDING"}
    elif result.state == "SUCCESS":
        return {"status": "SUCCESS", "result": result.result}
    elif result.state == "FAILURE":
        return {"status": "FAILURE", "error": str(result.result)}
    else:
        return {"status": result.state}
      
@app.get("/roterizacao/entregas")
def listar_entregas():
    entregas = supabase.table("routes").select("*").execute().data
    return {"entregas": entregas}

@app.post("/checkin")
def checkin(motoboy_uid: str):
    if not motoboy_uid:
        raise HTTPException(status_code=400, detail="Motoboy UID não enviado")

    supabase.table("motoboy_checkins").insert({
        "motoboy_uid": motoboy_uid,
        "checkin_time": datetime.now(timezone.utc).isoformat()
    }).execute()

    return {"status": "ok", "message": "Check-in realizado com sucesso"}

@app.patch("/pedido_entregue/{order_id}")
def marcar_entrega_concluida(order_id: int):
    # Marca a entrega como entregue
    supabase.table("route_deliveries").update({"entregue": True}) \
        .eq("order_id", order_id).execute()

    # Atualiza status do pedido
    supabase.table("orders").update({"status": "Entregue"}) \
        .eq("id", order_id).execute()

    print(f"✅ Pedido {order_id} marcado como entregue")
    return {"status": "ok", "message": "Entrega marcada como concluída"}
@app.post("/upload-planilha/")
async def upload_planilha_excel(file: UploadFile = File(...)):
    if not file.filename == None and file.filename.endswith(".xlsx"):
        return JSONResponse(status_code=400, content={"error": "Arquivo deve ser .xlsx"})

    contents = await file.read()
    df = pd.read_excel(BytesIO(contents))
    print(df.columns)  # Isso vai mostrar as colunas reais no terminal

    created_variations = {}
    inserted_products = []

    for _, row in df.iterrows():
        nome = row["Nome"]
        subcategoria = row["Subcategoria"] if pd.notnull(row["Subcategoria"]) else nome.split()[0]
        tamanhos = {
            "Pequena": row.get("Pizza Pequena"),
            "Grande": row.get("Pizza Grande"),
            "Gigante": row.get("Pizza Gigante")
        }

        for tamanho, preco in tamanhos.items():
            if pd.isnull(preco):
                continue

            key = f"{subcategoria}_{tamanho}"
            if key not in created_variations:
                # Verifica se a variation já existe na tabela
                existing = supabase.table("variations").select("*").eq("category", subcategoria).eq("size", tamanho).execute()
                if existing.data:
                    id_variation = existing.data[0]["id"]
                else:
                    variation = {
                        "category": subcategoria,
                        "size": tamanho,
                        "limit_items": 0,
                        "business": 1
                    }
                    insert_response = supabase.table("variations").insert(variation).execute()
                    id_variation = insert_response.data[0]["id"]

                created_variations[key] = id_variation

            # Insere o produto
            product = {
                "name": nome,
                "price": float(preco),
                "id_variation": created_variations[key]
            }

            supabase.table("products").insert(product).execute()
            inserted_products.append(product)

    return {"message": "Produtos inseridos com sucesso!", "total": len(inserted_products)}

@app.post("/upload/")
async def upload_planilha(file: UploadFile = File(...)):
    if not file.filename == None and file.filename.endswith(".xlsx"):
        return JSONResponse(status_code=400, content={"error": "Arquivo deve ser .xlsx"})

    contents = await file.read()
    df = pd.read_excel(BytesIO(contents))
    print(df.columns)  # Isso vai mostrar as colunas reais no terminal

    created_variations = {}
    inserted_products = []

    # Buscar nomes de produtos já cadastrados
    try:
        response = supabase.table("products").select("name").execute()
        nomes_cadastrados = {item["name"] for item in response.data}
    except Exception as e:
        return {"erro": f"Erro ao buscar produtos: {str(e)}"}

    produtos_importados = []
    

    for _, row in df.iterrows():
        nome_produto = str(row["Nome"]).strip()

        print(f"Processando produto: {nome_produto}")
      
        # Ignorar produtos já cadastrados
        if nome_produto in nomes_cadastrados:
            continue

        subcategoria = row["Subcategoria"] if pd.notnull(row["Subcategoria"]) else nome_produto.split()[0]
        preco = float(row["Preço"]) if pd.notnull(row["Preço"]) else 0.0

        # Criar a variação se ainda não existir
        if subcategoria not in created_variations:
            # Verifica se a variação já existe na tabela
            existing = supabase.table("variations").select("*").eq("category", subcategoria).eq("size", "UNICO").execute()
            if existing.data:
                id_variation = existing.data[0]["id"]
            else:
                try:
                    variation_data = {
                        "category": subcategoria,
                        "size": "UNICO",
                        "limit_items": 0,
                        "business": 1,
                    }
                    variation_response = supabase.table("variations").insert(variation_data).execute()
                    id_variation = variation_response.data[0]["id"]
                except Exception as e:
                    print(f"Erro ao inserir variação para {nome_produto}: {str(e)}")
                    continue

            # Adicionar a variação ao dicionário
            created_variations[subcategoria] = id_variation

        # Recuperar o ID da variação
        id_variation = created_variations.get(subcategoria)

        # Criar o produto
        product_data = {
            "name": nome_produto,
            "id_variation": id_variation,
            "price": preco,
        }

        try:
            product_response = supabase.table("products").insert(product_data).execute()
            if product_response.error: # type: ignore
                print(f"Erro ao inserir produto {nome_produto}: {product_response.error.message}") # type: ignore
                continue
        except Exception as e:
            print(f"Erro ao inserir produto {nome_produto}: {str(e)}")
            continue

        produtos_importados.append(product_data)

    return {
        "importados": produtos_importados,
        "ignorados": list(nomes_cadastrados)
    }

@app.on_event("startup")
def start_realtime_on_startup():
    threading.Thread(target=start_realtime, daemon=True).start()

import sys
import traceback

def excepthook(type, value, tb):
    print("".join(traceback.format_exception(type, value, tb)), file=sys.stderr)
sys.excepthook = excepthook