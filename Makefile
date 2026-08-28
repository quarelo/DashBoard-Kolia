.PHONY: dev dev-detached down logs ps test tests test-backend test-ia test-frontend

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
