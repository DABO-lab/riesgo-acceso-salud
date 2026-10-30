"""El pipeline orquestado con Prefect: estados, reintentos y corte por calidad de datos."""

import pytest
from prefect.testing.utilities import prefect_test_harness

from riesgo_salud import flujo, pipeline, validacion


@pytest.fixture(scope="module", autouse=True)
def prefect_local():
    with prefect_test_harness():
        yield


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("RIESGO_BASE_DIR", str(tmp_path))
    return tmp_path


def test_flow_completo_con_datos_sinteticos(base):
    r = flujo.flujo(fecha="2026-01-01", demo=True, rapido=True, usar_mlflow=False, n_demo=150)
    assert (r["salida"] / "municipios_riesgo.csv").exists()
    assert r["monitoreo"].get("sin_referencia")


def test_extraccion_se_reintenta_ante_fallas_transitorias(base, monkeypatch):
    original, llamadas = pipeline.etapa_extraccion, []

    def falla_dos_veces(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise ConnectionError("datos.gov.co no respondió")
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "etapa_extraccion", falla_dos_veces)
    monkeypatch.setattr(flujo, "t_extraccion", flujo.t_extraccion.with_options(retry_delay_seconds=0))
    flujo.flujo(fecha="2026-01-01", demo=True, rapido=True, usar_mlflow=False, n_demo=150)
    assert len(llamadas) == 3


def test_error_de_calidad_detiene_el_flow_sin_entrenar(base, monkeypatch):
    def datos_rotos(*args, **kwargs):
        raise validacion.ErrorCalidad("Fallaron chequeos críticos: cruce_divipola")

    entrenado = []
    monkeypatch.setattr(pipeline, "etapa_preparacion", datos_rotos)
    monkeypatch.setattr(pipeline, "etapa_modelado", lambda *a, **k: entrenado.append(1))
    estado = flujo.flujo(
        fecha="2026-01-01", demo=True, rapido=True, usar_mlflow=False, n_demo=150, return_state=True
    )
    assert estado.is_failed()
    assert entrenado == []
