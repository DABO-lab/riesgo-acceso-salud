import pandas as pd
import pytest

from riesgo_salud import limpieza, validacion


def test_normalizar_texto():
    assert limpieza.normalizar_texto("NARI¥O") == "NARINO"
    assert limpieza.normalizar_texto("Bogotá, D.C.") == "BOGOTA D C"
    assert limpieza.normalizar_texto("  la paz  robles ") == "LA PAZ ROBLES"


def test_eps_canonica_unifica_codigos_cm():
    assert limpieza.eps_canonica("NUEVA EPS S.A. -CM") == "NUEVA EPS"
    assert limpieza.eps_canonica("EPS SURAMERICANA S.A.") == "SURA"
    assert limpieza.eps_canonica('ALIANZA MEDELLIN ANTIOQUIA EPS S.A.S. "SAVIA SALUD EPS"') == "SAVIA SALUD"
    assert limpieza.eps_canonica("ENTIDAD PROMOTORA DE SALUD SERVICIO OCCIDENTAL DE SALUD S.A.") == "SOS"


def test_zona_simple():
    assert limpieza.zona_simple("Rural - Dispersal") == "RURAL"
    assert limpieza.zona_simple("Urbana-Cabecera Municipal") == "URBANA"


def test_homologacion_casos_conocidos():
    div = pd.DataFrame(
        {
            "cod_dpto": ["54", "05", "05", "76"],
            "cod_mpio": ["54001", "05664", "05665", "76001"],
            "dpto": ["NORTE DE SANTANDER", "ANTIOQUIA", "ANTIOQUIA", "VALLE DEL CAUCA"],
            "nom_mpio": ["SAN JOSÉ DE CÚCUTA", "SAN PEDRO DE LOS MILAGROS", "SAN PEDRO DE URABÁ", "CALI"],
            "latitud": ["7,9"] * 4,
            "longitud": ["-72,5"] * 4,
            "tipo_municipio": ["Municipio"] * 4,
        }
    )
    div = div.assign(
        dpto_norm=div["dpto"].map(limpieza.normalizar_texto),
        mpio_norm=div["nom_mpio"].map(limpieza.normalizar_texto),
    )
    bdua = pd.DataFrame(
        {
            "dpr_nombre": ["NORTE DE SANTANDER", "ANTIOQUIA", "ANTIOQUIA", "VALLE", "X"],
            "mnc_nombre": ["CUCUTA", "SAN PEDRO", "SAN PEDRO DE URABA", "CALI", "Y"],
        }
    )
    r = limpieza.asignar_divipola(bdua, div)
    assert r["cod_mpio"].tolist()[:4] == ["54001", "05664", "05665", "76001"]
    assert r["estado_cruce"].tolist() == ["manual", "manual", "exacto", "exacto", "sin_cruce"]


def test_todo_municipio_sintetico_cruza(preparado):
    assert set(preparado["cruce"]["estado_cruce"]) <= {"exacto", "manual", "area_no_municipalizada"}


def test_reps_excluye_codigo_inexistente(preparado):
    assert "27086" in preparado["info"]["sedes_sin_divipola"]
    assert preparado["reps"]["cod_mpio"].isin(preparado["div"]["cod_mpio"]).all()


def test_validacion_detiene_si_falta_eps(preparado, cfg_copia):
    cfg_copia["eps_intervenidas"]["lista"] = ["EPS QUE NO EXISTE"]
    ch = validacion.validar_preparacion(
        preparado["eps"],
        preparado["demo"],
        preparado["reps"],
        preparado["div"],
        preparado["cruce"],
        cfg_copia,
    )
    with pytest.raises(validacion.ErrorCalidad):
        validacion.aplicar(ch)


# --- Controles negativos: datos rotos a propósito deben detener el pipeline -------------------
def _validar(p, cfg, **cambios):
    datos = {"eps": p["eps"], "demo": p["demo"], **cambios}
    ch = validacion.validar_preparacion(datos["eps"], datos["demo"], p["reps"], p["div"], p["cruce"], cfg)
    return {c["chequeo"]: c["ok"] for c in ch}, ch


def test_grupo_de_edad_nuevo_detiene_el_pipeline(preparado, cfg):
    demo = preparado["demo"].copy()
    demo.loc[demo.index[0], "grupo_edad"] = "75 a 80"
    ok, ch = _validar(preparado, cfg, demo=demo)
    assert not ok["grupos_edad_conocidos"]
    with pytest.raises(validacion.ErrorCalidad):
        validacion.aplicar(ch)


def test_vistas_bdua_que_no_cuadran_detienen_el_pipeline(preparado, cfg):
    demo = preparado["demo"].copy()
    demo.loc[demo.index[0], "afiliados"] += 1000
    ok, ch = _validar(preparado, cfg, demo=demo)
    assert not ok["vistas_bdua_consistentes"]
    with pytest.raises(validacion.ErrorCalidad):
        validacion.aplicar(ch)


def test_municipios_sin_cruce_detienen_el_pipeline(preparado, cfg):
    eps = preparado["eps"].copy()
    grandes = eps["afiliados"].nlargest(5).index  # suficiente para pasar el 0,1 % permitido
    eps.loc[grandes, "estado_cruce"] = "sin_cruce"
    ok, ch = _validar(preparado, cfg, eps=eps)
    assert not ok["cruce_divipola"]
    with pytest.raises(validacion.ErrorCalidad):
        validacion.aplicar(ch)


def test_afiliados_negativos_detienen_el_pipeline(preparado, cfg):
    eps = preparado["eps"].copy()
    eps.loc[eps.index[0], "afiliados"] = -5
    ok, _ = _validar(preparado, cfg, eps=eps)
    assert not ok["afiliados_sin_nulos_ni_negativos"]
