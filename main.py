import asyncio
from io import BytesIO
import os
from urllib.parse import quote_plus
import ocrmypdf
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import Optional, Dict
from datetime import datetime

from fastapi.responses import JSONResponse
import openrouteservice
from parse_items import parse_items
from pdf2image import convert_from_bytes
import pytesseract
import re
import logging
import urllib
from models import Endereco, Entrega, RoterizacaoInput, TempoEstimadoInput
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timedelta


load_dotenv()

logging.basicConfig(
    filename="api_logs.txt",  # Nome do arquivo de log
    level=logging.INFO,       # Nível de log
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

def extrair_texto_ocr(pdf_bytes: bytes) -> str:
    try:
        # Salva PDF temporário
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # Aplica OCR com ocrmypdf
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_output_pdf:
            temp_output_path = temp_output_pdf.name

        ocrmypdf.ocr(
            input_file=temp_pdf_path,
            output_file=temp_output_path,
            language='por',
            force_ocr=True,
            deskew=True,
            rotate_pages=True,
            optimize=3
        )

        # Extração textual via PyMuPDF (mais confiável que OCR visual quando possível)
        texto_total = ""
        with fitz.open(temp_output_path) as doc:
            for page in doc:
                texto_total += page.get_text()

        if not texto_total.strip():
            raise RuntimeError("Texto OCR vazio")

        return texto_total

    except Exception as e:
        logger.error(f"Falha na extração OCR: {e}")
        raise


def parse_endereco(texto: str) -> Optional[Endereco]:
    # Improved address parsing with multiple patterns
    padrao_endereco = re.compile(
        r"ENDEREÇO:\s*(.*?)\s*"  # Street
        r"(\d+)[,\s]*"            # Number
        r"([^,]+?)\s*,\s*"        # Neighborhood
        r"([^/]+?)\s*/\s*"        # City
        r"([A-Z]{2})"             # State
        r"(?:\s*-\s*(.*))?",      # Optional complement
        re.IGNORECASE | re.DOTALL
    )
    
    match = padrao_endereco.search(texto)
    if not match:
        return None
        
    return Endereco(
        rua=match.group(1).strip(),
        numero=match.group(2).strip(),
        bairro=match.group(3).strip(),
        cidade=match.group(4).strip(),
        estado=match.group(5).strip(),
        complemento=match.group(6).strip() if match.group(6) else None
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

    tipo_match = re.search(r"(ENTREGA|RETIRAR|BALCÃO|MESA)\s*(\d{1,5})?", texto)
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

    valor_total_match = re.search(r"VALOR DO PEDIDO:\s*([\d.,]+)", texto)
    if valor_total_match:
        resultado["valor_total"] = valor_total_match.group(1)
    else:
        for linha in reversed(linhas):
            if re.search(r"\d+,\d{2}", linha):
                resultado["valor_total"] = re.search(r"(\d+,\d{2})", linha).group(1)
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
                texto_final += page.get_text("text")

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
    
def get_coordenadas(client, endereco):
    try:
        # Dividir o endereço em partes
        partes = endereco.split(',')
        street = partes[0].strip() if len(partes) > 0 else ""
        number = partes[1].strip() if len(partes) > 1 else "S/N"  # Valor padrão "S/N" para sem número
        district = partes[2].strip() if len(partes) > 2 else ""  # Valor padrão vazio para distrito

        # Construir o endereço completo para consulta
        endereco_completo = f"{street}, {number}, {district}, Jardinópolis, SP"
        print(f"Consultando coordenadas para: {endereco_completo}")

        # Fazer a consulta de coordenadas
        response = client.pelias_search(text=endereco_completo)
        if response and "features" in response and len(response["features"]) > 0:
            coords = response["features"][0]["geometry"]["coordinates"]
            return coords  # Retorna [longitude, latitude]

        return None
    except Exception as e:
        print(f"Erro ao obter coordenadas para o endereço '{endereco}': {e}")
        return None

def gerar_link_google_maps(paradas):
    # Remove paradas vazias ou inválidas
    paradas_validas = [p for p in paradas if p and isinstance(p, str)]
    paradas_formatadas = [urllib.parse.quote_plus(p) for p in paradas_validas]
    return "https://www.google.com/maps/dir/" + "/".join(paradas_formatadas)

def gerar_link_waze(paradas):
    if not paradas:
        return ""
    destino = quote_plus(paradas[-1])
    waypoints = [quote_plus(p) for p in paradas[:-1]]
    return f"https://waze.com/ul?ll=&navigate=yes&to={destino}&via={'|'.join(waypoints)}"


def contar_pizzas_no_supabase(id_order=None):
    # 1. Buscar todos os itens válidos (com relation_id nulo) dos pedidos com status correto
    query = supabase.table("items") \
        .select("id_product, qtd") \
        .is_("relation_id", None)

    if id_order:
        query = query.eq("id_order", id_order)
    else:
        query = query.in_("id_order", supabase.table("orders")
                          .select("id")
                          .in_("status", ["Pronto para entrega", "Quase pronto"])
                          .execute()
                          .data)

    items_result = query.execute()

    if not items_result.data:
        return 0

    # 2. Coletar todos os id_product usados
    produtos_ativos = {}
    for item in items_result.data:
        id_prod = item["id_product"]
        qtd = item.get("qtd", 1)
        if id_prod:
            produtos_ativos[id_prod] = produtos_ativos.get(id_prod, 0) + qtd

    if not produtos_ativos:
        return 0

    # 3. Verificar se esses produtos são variações do tipo pizza
    variations_result = supabase.table("variations") \
        .select("id, category") \
        .in_("id", list(produtos_ativos.keys())) \
        .execute()

    total_pizzas = 0
    for var in variations_result.data:
        categoria = var.get("category", "").lower()
        if "pizza" in categoria:
            total_pizzas += produtos_ativos.get(var["id"], 0)

    return total_pizzas



def buscar_enderecos_para_entrega():
    orders = supabase.table("orders") \
        .select("id, address, prioritaria, datetime") \
        .in_("status", ["Pronto para entrega", "Quase pronto"]) \
        .execute()
    print(f"Endereços encontrados: {orders.data}")
    address_ids = [o["address"] for o in orders.data if o.get("address")]

    if not address_ids:
        return []

    addresses = supabase.table("address") \
        .select("id, street, number, district") \
        .in_("id", address_ids) \
        .execute()

    entregas = []
    for order in orders.data:
        endereco = next((a for a in addresses.data if a["id"] == order["address"]), None)
        if not endereco:
            continue

        order_datetime = datetime.fromisoformat(order["datetime"]) if order.get("datetime") else datetime.now()

        entregas.append(Endereco(
            rua=endereco["street"],
            numero=str(endereco["number"]),
            bairro=endereco["district"],
            cidade="Jardinópolis",
            estado="SP",
            quantidade_pizzas=contar_pizzas_no_supabase(id_order=order["id"]),
            prioridade=order.get("prioritaria", 1),
            datetime=order_datetime  # Agora é um objeto datetime
        ))

    # Ordenar entregas: prioritaria=True primeiro, depois por datetime (mais antigo primeiro)
    entregas.sort(key=lambda x: (x.prioridade, x.datetime) if hasattr(x, 'prioridade') else (1, datetime.max))
    return entregas
  
@app.post("/tempo-estimado")
def tempo_estimado(data: TempoEstimadoInput):
    try:
        num_pizzas = contar_pizzas_no_supabase()
        tempo_preparo = max(15, num_pizzas * 2 + 7)

        tipo = data.tipo.lower() if data.tipo else None
        resultados = {}

        if tipo == "retirada":
            tempo = tempo_preparo if num_pizzas > 0 else 20
            return {
                "tipo": "retirada",
                "tempo_preparo_min": tempo,
                "tempo_total_min": tempo
            }

        enderecos = buscar_enderecos_para_entrega()
        tempo_entrega_min = 0

        if enderecos:
            client = openrouteservice.Client(key=data.api_key, timeout=120)
            coord_pizzaria = get_coordenadas(client, data.pizzaria)
            if not coord_pizzaria:
                raise HTTPException(404, detail="Coordenadas da pizzaria não encontradas")

            for endereco in enderecos:
                coord_cliente = get_coordenadas(client, endereco)
                if not coord_cliente:
                    continue

                matrix = client.distance_matrix(
                    locations=[coord_pizzaria, coord_cliente],
                    profile='driving-car',
                    metrics=['duration'],
                    units='km'
                )
                duracao = matrix['durations'][0][1] / 60 + matrix['durations'][1][0] / 60 + 5
                tempo_entrega_min += duracao

        tempo_entrega_total = (
            round(tempo_preparo + tempo_entrega_min, 1)
            if num_pizzas > 0 else 40
        )

        if tipo == "entrega":
            return {
                "tipo": "entrega",
                "tempo_preparo_min": tempo_preparo if num_pizzas > 0 else 0,
                "tempo_entrega_min": round(tempo_entrega_min, 1) if num_pizzas > 0 else 40,
                "tempo_total_min": tempo_entrega_total
            }

        # Se tipo não foi enviado, retorna os dois
        resultados["retirada"] = {
            "tempo_preparo_min": tempo_preparo if num_pizzas > 0 else 20,
            "tempo_total_min": tempo_preparo if num_pizzas > 0 else 20
        }

        resultados["entrega"] = {
            "tempo_preparo_min": tempo_preparo if num_pizzas > 0 else 0,
            "tempo_entrega_min": round(tempo_entrega_min, 1) if num_pizzas > 0 else 40,
            "tempo_total_min": tempo_entrega_total
        }

        return resultados

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=f"Erro interno: {str(e)}")



# Atualização completa da rota /roterizacao: distribuir entre vários usuario_uids

# Atualização completa da rota /roterizacao: distribuir entre vários usuario_uids

@app.post("/roterizacao")
def roterizacao(data: RoterizacaoInput):
    try:
        client = openrouteservice.Client(key=data.api_key, timeout=(10, 60))

        coord_pizzaria = get_coordenadas(client, data.pizzaria)
        if not coord_pizzaria or len(coord_pizzaria) != 2:
            raise HTTPException(404, detail="Coordenadas da pizzaria inválidas ou não encontradas")

        entregas_restantes = buscar_enderecos_para_entrega()
        if not entregas_restantes:
            return {"viagens": [], "tempo_total_min": 0}
        jobs = []
        total_pizzas = 0
        from datetime import datetime

        # Recarregar prioridades a partir da tabela 'orders'
        alerta_pedidos_vencidos = []
        tempo_limite_segundos = 30 * 60  # 30 minutos

        cache_orders = {}
        for entrega in entregas_restantes:
            address = getattr(entrega, 'address', None)
            if address in cache_orders:
                order = cache_orders[address]
            else:
                if not address:
                    continue
                order = {
                    "prioritaria": entrega.prioridade,
                    "datetime": entrega.datetime,
                    "address": address
                }
                cache_orders[address] = order

            if order:
                if order["prioritaria"]:
                    entrega.prioridade = 0
                else:
                    tempo_espera = (datetime.now() - datetime.fromisoformat(order["datetime"])).total_seconds()
                    entrega.prioridade = int(tempo_espera)
                    if tempo_espera > tempo_limite_segundos:
                        alerta_pedidos_vencidos.append({
                            "address": address,
                            "tempo_espera_min": round(tempo_espera / 60, 1)
                        })
            else:
                entrega.prioridade = 999

        entregas_restantes.sort(key=lambda x: x.prioridade)
        for idx, entrega in enumerate(entregas_restantes):
            endereco = entrega.endereco_completo
            coord = get_coordenadas(client, endereco)
            if not coord or len(coord) != 2:
                continue

            query_address = supabase.table("address").select("id").eq("street", entrega.rua).eq("number", entrega.numero).eq("district", entrega.bairro).execute()
            if not query_address.data:
                continue

            jobs.append({
                "id": idx + 1,
                "location": [float(coord[0]), float(coord[1])],
                "amount": [entrega.quantidade_pizzas],
                "service": 300,
                "priority": getattr(entrega, 'prioridade', 999)
            })
            total_pizzas += entrega.quantidade_pizzas

        if not jobs:
            return {"viagens": [], "tempo_total_min": 0}

        vehicles = []
        for idx, uid in enumerate(data.usuario_uids):
            vehicles.append({
                "id": idx + 1,
                "start": [float(coord_pizzaria[0]), float(coord_pizzaria[1])],
                "end": [float(coord_pizzaria[0]), float(coord_pizzaria[1])],
                "capacity": [999],
                "time_window": [0, 28800],
                "profile": "driving-car"
            })

        result = client.request(
            "/optimization",
            post_json={
                "jobs": jobs,
                "vehicles": vehicles,
                "profile": "driving-car"
            }
        )

        viagens = []
        for rota in result['routes']:
            entregador_idx = rota['vehicle'] - 1
            if entregador_idx >= len(data.usuario_uids):
                continue
            entregador_uid = data.usuario_uids[entregador_idx]

            steps = rota.get('steps', [])
            rotas_veiculo = []
            for step in steps:
                if step['type'] == 'job':
                    entrega = entregas_restantes[step['job'] - 1]
                    rotas_veiculo.append(entrega.endereco_completo)

            viagens.append({
                "entregador": entregador_uid,
                "tempo_estimado_min": round(rota['duration'] / 60, 1),
                "distancia_km": round(rota.get('distance', 0) / 1000, 2),
                "entregas": rotas_veiculo,
                "link_google_maps": gerar_link_google_maps([data.pizzaria] + rotas_veiculo + [data.pizzaria]),
                "link_waze": gerar_link_waze([data.pizzaria] + rotas_veiculo + [data.pizzaria]),
                "tempo_estimado": str(timedelta(seconds=rota['duration'])),
            })

        tempo_total_min = sum([v["tempo_estimado_min"] for v in viagens])

        # Notificar sobre pedidos vencidos (pode ser adaptado para envio real)
        for alerta in alerta_pedidos_vencidos:
            print(f"⚠️ Pedido atrasado! Endereço ID {alerta['address']} está esperando há {alerta['tempo_espera_min']} minutos.")

        return {
            "viagens": viagens,
            "alertas_pedidos_vencidos": alerta_pedidos_vencidos,
            "tempo_total_min": round(tempo_total_min, 1)
        }

    except openrouteservice.exceptions.ApiError as api_err:
        raise HTTPException(status_code=400, detail=f"Erro na API ORS: {str(api_err)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")



@app.post("/upload-planilha/")
async def upload_planilha(file: UploadFile = File(...)):
    if not file.filename.endswith(".xlsx"):
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
    if not file.filename.endswith(".xlsx"):
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
            if product_response.error:
                print(f"Erro ao inserir produto {nome_produto}: {product_response.error.message}")
                continue
        except Exception as e:
            print(f"Erro ao inserir produto {nome_produto}: {str(e)}")
            continue

        produtos_importados.append(product_data)

    return {
        "importados": produtos_importados,
        "ignorados": list(nomes_cadastrados)
    }
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0",
        port=8001,
        log_level="info",
        reload=False  # Desative o reload se necessário
    )