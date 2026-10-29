import numpy as np
import pandas as pd

from riesgo_salud import indice, modelado, monitoreo


def test_experimentos_y_seleccion(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    res = modelado.experimentos(ti, cfg)
    assert len(res) == len(cfg["clustering"]["algoritmos"]) * len(cfg["clustering"]["valores_k"])
    assert res["silhouette"].between(-1, 1).all()
    elegido = modelado.seleccionar(res, cfg)
    assert elegido["algoritmo"] in cfg["clustering"]["algoritmos"]


def test_modelo_final_ordena_grupos_por_riesgo(preparado, cfg):
    ti = indice.calcular_indice(preparado["tabla"], cfg)
    modelo, grupo, Xs = modelado.ajustar_final(ti, cfg, "kmeans", 4)
    medias = ti.assign(grupo=grupo).groupby("grupo")["indice_riesgo"].mean()
    assert list(medias.index) == [1, 2, 3, 4]
    assert medias.is_monotonic_decreasing  # grupo 1 = mayor riesgo
    assert (modelo.predict(modelado.matriz(ti, cfg)) == grupo.to_numpy()).mean() > 0.9
    perf = modelado.perfiles(ti, grupo, Xs, cfg)
    assert perf["municipios"].sum() == len(ti)


def test_psi():
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(0, 1, 2000))
    assert monitoreo.psi(a, pd.Series(rng.normal(0, 1, 2000))) < 0.05
    assert monitoreo.psi(a, pd.Series(rng.normal(1, 1, 2000))) > 0.25


def test_sin_candidato_que_cumpla_la_regla_no_se_promueve(preparado, cfg_copia):
    ti = indice.calcular_indice(preparado["tabla"], cfg_copia)
    res = modelado.experimentos(ti, cfg_copia)
    assert modelado.seleccionar(res, cfg_copia)["cumple_regla"] in (True, False)
    cfg_copia["clustering"]["min_estabilidad"] = 1.01  # imposible de cumplir
    elegido = modelado.seleccionar(res, cfg_copia)
    assert elegido["cumple_regla"] is False


def test_registro_mlflow_solo_mueve_el_alias_si_cumple(preparado, cfg_copia, tmp_path, monkeypatch):
    import mlflow

    from riesgo_salud.tracking import Tracker

    monkeypatch.setenv("RIESGO_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.chdir(tmp_path)  # MLflow crea ./mlruns para el experimento "Default": que no quede en el repo
    cfg_copia["rutas"]["base"] = str(tmp_path)
    ti = indice.calcular_indice(preparado["tabla"], cfg_copia)
    modelo, _, _ = modelado.ajustar_final(ti, cfg_copia, "kmeans", 3)
    ejemplo = modelado.matriz(ti, cfg_copia).head(5)
    tracker = Tracker(cfg_copia)
    nombre, alias = cfg_copia["mlflow"]["modelo_registrado"], cfg_copia["mlflow"]["alias_produccion"]

    with tracker.run("bueno"):
        v1 = tracker.registrar_modelo(modelo, ejemplo, promover=True)
    with tracker.run("malo"):
        v2 = tracker.registrar_modelo(modelo, ejemplo, promover=False, motivo="prueba")

    cliente = mlflow.MlflowClient()
    assert str(cliente.get_model_version_by_alias(nombre, alias).version) == v1
    assert v2 != v1
    assert cliente.get_model_version(nombre, v2).tags["cumple_regla_seleccion"] == "false"
