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

bash:
	docker exec -it noon-scrapper-noon-1 bash

psql: 
	docker exec -it noon-scrapper-noon_pg-1  psql -U postgres
