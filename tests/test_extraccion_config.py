"""Extracción y configuración, sin internet: se reemplaza requests.get por un portal falso."""

import pandas as pd

from riesgo_salud import config, extraccion


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

    monkeypatch.setattr(extraccion.requests, "get", get_falso)
    df = extraccion.soda_get("https://portal/", "abcd-1234", {}, tamano_pagina=2)
    assert len(df) == 5
    assert pedidos == [0, 2, 4]  # el último lote (1 fila < 2) cierra la paginación


def test_extraer_usa_la_cache_del_corte(monkeypatch, tmp_path, cfg_copia):
    monkeypatch.setenv("RIESGO_BASE_DIR", str(tmp_path))
    cfg = config.cargar_config()
    carpeta = config.ruta(cfg, "raw", "2026-10-25")
    for nombre in extraccion.consultas(cfg):
        pd.DataFrame({"a": ["1"]}).to_csv(carpeta / f"{nombre}.csv", index=False)

    def no_llamar(*args, **kwargs):
        raise AssertionError("No debía conectarse al portal: los archivos ya existían")

    monkeypatch.setattr(extraccion, "soda_get", no_llamar)
    raw = extraccion.extraer(cfg, "2026-10-25")
    assert set(raw) == set(extraccion.consultas(cfg))
    assert (carpeta / "metadatos_corte.json").exists()


def test_leer_raw_acepta_los_nombres_de_la_fase_1(tmp_path):
    for viejo in extraccion.NOMBRES_FASE1.values():
        pd.DataFrame({"a": ["1"]}).to_csv(tmp_path / f"{viejo}.csv", index=False)
    assert set(extraccion.leer_raw(tmp_path)) == set(extraccion.NOMBRES_FASE1)


def test_la_bdua_se_pide_agregada_en_el_servidor(cfg):
    _, params = extraccion.consultas(cfg)["eps_contributivo"]
    assert "sum(cantidad::number) as afiliados" in params["$select"]
    assert params["$group"].startswith("dpr_nombre,mnc_nombre")


def test_el_reps_no_pide_datos_personales(cfg):
    _, params = extraccion.consultas(cfg)["reps_ips"]
    columnas = params["$select"].lower()
    for sensible in ("correo", "email", "telefono", "direccion", "numeroidentificacion"):
        assert sensible not in columnas


def test_ruta_relativa_se_resuelve_desde_la_raiz_del_repo(monkeypatch, tmp_path):
    """Un notebook abierto en notebooks/ debe escribir en el mismo data/ que la terminal."""
    monkeypatch.delenv("RIESGO_BASE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = config.cargar_config()
    assert cfg["rutas"]["base"] == str(config.RAIZ_REPO)


def test_ultimo_corte(monkeypatch, tmp_path):
    monkeypatch.setenv("RIESGO_BASE_DIR", str(tmp_path))
    cfg = config.cargar_config()
    assert config.ultimo_corte(cfg) is None
    for fecha in ("2026-09-30", "2026-10-29"):
        config.ruta(cfg, "raw", fecha)
    assert config.ultimo_corte(cfg) == "2026-10-29"
