#!/bin/bash

set -e

cd "$(dirname "$0")/.."

echo "Modelos instalados no Ollama:"
docker compose exec ollama ollama list || {
  echo "Container do Ollama não está rodando."
  echo "Suba com: docker compose up -d ollama"
  exit 1
}

echo ""
read -p "Digite o nome do modelo para deletar: " MODEL_NAME

if [ -z "$MODEL_NAME" ]; then
  echo "Nome do modelo não pode ser vazio."
  exit 1
fi

echo ""
echo "Você tem certeza que quer deletar o modelo '$MODEL_NAME'?"
read -p "Digite 'sim' para confirmar: " CONFIRM

if [ "$CONFIRM" != "sim" ]; then
  echo "Operação cancelada."
  exit 0
fi

echo "Deletando modelo: $MODEL_NAME"
docker compose exec ollama ollama rm "$MODEL_NAME"

echo ""
echo "Modelo deletado com sucesso."
echo "Modelos restantes:"
docker compose exec ollama ollama list