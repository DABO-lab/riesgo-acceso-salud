"""Construye la tabla analítica municipal: una fila por municipio.

Une BDUA (demanda: de qué EPS depende la gente), REPS (oferta: cuántas sedes
de IPS hay) y DIVIPOLA (la llave y las coordenadas).

Entrada:  data/processed/{divipola,bdua_eps,reps_ips}_<fecha>.parquet
Salida:   data/processed/tabla_municipal_<fecha>.{parquet,csv}

Uso:  uv run python -m salud.features
"""

import numpy as np
import pandas as pd

from salud.config import PROCESSED_DIR, UMBRAL_DEPENDENCIA_INTERVENIDAS, ultimo_corte
from salud.data.clean import verificar

COLUMNAS_DIVIPOLA = ["cod_mpio", "cod_dpto", "dpto", "nom_mpio", "tipo_municipio", "latitud", "longitud"]

CUADRANTES = [
    "Alta dependencia · baja oferta",
    "Alta dependencia · oferta media/alta",
    "Baja dependencia · baja oferta",
    "Baja dependencia · oferta media/alta",
]


def participacion_eps(bdua_eps: pd.DataFrame) -> pd.DataFrame:
    """Afiliados y participación de cada EPS dentro de cada municipio."""
    b = bdua_eps[bdua_eps["cod_mpio"].notna()]
    eps_mun = b.groupby(["cod_mpio", "eps", "eps_intervenida"], as_index=False)["afiliados"].sum()
    eps_mun["part"] = eps_mun["afiliados"] / eps_mun.groupby("cod_mpio")["afiliados"].transform("sum")
    return eps_mun


def indicadores_demanda(bdua_eps: pd.DataFrame) -> pd.DataFrame:
    """Afiliados, % subsidiado, % rural, % en EPS intervenidas, n_eps, HHI y EPS principal."""
    b = bdua_eps[bdua_eps["cod_mpio"].notna()]
    eps_mun = participacion_eps(bdua_eps)

    dem = (
        b.assign(
            af_sub=np.where(b["regimen"] == "SUBSIDIADO", b["afiliados"], 0),
            af_rur=np.where(b["zona"] == "RURAL", b["afiliados"], 0),
            af_int=np.where(b["eps_intervenida"], b["afiliados"], 0),
        )
        .groupby("cod_mpio")
        .agg(
            afiliados=("afiliados", "sum"),
            af_sub=("af_sub", "sum"),
            af_rur=("af_rur", "sum"),
            af_int=("af_int", "sum"),
        )
    )
    dem["pct_subsidiado"] = dem["af_sub"] / dem["afiliados"]
    dem["pct_rural"] = dem["af_rur"] / dem["afiliados"]
    dem["pct_intervenidas"] = dem["af_int"] / dem["afiliados"]
    dem["n_eps"] = eps_mun.groupby("cod_mpio")["eps"].nunique()
    # HHI: suma de participaciones al cuadrado, en escala 0-10.000.
    # Ej.: 60 % y 40 % -> 60² + 40² = 5.200.
    dem["hhi"] = eps_mun.assign(part2=eps_mun["part"] ** 2).groupby("cod_mpio")["part2"].sum() * 10_000
    dem = dem.drop(columns=["af_sub", "af_rur", "af_int"]).reset_index()

    principal = (
        eps_mun.sort_values(["cod_mpio", "part"], ascending=[True, False])
        .drop_duplicates("cod_mpio")
        .rename(columns={"eps": "eps_principal", "part": "pct_eps_principal"})[
            ["cod_mpio", "eps_principal", "pct_eps_principal"]
        ]
    )
    return dem.merge(principal, on="cod_mpio", how="left")


def indicadores_oferta(reps: pd.DataFrame) -> pd.DataFrame:
    return (
        reps.groupby("cod_mpio")
        .agg(
            sedes_ips=("codigohabilitacionsede", "size"),
            sedes_ips_publicas=("naturaleza", lambda s: (s == "PUBLICA").sum()),
            sedes_ese=("es_ese", "sum"),
        )
        .reset_index()
    )


def construir_tabla_municipal(div: pd.DataFrame, bdua_eps: pd.DataFrame, reps: pd.DataFrame) -> pd.DataFrame:
    tabla = (
        div[COLUMNAS_DIVIPOLA]
        .merge(indicadores_demanda(bdua_eps), on="cod_mpio", how="left")
        .merge(indicadores_oferta(reps), on="cod_mpio", how="left")
    )
    for c in ["sedes_ips", "sedes_ips_publicas", "sedes_ese"]:
        tabla[c] = tabla[c].fillna(0).astype(int)
    tabla["ips_x_10mil"] = np.where(
        tabla["afiliados"] > 0, tabla["sedes_ips"] / tabla["afiliados"] * 10_000, np.nan
    )
    tabla["sin_ips"] = tabla["sedes_ips"] == 0

    afiliados_con_municipio = bdua_eps.loc[bdua_eps["cod_mpio"].notna(), "afiliados"].sum()
    verificar(tabla["cod_mpio"].is_unique, "La tabla municipal tiene municipios repetidos")
    verificar(
        np.isclose(tabla["afiliados"].sum(), afiliados_con_municipio),
        "La tabla municipal no conserva el total de afiliados",
    )
    verificar(tabla["pct_intervenidas"].dropna().between(0, 1).all(), "pct_intervenidas fuera de [0, 1]")
    verificar(tabla["hhi"].dropna().between(0, 10_000.001).all(), "HHI fuera de [0, 10.000]")
    return tabla


def clasificar_cuadrante(tabla: pd.DataFrame, umbral: float = UMBRAL_DEPENDENCIA_INTERVENIDAS) -> pd.Series:
    """Clasificación EXPLORATORIA: dependencia de EPS intervenidas (umbral) x oferta (mediana).

    No es el índice de riesgo final: ese se construye en la fase 2. Los
    municipios sin afiliados en la BDUA quedan sin cuadrante (nulo).
    """
    mediana_oferta = tabla["ips_x_10mil"].median()
    alta_dep = tabla["pct_intervenidas"] >= umbral
    baja_oferta = tabla["ips_x_10mil"] <= mediana_oferta
    cuadrante = pd.Series(
        np.select([alta_dep & baja_oferta, alta_dep, baja_oferta], CUADRANTES[:3], default=CUADRANTES[3]),
        index=tabla.index,
        name="cuadrante",
    )
    sin_datos = tabla["pct_intervenidas"].isna() | tabla["ips_x_10mil"].isna()
    return cuadrante.mask(sin_datos)


def main() -> None:
    fecha = ultimo_corte()
    div, bdua_eps, reps = (
        pd.read_parquet(PROCESSED_DIR / f"{nombre}_{fecha}.parquet")
        for nombre in ("divipola", "bdua_eps", "reps_ips")
    )
    tabla = construir_tabla_municipal(div, bdua_eps, reps)
    tabla["cuadrante"] = clasificar_cuadrante(tabla)

    print(f"Municipios en la tabla:              {len(tabla):,}")
    print(f"Municipios sin afiliados en la BDUA: {tabla['afiliados'].isna().sum()}")
    print(f"Municipios sin ninguna sede de IPS:  {tabla['sin_ips'].sum()}")
    print("\nClasificación exploratoria:")
    resumen = tabla.groupby("cuadrante").agg(municipios=("cod_mpio", "size"), afiliados=("afiliados", "sum"))
    print(resumen.reindex(CUADRANTES).to_string(float_format=lambda x: f"{x:,.0f}"))

    tabla.to_parquet(PROCESSED_DIR / f"tabla_municipal_{fecha}.parquet", index=False)
    # utf-8-sig: para que Excel y Power BI abran bien las tildes
    tabla.to_csv(PROCESSED_DIR / f"tabla_municipal_{fecha}.csv", index=False, encoding="utf-8-sig")
    print(f"\nGuardado en {PROCESSED_DIR / f'tabla_municipal_{fecha}'}.{{parquet,csv}}")


if __name__ == "__main__":
    main()
