"""El sitio del dashboard se arma con los cortes de resultados/ y sin el modelo .pkl."""

import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _modulo():
    spec = importlib.util.spec_from_file_location("construir", RAIZ / "dashboard" / "construir.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_construir_sitio(tmp_path):
    salida = tmp_path / "_site"
    cortes = _modulo().construir(salida)

    assert (salida / "index.html").exists()
    assert (salida / "app.js").exists()
    assert '"app.js?v=' in (salida / "index.html").read_text(encoding="utf-8")
    manifiesto = json.loads((salida / "datos" / "cortes.json").read_text(encoding="utf-8"))
    fechas = [c["fecha"] for c in manifiesto["cortes"]]
    assert fechas == sorted(fechas, reverse=True)
    assert len(cortes) == len(fechas) >= 1

    ultimo = salida / "datos" / fechas[0]
    assert (ultimo / "municipios_riesgo.csv").exists()
    assert not list(salida.rglob("*.pkl"))
