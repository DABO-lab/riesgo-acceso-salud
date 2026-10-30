"""Pruebas del contrato de la API sobre un corte sintético (sin internet ni MLflow)."""

import pytest
from fastapi.testclient import TestClient

from riesgo_salud.api.main import crear_app
from riesgo_salud.config import cargar_config
from riesgo_salud.pipeline import ejecutar, modo_demo


@pytest.fixture(scope="module")
def corte_demo(tmp_path_factory):
    base = tmp_path_factory.mktemp("api")
    mp = pytest.MonkeyPatch()
    mp.setenv("RIESGO_BASE_DIR", str(base))
    r = ejecutar(
        modo_demo(cargar_config(), rapido=True), "2026-01-01", demo=True, usar_mlflow=False, n_demo=150
    )
    yield r
    mp.undo()


@pytest.fixture(scope="module")
def cliente(corte_demo):
    with TestClient(crear_app(corte_demo["salida"].parent)) as c:
        yield c


@pytest.fixture(scope="module")
def un_municipio(corte_demo):
    return corte_demo["tabla"].sort_values("ranking_riesgo").iloc[0]


def indicadores(fila):
    return {
        v: float(fila[v]) for v in ["pct_intervenidas", "hhi", "ips_x_10mil", "pct_rural", "pct_subsidiado"]
    }


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok" and r.json()["corte"] == "2026-01-01"


def test_municipio_existente(cliente, un_municipio):
    r = cliente.get(f"/municipios/{un_municipio['cod_mpio']}")
    assert r.status_code == 200
    assert r.json()["ranking_riesgo"] == 1
    assert r.json()["nivel_riesgo"] == un_municipio["nivel_riesgo"]


@pytest.mark.parametrize("cod, estado", [("99999", 404), ("abc", 422), ("123", 422)])
def test_municipio_invalido_o_inexistente(cliente, cod, estado):
    assert cliente.get(f"/municipios/{cod}").status_code == estado


def test_ranking_ordenado_y_filtrado(cliente):
    r = cliente.get("/municipios", params={"limite": 5}).json()
    rankings = [m["ranking_riesgo"] for m in r["municipios"]]
    assert rankings == sorted(rankings) and len(rankings) == 5
    muy_alto = cliente.get("/municipios", params={"nivel": "muy alto", "limite": 1000}).json()
    assert {m["nivel_riesgo"] for m in muy_alto["municipios"]} == {"Muy alto"}
    assert cliente.get("/municipios", params={"nivel": "crítico"}).status_code == 422


def test_predict_reproduce_el_indice_de_un_municipio_conocido(cliente, un_municipio):
    r = cliente.post("/predict", json=indicadores(un_municipio))
    assert r.status_code == 200
    p = r.json()["prediccion"]
    assert p["indice_riesgo"] == pytest.approx(un_municipio["indice_riesgo"], abs=0.01)
    assert p["nivel_riesgo"] == un_municipio["nivel_riesgo"]
    assert p["grupo"] == un_municipio["grupo"]
    assert set(r.json()["metadata"]) == {"request_id", "corte", "modelo", "latencia_ms"}


def test_predict_menos_dependencia_baja_el_riesgo(cliente, un_municipio):
    base = indicadores(un_municipio)
    alto = cliente.post("/predict", json=base).json()["prediccion"]["indice_riesgo"]
    bajo = cliente.post("/predict", json={**base, "pct_intervenidas": 0.0}).json()["prediccion"][
        "indice_riesgo"
    ]
    assert bajo < alto


@pytest.mark.parametrize(
    "cambio",
    [{"pct_intervenidas": 1.5}, {"hhi": -1}, {"ips_x_10mil": -0.1}, {"pct_rural": "mucho"}],
)
def test_predict_rechaza_entradas_fuera_de_contrato(cliente, un_municipio, cambio):
    assert cliente.post("/predict", json={**indicadores(un_municipio), **cambio}).status_code == 422


def test_predict_falta_un_campo(cliente, un_municipio):
    datos = indicadores(un_municipio)
    datos.pop("hhi")
    assert cliente.post("/predict", json=datos).status_code == 422


def test_predict_batch(cliente, un_municipio):
    base = indicadores(un_municipio)
    r = cliente.post("/predict/batch", json={"municipios": [base, {**base, "pct_intervenidas": 0.0}]})
    assert r.status_code == 200 and len(r.json()["predicciones"]) == 2
    assert cliente.post("/predict/batch", json={"municipios": []}).status_code == 422


def test_pagina_y_documentacion(cliente):
    assert cliente.get("/").status_code == 200
    assert {"/predict", "/predict/batch", "/municipios", "/health"} <= set(
        cliente.get("/openapi.json").json()["paths"]
    )
