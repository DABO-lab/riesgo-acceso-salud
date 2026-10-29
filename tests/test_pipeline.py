"""Prueba de punta a punta: dos cortes sintéticos, el segundo con un cambio fuerte."""

import json

import pandas as pd

from riesgo_salud.config import cargar_config
from riesgo_salud.pipeline import ejecutar, modo_demo


def test_pipeline_dos_cortes_detecta_cambio(tmp_path, monkeypatch):
    monkeypatch.setenv("RIESGO_BASE_DIR", str(tmp_path))
    cfg = modo_demo(cargar_config(), rapido=True)
    r1 = ejecutar(cfg, "2026-09-01", demo=True, usar_mlflow=False, n_demo=150)
    assert r1["monitoreo"].get("sin_referencia")
    r2 = ejecutar(cfg, "2026-10-01", demo=True, usar_mlflow=False, n_demo=150, choque_demo=2.0)
    assert r2["monitoreo"]["psi"]["pct_intervenidas"] > 0.10
    salida = r2["salida"]
    for archivo in [
        "municipios_riesgo.csv",
        "perfiles_grupos.csv",
        "comparacion_modelos.csv",
        "resumen.md",
        "monitoreo.md",
        "calidad.json",
        "modelo.pkl",
        "figuras/01_seleccion_modelo.png",
    ]:
        assert (salida / archivo).exists(), archivo
    t = pd.read_csv(salida / "municipios_riesgo.csv")
    assert {"indice_riesgo", "nivel_riesgo", "grupo", "nombre_grupo"} <= set(t.columns)
    assert all(c["ok"] or not c["critico"] for c in json.loads((salida / "calidad.json").read_text()))
