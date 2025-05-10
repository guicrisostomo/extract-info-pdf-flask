FROM python:3.11-slim

# 1. Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    tesseract-ocr-eng \
    poppler-utils \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. Manually install tessdata to ensure proper location
RUN mkdir -p /usr/share/tesseract-ocr/tessdata && \
    cd /usr/share/tesseract-ocr/tessdata && \
    wget https://github.com/tesseract-ocr/tessdata/raw/main/por.traineddata && \
    wget https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata && \
    wget https://github.com/tesseract-ocr/tessdata/raw/main/osd.traineddata

# 3. Set environment variables
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/tessdata

# 4. Verify installation
RUN tesseract --list-langs && \
    echo "TESSDATA_PREFIX=$TESSDATA_PREFIX" && \
    ls -la $TESSDATA_PREFIX

# 5. Set working directory
WORKDIR /app

# 6. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy application
COPY . .

# 8. Expose port
EXPOSE 8000

# 9. Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]