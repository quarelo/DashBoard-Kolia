#!/bin/sh

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env"}

read_env_value() {
    key=$1
    fallback=$2
    if [ -f "$ENV_FILE" ]; then
        value=$(awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")
    else
        value=""
    fi
    if [ -n "$value" ]; then
        printf '%s\n' "$value"
    else
        printf '%s\n' "$fallback"
    fi
}

update_env_value() {
    key=$1
    value=$2
    env_dir=$(dirname "$ENV_FILE")
    mkdir -p "$env_dir"
    temporary=$(mktemp "$env_dir/.env.XXXXXX")
    if [ -f "$ENV_FILE" ]; then
        awk -F= -v wanted="$key" -v replacement="$value" '
            BEGIN { updated = 0 }
            $1 == wanted { print wanted "=" replacement; updated = 1; next }
            { print }
            END { if (!updated) print wanted "=" replacement }
        ' "$ENV_FILE" > "$temporary"
    else
        printf '%s=%s\n' "$key" "$value" > "$temporary"
    fi
    mv "$temporary" "$ENV_FILE"
}

model_is_installed() {
    wanted=$1
    case "$wanted" in
        *:*) canonical=$wanted ;;
        *) canonical="$wanted:latest" ;;
    esac
    docker compose exec -T ollama ollama list 2>/dev/null |
        awk -v model="$wanted" -v tagged="$canonical" '
            $1 == model || $1 == tagged { found = 1 }
            END { exit !found }
        '
}

ensure_model() {
    env_key=$1
    label=$2
    model=$3

    while ! model_is_installed "$model"; do
        printf '\n%s "%s" não está instalado.\n' "$label" "$model"
        printf '1. Baixar este modelo\n'
        printf '2. Trocar o modelo no arquivo %s\n' "$ENV_FILE"
        printf '3. Cancelar\n'
        printf 'Escolha: '
        read -r choice

        case "$choice" in
            1)
                printf 'Baixando %s...\n' "$model"
                docker compose exec -T ollama ollama pull "$model"
                return 0
                ;;
            2)
                printf 'Novo modelo para %s: ' "$env_key"
                read -r replacement
                if [ -z "$replacement" ]; then
                    printf 'O nome do modelo não pode ser vazio.\n' >&2
                    continue
                fi
                update_env_value "$env_key" "$replacement"
                model=$replacement
                printf '%s atualizado para %s.\n' "$env_key" "$model"
                ;;
            3)
                printf 'Instalação cancelada.\n' >&2
                return 1
                ;;
            *)
                printf 'Opção inválida.\n' >&2
                ;;
        esac
    done

    printf '%s "%s" já está instalado.\n' "$label" "$model"
}

cd "$PROJECT_ROOT"
printf 'Iniciando o Ollama...\n'
docker compose up -d ollama

generation_model=$(read_env_value OLLAMA_MODEL "qwen2.5:3b")
embedding_model=$(read_env_value EMBEDDING_MODEL "nomic-embed-text")

ensure_model OLLAMA_MODEL "Modelo de análise" "$generation_model"
ensure_model EMBEDDING_MODEL "Modelo de embedding" "$embedding_model"

printf '\nModelos necessários estão disponíveis.\n'
docker compose exec -T ollama ollama list
