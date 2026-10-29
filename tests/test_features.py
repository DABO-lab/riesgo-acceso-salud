import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from salud.data.clean import limpiar_corte
from salud.features import CUADRANTES, clasificar_cuadrante, construir_tabla_municipal, indicadores_demanda


def _bdua_minima(filas):
    """filas: (cod_mpio, eps, intervenida, regimen, zona, afiliados)"""
    return pd.DataFrame(filas, columns=["cod_mpio", "eps", "eps_intervenida", "regimen", "zona", "afiliados"])


def test_hhi_del_ejemplo_de_la_guia():
    # 60 % en una EPS y 40 % en otra -> 60² + 40² = 5.200
    b = _bdua_minima(
        [
            ("05001", "A", True, "SUBSIDIADO", "RURAL", 60),
            ("05001", "B", False, "CONTRIBUTIVO", "URBANA", 40),
        ]
    )
    d = indicadores_demanda(b).iloc[0]
    assert d["hhi"] == pytest.approx(5200)
    assert d["pct_intervenidas"] == pytest.approx(0.6)
    assert d["pct_rural"] == pytest.approx(0.6)
    assert d["eps_principal"] == "A" and d["pct_eps_principal"] == pytest.approx(0.6)
    assert d["n_eps"] == 2


def test_hhi_maximo_con_una_sola_eps():
    b = _bdua_minima([("05001", "A", False, "SUBSIDIADO", "URBANA", 100)])
    assert indicadores_demanda(b).iloc[0]["hhi"] == pytest.approx(10_000)


def test_tabla_municipal_ips_por_10mil(corte):
    limpios = limpiar_corte(corte)
    tabla = construir_tabla_municipal(limpios["divipola"], limpios["bdua_eps"], limpios["reps_ips"])
    assert tabla["cod_mpio"].is_unique
    fila = tabla.set_index("cod_mpio").loc["05001"]
    assert fila["ips_x_10mil"] == pytest.approx(fila["sedes_ips"] / fila["afiliados"] * 10_000)
    # El área no municipalizada no entra; los municipios sin BDUA quedan con NaN
    assert tabla["afiliados"].sum() == limpios["bdua_eps"].dropna(subset=["cod_mpio"])["afiliados"].sum()


def test_clasificar_cuadrante():
    t = pd.DataFrame({"pct_intervenidas": [0.9, 0.9, 0.1, 0.1], "ips_x_10mil": [1.0, 5.0, 1.0, 5.0]})
    assert list(clasificar_cuadrante(t)) == CUADRANTES


def test_municipio_sin_afiliados_queda_sin_cuadrante():
    t = pd.DataFrame({"pct_intervenidas": [0.9, np.nan], "ips_x_10mil": [1.0, np.nan]})
    assert clasificar_cuadrante(t).isna().tolist() == [False, True]


def test_flujo_completo_por_linea_de_comandos(corte, tmp_path):
    """make clean + make features sobre un corte guardado en disco, sin internet."""
    fecha = "2026-10-25"
    carpeta = tmp_path / "raw" / fecha
    carpeta.mkdir(parents=True)
    for nombre, df in corte.items():
        df.to_csv(carpeta / f"{nombre}.csv", index=False)

    env = {**os.environ, "SALUD_DATA_DIR": str(tmp_path)}
    for modulo in ("salud.data.clean", "salud.features"):
        r = subprocess.run([sys.executable, "-m", modulo], env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    tabla = pd.read_parquet(tmp_path / "processed" / f"tabla_municipal_{fecha}.parquet")
    csv = pd.read_csv(tmp_path / "processed" / f"tabla_municipal_{fecha}.csv", dtype={"cod_mpio": str})
    assert len(tabla) == len(csv) == len(corte["divipola"])
    assert np.isclose(tabla["afiliados"].sum(), csv["afiliados"].sum())
