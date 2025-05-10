import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import Optional, Dict
from datetime import datetime
from pdf2image import convert_from_bytes
import pytesseract
import re
import logging
from models import Endereco
from parse_bebidas import parse_bebidas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

def verify_tesseract():
    try:
        langs = pytesseract.get_languages()
        if 'por' not in langs:
            raise RuntimeError("Portuguese language data not found")
        return True
    except Exception as e:
        logger.error(f"Tesseract verification failed: {str(e)}")
        return False

verify_tesseract()

def extrair_texto_ocr(pdf_bytes: bytes) -> str:
    try:
        imagens = convert_from_bytes(pdf_bytes)
        return "\n".join(pytesseract.image_to_string(img, lang="por") for img in imagens)
    except Exception as e:
        logger.error(f"OCR extraction failed: {str(e)}")
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

def extract_clean_payment(text: str) -> str:
    """
    Extract and standardize payment method from text
    Returns one of: "Cartão De Débito", "Cartão De Crédito", "Dinheiro", "Pix", "Pagar no local"
    """
    # Fixed regex pattern (properly closed parentheses) all in uppercase
    pattern = r'(?i)(?:CART[ÃA]O\s*(?:DE\s*)?(?:D[ÉE]BITO|CRÉDITO)|PIX|DINHEIRO|PAGAR\s*NO\s*LOCAL)'
    
    try:
        match = re.search(pattern, text)
        if match:
            payment = match.group(0).title()
            # Standardize variations
            payment = (payment.replace("Cartao", "Cartão")
                             .replace("Debito", "Débito")
                             .replace("Credito", "Crédito"))
            return payment
    except Exception as e:
        logger.error(f"Payment extraction error: {str(e)}")

    
    return "Não Especificado"

def parse_campos(texto: str) -> Dict:
    texto = texto.upper()
    resultado = {}

    # Sale type and password
    tipo_match = re.search(r"(ENTREGA|RETIRAR|BALCÃO|MESA)\s*(\d{1,5})?", texto)
    if tipo_match:
        resultado["tipo_venda"] = tipo_match.group(1).capitalize()
        if tipo_match.group(2):
            resultado["senha"] = tipo_match.group(2)

    # Date and time
    data_match = re.search(r"(\d{2}/\d{2}/\d{4})\s*ÀS\s*(\d{2}:\d{2}:\d{2})", texto)
    if data_match:
        resultado["data_hora"] = datetime.strptime(
            f"{data_match.group(1)} {data_match.group(2)}", 
            "%d/%m/%Y %H:%M:%S"
        )

    # Customer info
    cliente_match = re.search(r"CLIENTE:\s*(.+?)(?:\n|$)", texto)
    if cliente_match:
        resultado["cliente"] = cliente_match.group(1).strip().title()
    

    email_match = re.search(r"EMAIL:\s*([^\n]+)", texto)
    if email_match:
        resultado["email"] = email_match.group(1).strip()

    # Phone number (improved pattern): TEL: (16) 9-9345-3444
    telefone_match = re.search(r"TEL:\s*([^\n]+)", texto)
    if telefone_match:
        telefone = telefone_match.group(1).strip()
        # Remove non-digit characters
        telefone = re.sub(r'\D', '', telefone)
        resultado["telefone"] = telefone

    # New customer flag
    resultado["novo_cliente"] = "NOVO CLIENTE" in texto

    # Source and attendant
    origem_match = re.search(r"ORIGEM:\s*(.+?)(?:\n|$)", texto)
    if origem_match:
        resultado["origem"] = origem_match.group(1).strip()
    
    atendente_match = re.search(r"ATENDENTE:\s*(.+?)(?:\n|$)", texto)
    if atendente_match:
        resultado["atendente"] = atendente_match.group(1).strip()

    # Address (using the improved function)
    resultado["endereco"] = parse_endereco(texto)

    linhas = [linha.strip() for linha in texto.splitlines()]
    linhas = [linha for linha in linhas if linha]  # Remove linhas vazias

    # Items (using the improved function)
    resultado["lista_bebidas"] = parse_bebidas(texto)
    resultado["tem_bebida"] = len(resultado["lista_bebidas"]) > 0
    logger.info("Texto recebido para parsear bebidas: %s", texto)
    # Totals and payment
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

    payment_match = re.search(
        r'(?:FORMA\s*DE\s*PAGAMENTO|PAGAMENTO)\s*:\s*([^\n]+(?:\s+[^\n]+)*)', 
        texto, 
        re.IGNORECASE
    )
    
    if payment_match:
        raw_payment = ' '.join(payment_match.group(1).split())
        resultado["forma_pagamento"] = extract_clean_payment(raw_payment)
    else:
        resultado["forma_pagamento"] = "Não Especificado"

    # Delivery time
    tempo_match = re.search(r"TEMPO P/ ENTREGA:\s*(\d+)\s*MIN\s*\|\s*(\d{2}:\d{2}:\d{2})", texto)
    if tempo_match:
        resultado["tempo_entrega"] = f"{tempo_match.group(1)} min | {tempo_match.group(2)}"

    # Observations
    observacoes_match = re.search(r"OBSERVAÇÕES:\s*(.+?)(?:\n|$)", texto)
    if observacoes_match:
        resultado["observacoes"] = observacoes_match.group(1).strip()

    

    return resultado

@app.post("/analisar-pedido/")
async def analisar_pdf(file: UploadFile = File(...)):
    try:
        if not file.content_type == "application/pdf":
            raise HTTPException(400, "Only PDF files are accepted")
        
        contents = await file.read()
        if not contents:
            raise HTTPException(400, "Empty PDF file")
        
        # Add OCR processing timeout
        try:
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: extrair_texto_ocr(contents)
                ),
                timeout=30.0
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
        raise HTTPException(500, f"Processing failed: {str(e)}")
    
@app.get("/")
async def root():
    return {"message": "API is running. Use /docs for Swagger UI."}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/verify-tesseract")
async def verify_tesseract_endpoint():
    if verify_tesseract():
        return {"status": "Tesseract is configured correctly"}
    else:
        raise HTTPException(500, "Tesseract configuration error")