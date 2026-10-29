# Imagen base: un Linux mínimo que ya trae Python 3.11
FROM python:3.11-slim

# Copiamos el binario de uv desde su imagen oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencias EXACTAS del uv.lock.
# --frozen: falla si el lock no coincide. --no-dev: sin jupyter/ruff/pytest.
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev

# Usuario sin privilegios: el contenedor no corre como root
RUN useradd --create-home app && mkdir -p /app/data && chown -R app /app
USER app

# El flujo completo de la fase 1 (lo mismo que `make data`).
# Monte ./data como volumen para conservar la descarga y los resultados.
CMD ["sh", "-c", "uv run --no-sync python -m salud.data.extract && uv run --no-sync python -m salud.data.clean && uv run --no-sync python -m salud.features"]
