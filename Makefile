.PHONY: dev dev-detached down logs ps test tests test-backend test-ia test-frontend reunioes reunioes-plano

dev:
	@docker compose up --build

dev-detached:
	@docker compose up -d --build

down:
	@docker compose down

logs:
	@docker compose logs -f

ps:
	@docker compose ps

test-backend:
	@echo "==> Testando backend"
	@cd backend && python -m compileall -q .

test-ia:
	@echo "==> Testando IA"
	@docker exec dashboard-kolia-ia-service-1 python -m pytest -q tests

test-frontend:
	@echo "==> Testando frontend"
	@cd frontend && npm run lint && npm run build

test: test-backend test-ia test-frontend
	@echo "==> Todos os testes concluídos"

tests: test

# Carga do CSV de reuniões pelo backend, uma análise por vez (backend/scripts/load_dataset.py).
#   make reunioes-plano        só divide e valida o CSV, sem login nem escrita
#   make reunioes LIMIT=5      ensaio: importa tudo e analisa só 5
#   make reunioes              todas; pode interromper e rodar de novo
#   make reunioes CSV=outro.csv
# Login: KOLIA_EMAIL e KOLIA_PASSWORD no .env da raiz, montado só para leitura.
CSV ?= transcricoes_TOTVS.csv
LOAD_DATASET = docker compose run --rm --no-deps \
	-v "$(abspath $(CSV)):/data/reunioes.csv:ro" \
	-v "$(CURDIR)/.env:/run/kolia.env:ro" \
	backend python scripts/load_dataset.py --csv /data/reunioes.csv --backend http://backend:8080

reunioes-plano:
	@test -f "$(CSV)" || { echo "CSV não encontrado: $(CSV)"; exit 1; }
	@test -f .env || { echo "Falta o .env na raiz"; exit 1; }
	@$(LOAD_DATASET) --dry-run

reunioes:
	@test -f "$(CSV)" || { echo "CSV não encontrado: $(CSV)"; exit 1; }
	@test -f .env || { echo "Falta o .env na raiz"; exit 1; }
	@for service in backend ia-service ollama; do \
		test -n "$$(docker compose ps --status running -q $$service)" || \
		{ echo "$$service não está rodando: make dev-detached"; exit 1; }; \
	done
	@$(LOAD_DATASET) $(if $(LIMIT),--limit $(LIMIT))
