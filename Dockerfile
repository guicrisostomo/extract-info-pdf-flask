# Etapa 1: Imagem base com Python 3.11
FROM python:3.11-slim

# Etapa 2: Instala pacotes do sistema necessários
RUN apt-get update && apt-get install -y \
    pngquant \
    unpaper \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-por \
    ghostscript \
    unpaper \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    build-essential \
    libpoppler-cpp-dev \
    gcc \
    libpq-dev \
    curl \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Etapa 3: Cria diretório de trabalho
WORKDIR /app

# Etapa 4: Copia os arquivos
COPY . .

# Etapa 5: Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /var/log/supervisor

# Etapa 7: Comando de execução
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]