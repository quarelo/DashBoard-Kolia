#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "Digite o nome do modelo para instalar no Ollama:"
echo "Exemplos:"
echo "- qwen2.5:3b"
echo "- llama3.2:3b"
echo "- mistral"
echo ""

read -p "Modelo: " MODEL_NAME

if [ -z "$MODEL_NAME" ]; then
  echo "Nome do modelo não pode ser vazio."
  exit 1
fi

echo "Subindo container do Ollama, se necessário..."
docker compose up -d ollama

echo "Instalando modelo: $MODEL_NAME"
docker compose exec ollama ollama pull "$MODEL_NAME"

echo ""
echo "Modelo instalado com sucesso:"
docker compose exec ollama ollama list