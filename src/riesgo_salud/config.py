"""Lectura de la configuración y manejo de rutas."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).resolve().parents[2]
CONFIG_POR_DEFECTO = RAIZ_REPO / "config" / "config.yaml"


def cargar_config(ruta: str | Path | None = None) -> dict:
    """Lee el YAML de configuración.

    La variable de entorno RIESGO_BASE_DIR cambia la carpeta base (por ejemplo, una carpeta de
    Google Drive en Colab o una carpeta temporal en las pruebas).
    """
    ruta = Path(ruta) if ruta else CONFIG_POR_DEFECTO
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg = copy.deepcopy(cfg)
    base = os.environ.get("RIESGO_BASE_DIR", cfg["rutas"]["base"])
    base = Path(base)
    if not base.is_absolute():
        # Relativa a la RAÍZ DEL REPO, no a la carpeta desde donde se ejecuta: así un notebook
        # abierto en notebooks/ y la terminal en la raíz escriben en el mismo data/ y resultados/.
        base = (RAIZ_REPO / base).resolve()
    cfg["rutas"]["base"] = str(base)
    return cfg


def ruta(cfg: dict, clave: str, *partes: str, crear: bool = True) -> Path:
    """Devuelve una ruta dentro de la carpeta base, por ejemplo ruta(cfg, 'raw', '2026-10-25')."""
    p = Path(cfg["rutas"]["base"]) / cfg["rutas"][clave]
    for parte in partes:
        p = p / parte
    if crear:
        p.mkdir(parents=True, exist_ok=True)
    return p


def ultimo_corte(cfg: dict) -> str | None:
    """Fecha (AAAA-MM-DD) del corte más reciente guardado en data/raw/, o None si no hay ninguno."""
    carpeta = ruta(cfg, "raw", crear=False)
    if not carpeta.exists():
        return None
    cortes = sorted(p.name for p in carpeta.glob("????-??-??") if p.is_dir())
    return cortes[-1] if cortes else None
