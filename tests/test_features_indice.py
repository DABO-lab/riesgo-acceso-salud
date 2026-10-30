import numpy as np
import pandas as pd

from riesgo_salud import features, indice, validacion


def test_hhi_con_ejemplo_a_mano():
    eps = pd.DataFrame(
        {
            "cod_mpio": ["00001"] * 2,
            "eps": ["A", "B"],
            "eps_intervenida": [True, False],
            "afiliados": [60, 40],
            "regimen": ["SUBSIDIADO", "CONTRIBUTIVO"],
            "zona": ["RURAL", "URBANA"],
        }
    )
    reps = pd.DataFrame(
        {"cod_mpio": ["00001"], "codigohabilitacionsede": ["1"], "naturaleza": ["PUBLICA"], "es_ese": [True]}
    )
    div = pd.DataFrame(
        {
            "cod_mpio": ["00001"],
            "cod_dpto": ["00"],
            "dpto": ["D"],
            "nom_mpio": ["M"],
            "tipo_municipio": ["Municipio"],
            "latitud": [1.0],
            "longitud": [1.0],
        }
    )
    t = features.construir_tabla_municipal(eps, reps, div).iloc[0]
    assert np.isclose(t["hhi"], 5200)  # 60² + 40²
    assert np.isclose(t["pct_intervenidas"], 0.6)
    assert np.isclose(t["ips_x_10mil"], 1 / 100 * 10000)
    assert t["eps_principal"] == "A"


def test_tabla_municipal_valida(preparado):
    total = preparado["eps"].loc[preparado["eps"]["cod_mpio"].notna(), "afiliados"].sum()
    validacion.aplicar(validacion.validar_tabla_municipal(preparado["tabla"], total))


def test_indice_en_rango_y_orientado(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    assert ti["indice_riesgo"].between(0, 100).all()
    # a más dependencia de intervenidas, más índice (en promedio)
    assert ti["indice_riesgo"].corr(ti["pct_intervenidas"], method="spearman") > 0
    # a más oferta de IPS, menos índice (en promedio)
    assert ti["indice_riesgo"].corr(ti["ips_x_10mil"], method="spearman") < 0


def test_niveles_respetan_cuantiles(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    prop = ti["nivel_riesgo"].value_counts(normalize=True)
    assert abs(prop["Muy alto"] - 0.10) < 0.03
    assert abs(prop["Bajo"] - 0.30) < 0.03


def test_sensibilidad_y_pca(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    m, prob = indice.sensibilidad(ti, cfg)
    assert 0.5 < m["sens_spearman_mediana"] <= 1
    assert prob.between(0, 1).all()
    r = indice.comparar_con_pca(ti, cfg)
    assert np.isclose(sum(r["pesos_pca"].values()), 1, atol=0.01)


def test_clasificar_cuadrante_exploratorio():
    t = pd.DataFrame(
        {"pct_intervenidas": [0.9, 0.9, 0.1, 0.1, np.nan], "ips_x_10mil": [1.0, 5.0, 1.0, 5.0, np.nan]}
    )
    c = features.clasificar_cuadrante(t)
    assert list(c[:4]) == features.CUADRANTES
    assert pd.isna(c.iloc[4])


def test_estimar_indice_reproduce_el_indice_del_corte(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    est = indice.estimar_indice(ti, ti, cfg)
    assert np.allclose(est["indice_riesgo"], ti["indice_riesgo"])
    assert (est["nivel_riesgo"] == ti["nivel_riesgo"].astype(str)).all()
