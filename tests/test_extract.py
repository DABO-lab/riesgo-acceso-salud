"""La extracción se prueba sin internet: se reemplaza requests.get por un portal falso."""

import pandas as pd

from salud.data import extract


class RespuestaFalsa:
    def __init__(self, filas):
        self._filas = filas

    def raise_for_status(self):
        pass

    def json(self):
        return self._filas


def test_soda_get_pagina_hasta_el_ultimo_lote(monkeypatch):
    datos = [{"x": str(i)} for i in range(5)]
    pedidos = []

    def get_falso(url, params, timeout):
        pedidos.append(params["$offset"])
        inicio = params["$offset"]
        return RespuestaFalsa(datos[inicio : inicio + params["$limit"]])

    monkeypatch.setattr(extract.requests, "get", get_falso)
    df = extract.soda_get("abcd-1234", {}, page_size=2)
    assert len(df) == 5
    assert pedidos == [0, 2, 4]  # el último lote (1 fila < 2) cierra la paginación


def test_descargar_usa_la_cache_del_dia(monkeypatch, tmp_path):
    pd.DataFrame({"a": ["1", "2"]}).to_csv(tmp_path / "tabla.csv", index=False)

    def no_llamar(*args, **kwargs):
        raise AssertionError("No debía conectarse al portal: el archivo ya existía")

    monkeypatch.setattr(extract, "soda_get", no_llamar)
    df = extract.descargar("tabla", "abcd-1234", {}, tmp_path)
    assert len(df) == 2


def test_la_bdua_se_pide_agregada_en_el_servidor():
    p = extract.params_agregados(["dpr_nombre", "mnc_nombre"])
    assert p["$group"] == "dpr_nombre,mnc_nombre"
    assert "sum(cantidad::number) as afiliados" in p["$select"]


def test_el_reps_no_pide_datos_personales():
    _, params = extract.consultas()["reps_ips"]
    columnas = params["$select"].lower()
    for sensible in ("correo", "email", "telefono", "direccion", "numeroidentificacion"):
        assert sensible not in columnas
