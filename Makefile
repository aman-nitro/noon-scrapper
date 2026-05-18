build:
	docker compose build

build-nocache:
	docker compose build --no-cache

up:
	docker compose up -d

run:
	docker compose up

logs:
	docker compose logs -f
