.PHONY: setup data extract clean features test lint notebook docker-build docker-run

# Instala las dependencias exactas del uv.lock y activa los hooks de pre-commit
setup:
	uv sync
	uv run pre-commit install

# Flujo completo de la fase 1: extraer -> limpiar -> tabla municipal
data: extract clean features

# Descarga las 7 tablas de datos.gov.co a data/raw/<fecha>/ (usa caché si ya existen)
extract:
	uv run python -m salud.data.extract

# Limpia y normaliza el corte más reciente (o el de FECHA_CORTE) -> data/processed/
clean:
	uv run python -m salud.data.clean

# Construye la tabla analítica municipal (una fila por municipio) en parquet y csv
features:
	uv run python -m salud.features

# Corre las pruebas (no necesitan internet: usan datos sintéticos)
test:
	uv run pytest -q

# Revisa y formatea el código con ruff
lint:
	uv run ruff check . --fix
	uv run ruff format .

# Abre Jupyter para los notebooks narrados
notebook:
	uv run jupyter lab notebooks/

# Construye la imagen Docker del proyecto
docker-build:
	docker build -t riesgo-acceso-salud .

# Corre el flujo completo dentro de Docker; los datos quedan en ./data de tu equipo
docker-run:
	docker run --rm -v "$(CURDIR)/data:/app/data" riesgo-acceso-salud
