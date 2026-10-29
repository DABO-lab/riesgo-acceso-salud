"""Etapa 2: limpieza y normalización (homologación DIVIPOLA, EPS canónicas, categorías)."""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- texto
def normalizar_texto(s):
    """Mayúsculas, sin tildes ni signos, y corrige el error de la BDUA '¥' en vez de 'Ñ'."""
    if s is None or (isinstance(s, float) and np.isnan(s)) or s is pd.NA:
        return s
    s = str(s).replace("¥", "Ñ")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- DIVIPOLA
ALIAS_DPTO = {
    "VALLE": "VALLE DEL CAUCA",
    "SAN ANDRES": "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA",
    "BOGOTA": "BOGOTA D C",
}

# (departamento BDUA, municipio BDUA) -> código DIVIPOLA. Revisado uno a uno contra el DANE.
HOMOLOGACION_MANUAL = {
    ("ANTIOQUIA", "ANTIOQUIA"): "05042",  # Santa Fe de Antioquia
    ("ANTIOQUIA", "BOLIVAR"): "05101",  # Ciudad Bolívar
    ("ANTIOQUIA", "CARMEN DE VIBORAL"): "05148",
    ("ANTIOQUIA", "DON MATIAS"): "05237",
    ("ANTIOQUIA", "SAN ANDRES"): "05647",  # San Andrés de Cuerquia
    ("ANTIOQUIA", "SAN PEDRO"): "05664",  # San Pedro de los Milagros
    ("ANTIOQUIA", "SANTUARIO"): "05697",
    ("ANTIOQUIA", "SAN VICENTE"): "05674",  # San Vicente Ferrer
    ("AMAZONAS", "MIRITIÑPARANA"): "91460",
    ("AMAZONAS", "PTO SANTANDER"): "91669",
    ("ATLANTICO", "POLO NUEVO"): "08558",
    ("BOLIVAR", "CARTAGENA"): "13001",
    ("BOLIVAR", "MOMPOS"): "13468",
    ("BOYACA", "GUICAN"): "15332",
    ("BOYACA", "TUTASA"): "15839",  # Tutazá
    ("CALDAS", "SAN JOSE DE CALDAS"): "17665",
    ("CAQUETA", "SAN JOSE DE FRAGUA"): "18610",
    ("CAUCA", "PATIA (EL BORDO)"): "19532",
    ("CAUCA", "PIENDAMO"): "19548",
    ("CAUCA", "SOTARA"): "19760",
    ("CESAR", "CODAZZI"): "20013",
    ("CESAR", "LA PAZ  ROBLES"): "20621",
    ("CHOCO", "BELEN DE BAJIRA"): "27493",
    ("CHOCO", "CANTON DE SAN PABLO"): "27135",
    ("CHOCO", "EL CARMEN"): "27245",  # El Carmen de Atrato
    ("CHOCO", "ITSMINA"): "27361",
    ("CORDOBA", "PURISIMA"): "23586",
    ("CUNDINAMARCA", "EL PEÑOL"): "25258",  # El Peñón
    ("CUNDINAMARCA", "S.ANTONIO TEQUENDAMA"): "25645",
    ("CUNDINAMARCA", "SAN JUAN DE RIO SECO"): "25662",
    ("CUNDINAMARCA", "UBATE"): "25843",
    ("GUAINIA", "BARRANCO MINAS"): "94343",
    ("GUAINIA", "MORICHAL NUEVO"): "94888",
    ("MAGDALENA", "CERRO SAN ANTONIO"): "47161",
    ("MAGDALENA", "EL PIJI¥O DEL CARMEN"): "47545",
    ("MAGDALENA", "SABANA DE SAN ANGEL"): "47660",
    ("MAGDALENA", "SAN SEBASTIAN BUENAVIST"): "47692",
    ("META", "LA URIBE"): "50370",
    ("META", "SAN CARLOS GUAROA"): "50680",
    ("META", "VISTA HERMOSA"): "50711",
    ("NARINO", "CUASPUD"): "52224",
    ("NARINO", "EL TABLON"): "52258",
    ("NARINO", "FRANCIS PIZARRO"): "52520",
    ("NARINO", "LEYVA"): "52405",
    ("NARINO", "TUMACO"): "52835",
    ("NORTE DE SANTANDER", "CUCUTA"): "54001",
    ("RISARALDA", "DOS QUEBRADAS"): "66170",
    ("SANTANDER", "EL CARMEN"): "68235",  # El Carmen de Chucurí
    ("SUCRE", "SINCE"): "70742",
    ("SUCRE", "TOLU"): "70820",
    ("SUCRE", "TOLUVIEJO"): "70823",
    ("TOLIMA", "GUAYABAL"): "73055",  # Armero (cabecera: Guayabal)
    ("TOLIMA", "MARIQUITA"): "73443",
    ("TOLIMA", "VILLA HERMOSA"): "73870",
    ("VALLE", "BUGA"): "76111",
}
AREAS_NO_MUNICIPALIZADAS = {("GUAINIA", "DPTO GUAINIA"), ("VAUPES", "DPTO VAUPES")}
_MANUAL = {(normalizar_texto(d), normalizar_texto(m)): c for (d, m), c in HOMOLOGACION_MANUAL.items()}


def preparar_divipola(div_raw: pd.DataFrame) -> pd.DataFrame:
    div = div_raw.copy()
    div["cod_mpio"] = div["cod_mpio"].astype(str).str.zfill(5)
    div["cod_dpto"] = div["cod_dpto"].astype(str).str.zfill(2)
    for c in ("latitud", "longitud"):
        div[c] = pd.to_numeric(div[c].astype(str).str.replace(",", "."), errors="coerce")
    div["dpto_norm"] = div["dpto"].map(normalizar_texto)
    div["mpio_norm"] = div["nom_mpio"].map(normalizar_texto)
    if not div["cod_mpio"].is_unique:
        raise ValueError("DIVIPOLA tiene códigos de municipio repetidos")
    faltan = set(_MANUAL.values()) - set(div["cod_mpio"])
    if faltan:
        raise ValueError(f"Códigos de la homologación manual que no existen en DIVIPOLA: {sorted(faltan)}")
    return div


def asignar_divipola(
    df: pd.DataFrame, div: pd.DataFrame, col_dpto: str = "dpr_nombre", col_mpio: str = "mnc_nombre"
) -> pd.DataFrame:
    """Agrega cod_mpio y estado_cruce (exacto, manual, area_no_municipalizada, sin_cruce)."""
    exacto = dict(zip(zip(div["dpto_norm"], div["mpio_norm"], strict=True), div["cod_mpio"], strict=True))
    pares = df[[col_dpto, col_mpio]].drop_duplicates()
    filas = []
    for d_raw, m_raw in pares.itertuples(index=False):
        d, m = normalizar_texto(d_raw), normalizar_texto(m_raw)
        d_alias = ALIAS_DPTO.get(d, d)
        if (d, m) in _MANUAL:
            filas.append((d_raw, m_raw, _MANUAL[(d, m)], "manual"))
        elif (d_alias, m) in exacto:
            filas.append((d_raw, m_raw, exacto[(d_alias, m)], "exacto"))
        elif (d, m) in AREAS_NO_MUNICIPALIZADAS:
            filas.append((d_raw, m_raw, None, "area_no_municipalizada"))
        else:
            filas.append((d_raw, m_raw, None, "sin_cruce"))
    mapa = pd.DataFrame(filas, columns=[col_dpto, col_mpio, "cod_mpio", "estado_cruce"])
    return df.merge(mapa, on=[col_dpto, col_mpio], how="left")


# --------------------------------------------------------------------------- EPS
REGLAS_EPS = [  # (palabra clave en el nombre normalizado, nombre canónico). El orden importa.
    ("NUEVA EPS", "NUEVA EPS"),
    ("COOSALUD", "COOSALUD"),
    ("MUTUAL SER", "MUTUAL SER"),
    ("SALUD TOTAL", "SALUD TOTAL"),
    ("EMSSANAR", "EMSSANAR"),
    ("SAVIA", "SAVIA SALUD"),
    ("SANITAS", "SANITAS"),
    ("ASMET", "ASMET SALUD"),
    ("PROTEGER", "PROTEGER"),
    ("CAPITAL SALUD", "CAPITAL SALUD"),
    ("SURAMERICANA", "SURA"),
    ("FAMISANAR", "FAMISANAR"),
    ("COMPENSAR", "COMPENSAR"),
    ("SERVICIO OCCIDENTAL", "SOS"),
    ("CAPRESOCA", "CAPRESOCA"),
    ("MALLAMAS", "MALLAMAS"),
    ("FAMILIAR DE COLOMBIA", "FAMILIAR DE COLOMBIA"),
    ("CABILDOS INDIGENAS DEL CESAR", "DUSAKAWI"),
    ("ANAS WAY", "ANAS WAYUU"),
    ("INDIGENA DEL CAUCA", "AIC"),
    ("PIJAOS", "PIJAOS SALUD"),
    ("ORIENTE COL", "COMFAORIENTE"),
    ("VALLE DEL C", "COMFENALCO VALLE"),
    ("DEL CHOCO", "COMFACHOCO"),
    ("SALUD MIA", "SALUD MIA"),
    ("ALIANSALUD", "ALIANSALUD"),
    ("FERROCARRILES", "FERROCARRILES"),
    ("EMPRESAS PUBLICAS DE MEDELLIN", "EPM"),
]


def eps_canonica(nombre) -> str:
    n = normalizar_texto(nombre)
    n = re.sub(r"\bCM$", "", n).strip()
    for clave, canon in REGLAS_EPS:
        if clave in n:
            return canon
    return n


# --------------------------------------------------------------------------- categorías
ORDEN_EDAD = [
    "< 1",
    "1 a 5",
    "5 a 15",
    "15 a 19",
    "19 a 45",
    "45 a 50",
    "50 a 55",
    "55 a 60",
    "60 a 65",
    "65 a 70",
    "70 a 75",
    "> 75",
]


def zona_simple(z) -> str:
    z = normalizar_texto(z) or ""
    if z.startswith("RURAL"):
        return "RURAL"
    if z.startswith("URBANA"):
        return "URBANA"
    return "SIN DATO"


# --------------------------------------------------------------------------- etapas
def limpiar_bdua(raw: dict, div: pd.DataFrame, eps_intervenidas: list[str]):
    """Une los dos regímenes, homologa municipios y estandariza EPS y categorías."""
    eps = pd.concat([raw["eps_contributivo"], raw["eps_subsidiado"]], ignore_index=True)
    demo = pd.concat([raw["demo_contributivo"], raw["demo_subsidiado"]], ignore_index=True)
    for df in (eps, demo):
        df["afiliados"] = pd.to_numeric(df["afiliados"], errors="coerce")
    eps = asignar_divipola(eps, div)
    demo = asignar_divipola(demo, div)

    eps["eps"] = eps["ent_nombre"].map(eps_canonica)
    eps["eps_intervenida"] = eps["eps"].isin(set(eps_intervenidas))
    eps["regimen"] = eps["tps_rgm_nombre"].map(normalizar_texto)
    eps["zona"] = eps["zns_nombre"].map(zona_simple)
    eps["estado_afiliado"] = eps["tps_est_afl_nombre"].map(normalizar_texto)

    demo["regimen"] = demo["tps_rgm_nombre"].map(normalizar_texto)
    demo["sexo"] = demo["tps_gnr_nombre"].map(normalizar_texto)
    demo["grupo_edad"] = demo["tps_grp_etr_id"].astype(str).str.strip()

    reporte = eps.groupby("estado_cruce").agg(
        pares_municipio=("mnc_nombre", "nunique"), afiliados=("afiliados", "sum")
    )
    reporte["pct_afiliados"] = reporte["afiliados"] / reporte["afiliados"].sum()
    return eps, demo, reporte.reset_index()


def limpiar_reps(raw: dict, div: pd.DataFrame):
    reps = raw["reps_ips"].copy()
    reps["cod_mpio"] = reps["municipiosede"].astype(str).str.zfill(5)
    reps["naturaleza"] = reps["naturalezajuridica"].map(normalizar_texto)
    reps["es_ese"] = reps["ese"].map(normalizar_texto).eq("SI")
    duplicados = int(reps["codigohabilitacionsede"].duplicated().sum())
    reps = reps.drop_duplicates("codigohabilitacionsede")
    fuera = reps.loc[~reps["cod_mpio"].isin(div["cod_mpio"]), "cod_mpio"].value_counts()
    reps = reps[reps["cod_mpio"].isin(div["cod_mpio"])].copy()
    return reps, {"duplicados": duplicados, "sedes_sin_divipola": {k: int(v) for k, v in fuera.items()}}


def resumen_eps(bdua_eps: pd.DataFrame) -> pd.DataFrame:
    r = bdua_eps.groupby(["eps", "eps_intervenida"], as_index=False).agg(
        afiliados=("afiliados", "sum"),
        codigos=("ent_id", lambda s: ", ".join(sorted(s.astype(str).unique()))),
    )
    r["pct_nacional"] = r["afiliados"] / r["afiliados"].sum()
    return r.sort_values("afiliados", ascending=False, ignore_index=True)
