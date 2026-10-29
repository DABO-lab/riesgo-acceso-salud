import pandas as pd
import pytest

from salud.config import EPS_INTERVENIDAS
from salud.data.clean import (
    ValidacionError,
    asignar_divipola,
    eps_canonica,
    limpiar_corte,
    limpiar_reps,
    normalizar_texto,
    preparar_divipola,
    zona_simple,
)


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("NARI¥O", "NARINO"),
        ("Bogotá, D.C.", "BOGOTA D C"),
        ("  la paz  robles ", "LA PAZ ROBLES"),
        ("San José de Cúcuta", "SAN JOSE DE CUCUTA"),
    ],
)
def test_normalizar_texto(entrada, esperado):
    assert normalizar_texto(entrada) == esperado


def test_normalizar_texto_conserva_nulos():
    assert pd.isna(normalizar_texto(None))


@pytest.mark.parametrize(
    "nombre, canon",
    [
        ("NUEVA EPS S.A.", "NUEVA EPS"),
        ("NUEVA EPS S.A. -CM", "NUEVA EPS"),
        ("EPS SURAMERICANA S.A.", "SURA"),
        ("SERVICIO OCCIDENTAL DE SALUD S.A. - S.O.S.", "SOS"),
        ("ALGUNA EPS NUEVA", "ALGUNA EPS NUEVA"),  # sin regla: nombre normalizado
    ],
)
def test_eps_canonica(nombre, canon):
    assert eps_canonica(nombre) == canon


@pytest.mark.parametrize(
    "zona, esperado",
    [("Urbana-Cabecera Municipal", "URBANA"), ("Rural - Dispersal", "RURAL"), ("", "SIN DATO")],
)
def test_zona_simple(zona, esperado):
    assert zona_simple(zona) == esperado


def test_divipola_rellena_ceros_y_corrige_coma_decimal(corte):
    div = preparar_divipola(corte["divipola"])
    assert "05001" in set(div["cod_mpio"])
    assert div["latitud"].dtype.kind == "f"


def test_asignar_divipola_cubre_los_cuatro_casos(corte):
    div = preparar_divipola(corte["divipola"])
    casos = pd.DataFrame(
        {
            "dpr_nombre": ["NORTE DE SANTANDER", "VALLE", "GUAINIA", "ANTIOQUIA"],
            "mnc_nombre": ["CUCUTA", "CALI", "DPTO. GUAINIA", "MUNICIPIO INVENTADO"],
        }
    )
    r = asignar_divipola(casos, div)
    assert list(r["estado_cruce"]) == ["manual", "exacto", "area_no_municipalizada", "sin_cruce"]
    assert list(r["cod_mpio"][:2]) == ["54001", "76001"]


def test_limpiar_corte_conserva_afiliados_y_marca_intervenidas(corte):
    limpios = limpiar_corte(corte)
    eps = limpios["bdua_eps"]
    total_crudo = sum(pd.to_numeric(corte[k]["afiliados"]).sum() for k in corte if k.startswith("bdua_eps"))
    assert eps["afiliados"].sum() == total_crudo
    assert set(EPS_INTERVENIDAS) <= set(eps["eps"])
    assert eps.loc[eps["eps"] == "SURA", "eps_intervenida"].eq(False).all()
    assert set(eps["zona"]) <= {"URBANA", "RURAL"}


def test_reps_excluye_codigo_inexistente_y_duplicados(corte):
    div = preparar_divipola(corte["divipola"])
    reps, excluidos = limpiar_reps(corte["reps_ips"], div)
    assert excluidos.to_dict() == {"27086": 4}
    assert reps["codigohabilitacionsede"].is_unique


# --- Controles negativos: datos rotos a propósito -------------------------------
def test_municipio_sin_cruce_detiene_la_limpieza(corte):
    corte["bdua_eps_subsidiado"].loc[0, "mnc_nombre"] = "MUNICIPIO INVENTADO"
    with pytest.raises(ValidacionError, match="sin cruce"):
        limpiar_corte(corte)


def test_grupo_de_edad_nuevo_detiene_la_limpieza(corte):
    corte["bdua_demo_subsidiado"].loc[0, "tps_grp_etr_id"] = "75 a 80"
    with pytest.raises(ValidacionError, match="grupos de edad"):
        limpiar_corte(corte)


def test_vistas_bdua_que_no_cuadran_detienen_la_limpieza(corte):
    corte["bdua_demo_contributivo"].loc[0, "afiliados"] = "999999"
    with pytest.raises(ValidacionError, match="no suman lo mismo"):
        limpiar_corte(corte)


def test_eps_intervenida_ausente_detiene_la_limpieza(corte):
    df = corte["bdua_eps_subsidiado"]
    corte["bdua_eps_subsidiado"] = df[~df["ent_nombre"].str.contains("CAPRESOCA")]
    with pytest.raises(ValidacionError, match="CAPRESOCA"):
        limpiar_corte(corte)
