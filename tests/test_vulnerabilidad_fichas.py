"""Cruce con vulnerabilidad, fichas y validación de la IA, sin internet."""

import io
import json

import numpy as np
import pandas as pd
import pytest

from riesgo_salud import fichas, validar_ia, vulnerabilidad


def _municipios(n=200, semilla=3):
    rng = np.random.default_rng(semilla)
    ipm = rng.uniform(5, 90, n)
    indice = np.clip(ipm * 0.8 + rng.normal(0, 8, n), 0, 100)
    nivel = pd.qcut(indice, [0, 0.3, 0.7, 0.9, 1], labels=["Bajo", "Medio", "Alto", "Muy alto"]).astype(str)
    df = pd.DataFrame(
        {
            "cod_mpio": [f"{i:05d}" for i in range(1, n + 1)],
            "nom_mpio": [f"MUNICIPIO {i}" for i in range(1, n + 1)],
            "dpto": ["CAUCA"] * n,
            "indice_riesgo": indice,
            "nivel_riesgo": nivel,
            "ranking_riesgo": pd.Series(indice).rank(ascending=False, method="first").astype(int),
            "nombre_grupo": np.where(indice > 50, "Grupo 1 (mayor riesgo)", "Grupo 3 (menor riesgo)"),
            "grupo": np.where(indice > 50, 1, 3),
            "afiliados": rng.integers(1000, 50000, n),
            "pct_intervenidas": rng.uniform(0, 1, n),
            "eps_principal": "ASMET SALUD",
            "pct_eps_principal": rng.uniform(0.3, 1, n),
            "eps_principal_intervenida": True,
            "n_eps": 3,
            "sedes_ips": 2,
            "ips_x_10mil": rng.uniform(0.5, 5, n),
            "pct_rural": rng.uniform(0, 1, n),
            "pct_subsidiado": rng.uniform(0, 1, n),
            "prob_top10": rng.uniform(0, 1, n),
            **{k: rng.uniform(0, 100, n) for k in fichas.COMPONENTES},
        }
    )
    ref = pd.DataFrame(
        {
            "cod_mpio": df["cod_mpio"],
            "ipm": ipm,
            "ipm_cabecera": ipm * 0.7,
            "ipm_rural": ipm * 1.1,
            "barreras_salud": rng.uniform(0, 20, n),
            "sin_aseguramiento": 10.0,
        }
    )
    pdet = set(df.sort_values("indice_riesgo", ascending=False)["cod_mpio"].head(40))
    return df, ref, pdet


def test_leer_ipm_del_anexo_dane():
    ipm = pd.DataFrame(
        {
            "ID": ["05001", "05002", "Total"],
            "Municipio": ["A", "B", "-"],
            "IPM": [12.8, 40.6, 1],
            "Cabeceras": [12.6, 24.1, 1],
            "IPM Centros poblados y rural disperso": [22.9, 51.4, 1],
        }
    )
    priv = pd.DataFrame(
        [
            ["ID", "Municipio", "Barreras de acceso a servicios de salud", "Sin aseguramiento en salud"],
            ["05001", "A", 2.6, 15.9],
            ["05002", "B", 3.2, 8.8],
            ["05001", "A", 99, 99],
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        ipm.to_excel(w, sheet_name=vulnerabilidad.HOJA_IPM, index=False)
        pd.concat([pd.DataFrame([[None, None, "Privaciones", None]]), priv]).to_excel(
            w, sheet_name=vulnerabilidad.HOJA_PRIVACIONES, index=False, header=False
        )
    df = vulnerabilidad.leer_ipm(buf.getvalue())
    assert list(df["cod_mpio"]) == ["05001", "05002"]
    assert df.loc[0, "ipm"] == 12.8 and df.loc[0, "barreras_salud"] == 2.6  # el duplicado se descarta


def test_evaluar_rubrica(cfg_copia):
    df, ref, pdet = _municipios()
    r = vulnerabilidad.evaluar(df, ref, pdet, cfg_copia)
    h = r["hipotesis"]
    assert set(h) == {"H1_pobreza", "H2_pdet", "H3_barreras_salud", "H4_doble_vulnerabilidad"}
    assert h["H1_pobreza"]["resultado"] == "se_cumple"  # el índice se construyó a partir del IPM
    assert h["H2_pdet"]["resultado"] == "se_cumple"  # los PDET son los de mayor índice
    assert h["H3_barreras_salud"]["resultado"] == "no_se_cumple"  # barreras al azar
    assert all(r["hipotesis"][k]["resultado"] in vulnerabilidad.ETIQUETA for k in h)
    assert r["doble_vulnerabilidad"]["municipios"] > 0
    assert "censo 2018" in vulnerabilidad.respaldo_informe(r)


def test_fichas_con_plantilla(cfg_copia, tmp_path):
    df, ref, pdet = _municipios(50)
    cfg_copia["rutas"]["base"] = str(tmp_path)
    salida = tmp_path / "resultados" / "2026-11-12"
    salida.mkdir(parents=True)
    df.to_csv(salida / "municipios_riesgo.csv", index=False)
    r = fichas.etapa(cfg_copia, "2026-11-12", gemini=None)
    assert r["estado"] == "ok" and len(r["fichas"]) == 5
    f = r["fichas"][0]
    assert f["hechos"]["ranking"] == 1
    assert f["resumen"] and f["por_que"] and f["accion_recomendada"]


def test_validacion_ia(cfg_copia, tmp_path):
    cfg_copia["rutas"]["base"] = str(tmp_path)
    salida = tmp_path / "resultados" / "2026-11-12"
    salida.mkdir(parents=True)
    noticias = [
        {
            "titulo": f"t{i}",
            "fuente": "f",
            "fecha": "2026-11-01",
            "enlace": "https://x",
            "relevante": i % 4 != 0,
            "departamentos": ["CAUCA"] if i % 2 else [],
            "tipo": "medicamentos",
        }
        for i in range(40)
    ]
    (salida / "noticias.json").write_text(json.dumps(noticias), encoding="utf-8")
    m = validar_ia.preparar(cfg_copia, "2026-11-12", n=20)
    assert len(m) == 20 and (m["humano_relevante"] == "").all()
    m["humano_relevante"] = m["ia_relevante"]
    m.loc[0, "humano_relevante"] = "no" if m.loc[0, "ia_relevante"] == "si" else "si"
    m["humano_departamentos"] = m["ia_departamentos"].str.lower()
    m["humano_tipo"] = "medicamentos"
    m.to_excel(salida / validar_ia.MUESTRA, index=False)
    r = validar_ia.evaluar(cfg_copia, "2026-11-12")
    assert r["revisadas"] == 20
    assert r["relevancia"]["acuerdo"] == pytest.approx(0.95)
    assert r["departamentos"]["acuerdo"] == 1.0 and r["tipo"]["acuerdo"] == 1.0
