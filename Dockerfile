# Imagen base: un Linux mínimo con Python 3.12 (la misma versión de .python-version)
FROM python:3.12-slim

# Copiamos el binario de uv desde su imagen oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencias EXACTAS del uv.lock.
# --frozen: falla si el lock no coincide. --no-dev: sin jupyter/ruff/pytest.
COPY pyproject.toml uv.lock README.md .python-version ./
COPY src/ src/
COPY config/ config/
RUN uv sync --frozen --no-dev

# Usuario sin privilegios: el contenedor no corre como root
RUN useradd --create-home app && mkdir -p data resultados mlflow && chown -R app /app
USER app

# El pipeline completo (lo mismo que `make pipeline`). Monte data/, resultados/ y mlflow/
# como volúmenes para conservar la descarga, los resultados y los experimentos.
CMD ["uv", "run", "--no-sync", "python", "-m", "riesgo_salud.pipeline"]
