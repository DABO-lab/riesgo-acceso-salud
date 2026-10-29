.PHONY: setup pipeline demo mlflow test lint notebook docker-build docker-run

# Fecha del corte: vacío = hoy. Ejemplo: make pipeline FECHA=2026-10-25
FECHA ?=
ARG_FECHA = $(if $(FECHA),--fecha $(FECHA),)

# Instala las dependencias exactas del uv.lock y activa los hooks de pre-commit
setup:
	uv sync
	uv run pre-commit install

# Pipeline completo con datos reales: extracción -> limpieza -> validaciones -> tabla municipal
# -> índice -> 15 modelos de clustering en MLflow -> monitoreo -> resultados/<fecha>/
pipeline:
	uv run python -m riesgo_salud.pipeline $(ARG_FECHA)

# El mismo pipeline con datos sintéticos (sin internet, en menos de un minuto)
demo:
	uv run python -m riesgo_salud.pipeline --demo --rapido $(ARG_FECHA)

# Interfaz de MLflow en http://127.0.0.1:5001 (queda en primer plano; use otra terminal)
mlflow:
	uv run mlflow ui --backend-store-uri sqlite:///mlflow/mlflow.db --host 127.0.0.1 --port 5001

# Pruebas (no necesitan internet: usan datos sintéticos)
test:
	uv run pytest -q

# Revisa y formatea el código con ruff
lint:
	uv run ruff check . --fix
	uv run ruff format .

# Abre Jupyter para los notebooks narrados (también se pueden abrir en VS Code)
notebook:
	uv run jupyter lab notebooks/

# Construye la imagen Docker del proyecto
docker-build:
	docker build -t riesgo-acceso-salud .

# Corre el pipeline dentro de Docker; datos, resultados y MLflow quedan en las carpetas del repo
docker-run:
	docker run --rm -v "$(CURDIR)/data:/app/data" -v "$(CURDIR)/resultados:/app/resultados" \
		-v "$(CURDIR)/mlflow:/app/mlflow" riesgo-acceso-salud
