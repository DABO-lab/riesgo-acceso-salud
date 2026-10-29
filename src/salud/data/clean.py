"""Limpia y normaliza las tablas crudas de un corte.

Entrada:  data/raw/<fecha>/*.csv
Salida:   data/processed/{divipola,bdua_eps,bdua_demo,reps_ips}_<fecha>.parquet

Cada paso imprime cuántas filas o afiliados afectó: la terminal cuenta la
historia de qué se arregló. Las validaciones detienen el proceso con un
mensaje claro si algo no cuadra (así no se analizan datos corruptos).

Uso:  uv run python -m salud.data.clean
"""

import re
import unicodedata

import pandas as pd

from salud.config import EPS_INTERVENIDAS, ORDEN_EDAD, PROCESSED_DIR, ruta_raw, ultimo_corte
from salud.data.catalogos import (
    ALIAS_DPTO,
    AREAS_NO_MUNICIPALIZADAS,
    HOMOLOGACION_MANUAL,
    REGLAS_EPS,
)


class ValidacionError(ValueError):
    """Los datos no pasaron una validación: hay que revisar antes de seguir."""


def verificar(condicion: bool, mensaje: str) -> None:
    # No usamos `assert`: Python lo desactiva con -O y la validación desaparecería.
    if not condicion:
        raise ValidacionError(mensaje)


# --- Paso 1: normalización de texto -------------------------------------------
def normalizar_texto(s):
    """Mayúsculas, sin tildes ni signos, espacios simples. Corrige ¥ -> Ñ de la BDUA.

    "Bogotá, D.C." -> "BOGOTA D C";  "NARI¥O" -> "NARINO".
    """
    if pd.isna(s):
        return s
    s = str(s).replace("¥", "Ñ")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


# --- Paso 2: DIVIPOLA y homologación de municipios ----------------------------
def preparar_divipola(raw_div: pd.DataFrame) -> pd.DataFrame:
    div = raw_div.copy()
    div["cod_mpio"] = div["cod_mpio"].str.zfill(5)
    div["cod_dpto"] = div["cod_dpto"].str.zfill(2)
    # DIVIPOLA trae coma decimal en las coordenadas ("6,246631")
    for c in ("latitud", "longitud"):
        div[c] = pd.to_numeric(div[c].str.replace(",", "."), errors="coerce")
    div["dpto_norm"] = div["dpto"].map(normalizar_texto)
    div["mpio_norm"] = div["nom_mpio"].map(normalizar_texto)
    verificar(div["cod_mpio"].is_unique, "DIVIPOLA con códigos de municipio repetidos")
    manuales_inexistentes = set(HOMOLOGACION_MANUAL.values()) - set(div["cod_mpio"])
    verificar(
        not manuales_inexistentes,
        f"Códigos de HOMOLOGACION_MANUAL que no existen en DIVIPOLA: {manuales_inexistentes}",
    )
    return div


def asignar_divipola(
    df: pd.DataFrame, div: pd.DataFrame, col_dpto: str = "dpr_nombre", col_mpio: str = "mnc_nombre"
) -> pd.DataFrame:
    """Agrega cod_mpio y estado_cruce (manual | exacto | area_no_municipalizada | sin_cruce).

    Orden: 1) homologación manual, 2) cruce exacto dpto+mpio (con alias de
    departamento), 3) áreas no municipalizadas. Lo demás queda 'sin_cruce'.
    El cruce es por departamento + municipio: hay nombres repetidos entre
    departamentos (varios 'SAN PEDRO', 'BOLIVAR'...).
    """
    manual = {(normalizar_texto(d), normalizar_texto(m)): c for (d, m), c in HOMOLOGACION_MANUAL.items()}
    exacto = dict(zip(zip(div["dpto_norm"], div["mpio_norm"], strict=True), div["cod_mpio"], strict=True))
    areas = {(normalizar_texto(d), normalizar_texto(m)) for d, m in AREAS_NO_MUNICIPALIZADAS}

    def resolver(d_orig, m_orig):
        d, m = normalizar_texto(d_orig), normalizar_texto(m_orig)
        if (d, m) in manual:
            return manual[(d, m)], "manual"
        if (ALIAS_DPTO.get(d, d), m) in exacto:
            return exacto[(ALIAS_DPTO.get(d, d), m)], "exacto"
        if (d, m) in areas:
            return None, "area_no_municipalizada"
        return None, "sin_cruce"

    # Se resuelve una vez por par único (≈1.100) y no por fila (≈100.000)
    pares = df[[col_dpto, col_mpio]].drop_duplicates()
    resueltos = [resolver(d, m) for d, m in zip(pares[col_dpto], pares[col_mpio], strict=True)]
    pares = pares.assign(cod_mpio=[r[0] for r in resueltos], estado_cruce=[r[1] for r in resueltos])
    return df.merge(pares, on=[col_dpto, col_mpio], how="left")


def reporte_cruce(bdua_eps: pd.DataFrame) -> pd.DataFrame:
    rep = bdua_eps.groupby("estado_cruce").agg(
        pares_municipio=("mnc_nombre", "nunique"), afiliados=("afiliados", "sum")
    )
    rep["pct_afiliados"] = rep["afiliados"] / rep["afiliados"].sum() * 100
    return rep


# --- Paso 3: EPS canónicas -----------------------------------------------------
def eps_canonica(nombre: str) -> str:
    """Une los varios códigos de una EPS (uno por régimen y otro '-CM') en un nombre corto."""
    n = normalizar_texto(nombre)
    n = re.sub(r"\bCM$", "", n).strip()
    for clave, canon in REGLAS_EPS:
        if clave in n:
            return canon
    return n  # sin regla: se conserva el nombre normalizado


def zona_simple(z: str) -> str:
    z = normalizar_texto(z)
    if z.startswith("RURAL"):
        return "RURAL"
    return "URBANA" if z.startswith("URBANA") else "SIN DATO"


# --- Limpieza de cada tabla ----------------------------------------------------
def limpiar_bdua_eps(contributivo: pd.DataFrame, subsidiado: pd.DataFrame, div: pd.DataFrame) -> pd.DataFrame:
    df = pd.concat([contributivo, subsidiado], ignore_index=True)
    df["afiliados"] = pd.to_numeric(df["afiliados"], errors="coerce")
    df = asignar_divipola(df, div)
    df["eps"] = df["ent_nombre"].map(eps_canonica)
    df["eps_intervenida"] = df["eps"].isin(EPS_INTERVENIDAS)
    df["regimen"] = df["tps_rgm_nombre"].map(normalizar_texto)
    df["zona"] = df["zns_nombre"].map(zona_simple)
    df["estado_afiliado"] = df["tps_est_afl_nombre"].map(normalizar_texto)
    return df


def limpiar_bdua_demo(
    contributivo: pd.DataFrame, subsidiado: pd.DataFrame, div: pd.DataFrame
) -> pd.DataFrame:
    df = pd.concat([contributivo, subsidiado], ignore_index=True)
    df["afiliados"] = pd.to_numeric(df["afiliados"], errors="coerce")
    df = asignar_divipola(df, div)
    df["regimen"] = df["tps_rgm_nombre"].map(normalizar_texto)
    df["sexo"] = df["tps_gnr_nombre"].map(normalizar_texto)
    edad = df["tps_grp_etr_id"].str.strip()
    # Un grupo que no está en ORDEN_EDAD queda nulo y la validación lo detecta
    df["grupo_edad"] = pd.Categorical(edad.where(edad.isin(ORDEN_EDAD)), categories=ORDEN_EDAD, ordered=True)
    return df


def limpiar_reps(reps_ips: pd.DataFrame, div: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Solo sedes de IPS, sin duplicados y con un código de municipio que exista en DIVIPOLA.

    Devuelve (reps limpio, conteo de sedes excluidas por código inexistente).
    """
    reps = reps_ips.copy()
    reps["cod_mpio"] = reps["municipiosede"].str.zfill(5)
    reps["naturaleza"] = reps["naturalezajuridica"].map(normalizar_texto)
    reps["es_ese"] = reps["ese"].map(normalizar_texto).eq("SI")
    reps = reps.drop_duplicates("codigohabilitacionsede")
    excluidos = reps.loc[~reps["cod_mpio"].isin(div["cod_mpio"]), "cod_mpio"].value_counts()
    reps = reps[reps["cod_mpio"].isin(div["cod_mpio"])]
    return reps, excluidos


def validar(bdua_eps: pd.DataFrame, bdua_demo: pd.DataFrame) -> None:
    verificar(
        bdua_eps["afiliados"].notna().all() and (bdua_eps["afiliados"] >= 0).all(),
        "Hay afiliados nulos o negativos en la BDUA",
    )
    regimenes = set(bdua_eps["regimen"])
    verificar(regimenes <= {"CONTRIBUTIVO", "SUBSIDIADO"}, f"Régimen inesperado: {regimenes}")
    verificar(
        bdua_demo["grupo_edad"].notna().all(), "Hay grupos de edad nuevos: actualice ORDEN_EDAD en config.py"
    )
    faltan = set(EPS_INTERVENIDAS) - set(bdua_eps["eps"])
    verificar(not faltan, f"EPS intervenidas que no aparecen en la BDUA (revise REGLAS_EPS): {faltan}")
    sin_cruce = bdua_eps.loc[bdua_eps["estado_cruce"] == "sin_cruce", ["dpr_nombre", "mnc_nombre"]]
    verificar(
        sin_cruce.empty,
        "Municipios sin cruce con DIVIPOLA. Agréguelos a HOMOLOGACION_MANUAL en catalogos.py:\n"
        + sin_cruce.drop_duplicates().to_string(index=False),
    )
    dif = abs(bdua_eps["afiliados"].sum() - bdua_demo["afiliados"].sum())
    verificar(dif == 0, f"Las dos vistas de la BDUA no suman lo mismo (diferencia: {dif:,.0f})")


def cargar_raw(fecha: str) -> dict[str, pd.DataFrame]:
    carpeta = ruta_raw(fecha)
    return {p.stem: pd.read_csv(p, dtype=str) for p in sorted(carpeta.glob("*.csv"))}


def limpiar_corte(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Aplica toda la limpieza a las tablas crudas de un corte y valida el resultado."""
    div = preparar_divipola(raw["divipola"])
    print(f"Paso 1 - DIVIPOLA: {len(div):,} municipios en {div['cod_dpto'].nunique()} departamentos")

    bdua_eps = limpiar_bdua_eps(raw["bdua_eps_contributivo"], raw["bdua_eps_subsidiado"], div)
    bdua_demo = limpiar_bdua_demo(raw["bdua_demo_contributivo"], raw["bdua_demo_subsidiado"], div)
    print("Paso 2 - Homologación de municipios con DIVIPOLA:")
    print(reporte_cruce(bdua_eps).to_string(float_format=lambda x: f"{x:,.2f}"))

    n_codigos = bdua_eps["ent_id"].nunique()
    print(f"Paso 3 - EPS unificadas: {n_codigos} códigos -> {bdua_eps['eps'].nunique()} EPS")
    pct_int = bdua_eps.loc[bdua_eps["eps_intervenida"], "afiliados"].sum() / bdua_eps["afiliados"].sum()
    print(f"         {pct_int:.1%} de los afiliados está en EPS intervenidas ({len(EPS_INTERVENIDAS)} EPS)")

    reps, excluidos = limpiar_reps(raw["reps_ips"], div)
    print(
        f"Paso 4 - REPS: {len(reps):,} sedes de IPS; excluidas por código inexistente: {int(excluidos.sum())}"
    )
    if len(excluidos):
        print("         " + ", ".join(f"{c} ({n})" for c, n in excluidos.items()))

    validar(bdua_eps, bdua_demo)
    print(f"Validaciones superadas. Afiliados totales: {bdua_eps['afiliados'].sum():,.0f}")
    return {"divipola": div, "bdua_eps": bdua_eps, "bdua_demo": bdua_demo, "reps_ips": reps}


def main() -> None:
    fecha = ultimo_corte()
    print(f"Limpiando el corte {fecha}")
    limpios = limpiar_corte(cargar_raw(fecha))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, df in limpios.items():
        df.to_parquet(PROCESSED_DIR / f"{nombre}_{fecha}.parquet", index=False)
    print(f"Guardado en {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
