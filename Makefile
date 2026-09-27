.PHONY: up down test demo benchmark lint

up:
	docker compose up --build

down:
	docker compose down -v

test:
	python -m pytest -q

demo:
	python scripts/demo_incident.py

benchmark:
	python scripts/benchmark.py

seed:
	python scripts/seed_neo4j.py
	python scripts/seed_qdrant.py
