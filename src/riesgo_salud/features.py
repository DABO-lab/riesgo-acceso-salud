"""Etapa 4: tabla analítica municipal (una fila por municipio)."""

from __future__ import annotations

import numpy as np
import pandas as pd

DICCIONARIO = {
    "cod_mpio": "Código DIVIPOLA del municipio (5 dígitos)",
    "afiliados": "Total de afiliados (contributivo + subsidiado)",
    "pct_subsidiado": "Proporción de afiliados en el régimen subsidiado",
    "pct_rural": "Proporción de afiliados en zona rural",
    "pct_intervenidas": "Proporción de afiliados en EPS intervenidas",
    "n_eps": "Número de EPS con afiliados en el municipio",
    "eps_principal": "EPS con más afiliados en el municipio",
    "pct_eps_principal": "Participación de la EPS principal",
    "eps_principal_intervenida": "La EPS principal está intervenida (sí/no)",
    "hhi": "Índice Herfindahl-Hirschman de concentración de EPS (0-10.000)",
    "sedes_ips": "Sedes de IPS habilitadas (REPS)",
    "sedes_ips_publicas": "Sedes de IPS públicas",
    "sedes_ese": "Sedes de Empresas Sociales del Estado",
    "ips_x_10mil": "Sedes de IPS por cada 10.000 afiliados",
}


def construir_tabla_municipal(bdua_eps: pd.DataFrame, reps: pd.DataFrame, div: pd.DataFrame) -> pd.DataFrame:
    b = bdua_eps[bdua_eps["cod_mpio"].notna()]

    eps_mun = b.groupby(["cod_mpio", "eps", "eps_intervenida"], as_index=False)["afiliados"].sum()
    eps_mun["part"] = eps_mun["afiliados"] / eps_mun.groupby("cod_mpio")["afiliados"].transform("sum")
    eps_mun["part2"] = eps_mun["part"] ** 2
    principal = (
        eps_mun.sort_values(["cod_mpio", "part"], ascending=[True, False])
        .drop_duplicates("cod_mpio")
        .rename(
            columns={
                "eps": "eps_principal",
                "part": "pct_eps_principal",
                "eps_intervenida": "eps_principal_intervenida",
            }
        )[["cod_mpio", "eps_principal", "pct_eps_principal", "eps_principal_intervenida"]]
    )

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
    dem["hhi"] = eps_mun.groupby("cod_mpio")["part2"].sum() * 10000
    dem = dem.drop(columns=["af_sub", "af_rur", "af_int"]).reset_index()

    oferta = (
        reps.groupby("cod_mpio")
        .agg(
            sedes_ips=("codigohabilitacionsede", "size"),
            sedes_ips_publicas=("naturaleza", lambda s: int((s == "PUBLICA").sum())),
            sedes_ese=("es_ese", "sum"),
        )
        .reset_index()
    )

    tabla = (
        div[["cod_mpio", "cod_dpto", "dpto", "nom_mpio", "tipo_municipio", "latitud", "longitud"]]
        .merge(dem, on="cod_mpio", how="left")
        .merge(principal, on="cod_mpio", how="left")
        .merge(oferta, on="cod_mpio", how="left")
    )
    for c in ["sedes_ips", "sedes_ips_publicas", "sedes_ese"]:
        tabla[c] = tabla[c].fillna(0).astype(int)
    tabla["ips_x_10mil"] = np.where(
        tabla["afiliados"] > 0, tabla["sedes_ips"] / tabla["afiliados"] * 10000, np.nan
    )
    tabla["eps_principal_intervenida"] = tabla["eps_principal_intervenida"].astype("boolean")
    return tabla


CUADRANTES = [
    "Alta dependencia · baja oferta",
    "Alta dependencia · oferta media/alta",
    "Baja dependencia · baja oferta",
    "Baja dependencia · oferta media/alta",
]


def clasificar_cuadrante(tabla: pd.DataFrame, umbral: float = 0.50) -> pd.Series:
    """Clasificación EXPLORATORIA de la fase 1: dependencia de EPS intervenidas (umbral) x oferta
    de IPS (mediana nacional). La usa el EDA; el índice de riesgo (indice.py) la reemplaza.
    Los municipios sin afiliados quedan sin cuadrante.
    """
    alta_dep = tabla["pct_intervenidas"] >= umbral
    baja_oferta = tabla["ips_x_10mil"] <= tabla["ips_x_10mil"].median()
    cuadrante = pd.Series(
        np.select([alta_dep & baja_oferta, alta_dep, baja_oferta], CUADRANTES[:3], default=CUADRANTES[3]),
        index=tabla.index,
        name="cuadrante",
    )
    return cuadrante.mask(tabla["pct_intervenidas"].isna() | tabla["ips_x_10mil"].isna())
