#!/bin/bash

# Nome do projeto
PROJETO="famintoos-pdf-api"
PASTA_EXPORT="exportados"

# Cria a pasta de exportação
mkdir -p $PASTA_EXPORT

echo "🔧 1. Buildando as imagens com docker-compose..."
docker-compose build

echo "📦 2. Salvando imagens Docker em arquivos .tar..."

# Lista os serviços do docker-compose
IMAGENS=$(docker-compose config | grep 'image:' | awk '{print $2}')

for IMG in $IMAGENS; do
  NOME_ARQ=$(echo $IMG | tr '/:' '__').tar
  echo "➡️  Exportando $IMG para $PASTA_EXPORT/$NOME_ARQ"
  docker save $IMG -o "$PASTA_EXPORT/$NOME_ARQ"
done

# Adiciona manualmente imagens locais buildadas (sem tag externa)
echo "🔍 3. Exportando imagens buildadas localmente..."

LOCAIS=("famintoos-pdf-api-app" "famintoos-pdf-api-celery" "famintoos-pdf-api-worker")

for IMG in "${LOCAIS[@]}"; do
  if docker image inspect "$IMG" > /dev/null 2>&1; then
    echo "➡️  Exportando $IMG"
    docker save "$IMG" -o "$PASTA_EXPORT/$IMG.tar"
  else
    echo "⚠️  Imagem $IMG não encontrada localmente"
  fi
done

echo "📄  4. Copiando docker-compose.yml para exportação..."
cp docker-compose.yml $PASTA_EXPORT/

echo "🗜️  5. Compactando tudo em $PROJETO.zip..."
zip -r "$PROJETO.zip" $PASTA_EXPORT

echo "✅ Exportação finalizada: $PROJETO.zip criado com sucesso!"
