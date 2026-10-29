import copy

import pytest

from riesgo_salud import features, limpieza, sintetico
from riesgo_salud.config import cargar_config


@pytest.fixture(scope="session")
def cfg():
    c = cargar_config()
    c["validacion"].update({"min_afiliados_total": 0, "min_municipios": 50})
    c["clustering"].update({"valores_k": [3, 4], "n_bootstrap": 3})
    c["indice"]["sensibilidad"]["simulaciones"] = 50
    return c


@pytest.fixture(scope="session")
def raw():
    return sintetico.generar_raw(200, semilla=7)


@pytest.fixture(scope="session")
def preparado(raw, cfg):
    div = limpieza.preparar_divipola(raw["divipola"])
    eps, demo, cruce = limpieza.limpiar_bdua(raw, div, cfg["eps_intervenidas"]["lista"])
    reps, info = limpieza.limpiar_reps(raw, div)
    tabla = features.construir_tabla_municipal(eps, reps, div)
    return {"div": div, "eps": eps, "demo": demo, "cruce": cruce, "reps": reps, "info": info, "tabla": tabla}


@pytest.fixture
def cfg_copia(cfg):
    return copy.deepcopy(cfg)
