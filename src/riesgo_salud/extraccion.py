"""Etapa 1: extracción de datos abiertos desde la API SODA de datos.gov.co.

Las agregaciones se hacen en el servidor, así que se descargan ~127 mil filas en vez de ~2 millones.
Cada tabla se guarda como CSV en data/raw/<fecha>/ y, si ya existe, se lee sin volver a descargar.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from .config import ruta

COLS_EPS = [
    "dpr_nombre",
    "mnc_nombre",
    "ent_id",
    "ent_nombre",
    "tps_rgm_nombre",
    "zns_nombre",
    "tps_est_afl_nombre",
]
COLS_DEMO = ["dpr_nombre", "mnc_nombre", "tps_rgm_nombre", "tps_gnr_nombre", "tps_grp_etr_id"]
# Del REPS NO se descargan correos, teléfonos, direcciones ni documentos (Ley 1581 de 2012).
COLS_REPS = [
    "codigoprestador",
    "nombreprestador",
    "codigohabilitacionsede",
    "nombresede",
    "naturalezajuridica",
    "ese",
    "claseprestador",
    "municipiosede",
    "fecha_corte_reps",
]
CLASE_IPS = "Instituciones Prestadoras de Servicios de Salud - IPS"


def soda_get(
    base_url: str,
    dataset_id: str,
    params: dict,
    tamano_pagina: int = 50000,
    reintentos: int = 4,
    pausa: int = 5,
) -> pd.DataFrame:
    """Descarga paginada con reintentos."""
    frames, offset = [], 0
    while True:
        p = {**params, "$limit": tamano_pagina, "$offset": offset}
        for intento in range(reintentos):
            try:
                r = requests.get(f"{base_url}{dataset_id}.json", params=p, timeout=180)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if intento == reintentos - 1:
                    raise
                print(f"  reintento {intento + 1} por: {e}")
                time.sleep(pausa * (intento + 1))
        lote = r.json()
        if not lote:
            break
        frames.append(pd.DataFrame(lote))
        offset += tamano_pagina
        if len(lote) < tamano_pagina:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _agregados(columnas: list[str]) -> dict:
    cols = ",".join(columnas)
    return {"$select": f"{cols},sum(cantidad::number) as afiliados", "$group": cols, "$order": cols}


def consultas(cfg: dict) -> dict[str, tuple[str, dict]]:
    """Nombre de archivo -> (id del dataset, parámetros de la consulta)."""
    d = cfg["fuente"]["datasets"]
    return {
        "eps_contributivo": (d["bdua_contributivo"], _agregados(COLS_EPS)),
        "eps_subsidiado": (d["bdua_subsidiado"], _agregados(COLS_EPS)),
        "demo_contributivo": (d["bdua_contributivo"], _agregados(COLS_DEMO)),
        "demo_subsidiado": (d["bdua_subsidiado"], _agregados(COLS_DEMO)),
        "reps_ips": (
            d["reps"],
            {
                "$select": ",".join(COLS_REPS),
                "$where": f"claseprestador='{CLASE_IPS}'",
                "$order": "codigohabilitacionsede",
            },
        ),
        "reps_resumen": (
            d["reps"],
            {
                "$select": "claseprestador,naturalezajuridica,count(*) as sedes",
                "$group": "claseprestador,naturalezajuridica",
                "$order": "claseprestador,naturalezajuridica",
            },
        ),
        "divipola": (d["divipola"], {"$order": "cod_mpio"}),
    }


# Nombres de archivo que usó el notebook de la fase 1 (para reutilizar esas descargas)
NOMBRES_FASE1 = {
    "eps_contributivo": "bdua_eps_contributivo",
    "eps_subsidiado": "bdua_eps_subsidiado",
    "demo_contributivo": "bdua_demo_contributivo",
    "demo_subsidiado": "bdua_demo_subsidiado",
    "reps_ips": "reps_ips",
    "reps_resumen": "reps_resumen_clase",
    "divipola": "divipola",
}


def leer_raw(carpeta: Path) -> dict[str, pd.DataFrame] | None:
    """Lee un corte ya descargado (con los nombres actuales o los de la fase 1). None si falta algo."""
    raw = {}
    for n, viejo in NOMBRES_FASE1.items():
        for candidato in (carpeta / f"{n}.csv", carpeta / f"{viejo}.csv"):
            if candidato.exists():
                raw[n] = pd.read_csv(candidato, dtype=str)
                break
        else:
            return None
    return raw


def extraer(cfg: dict, fecha: str, forzar: bool = False) -> dict[str, pd.DataFrame]:
    """Descarga (o lee de caché) todas las tablas del corte `fecha`."""
    carpeta = ruta(cfg, "raw", fecha)
    raw = {}
    for nombre, (dataset_id, params) in consultas(cfg).items():
        archivo = carpeta / f"{nombre}.csv"
        if archivo.exists() and not forzar:
            raw[nombre] = pd.read_csv(archivo, dtype=str)
            print(f"  {nombre:<20} (caché) {len(raw[nombre]):>8,} filas")
            continue
        t0 = time.time()
        df = soda_get(
            cfg["fuente"]["base_url"],
            dataset_id,
            params,
            cfg["fuente"]["tamano_pagina"],
            cfg["fuente"]["reintentos"],
        )
        df.to_csv(archivo, index=False)
        raw[nombre] = df.astype(str)
        print(f"  {nombre:<20}         {len(df):>8,} filas ({time.time() - t0:.0f} s)")
    guardar_metadatos(carpeta, cfg, fecha, raw, origen="api")
    return raw


def guardar_metadatos(carpeta: Path, cfg: dict, fecha: str, raw: dict, origen: str) -> None:
    meta = {
        "fecha_corte": fecha,
        "origen": origen,
        "datasets": cfg["fuente"]["datasets"],
        "filas": {k: int(len(v)) for k, v in raw.items()},
        "eps_intervenidas": cfg["eps_intervenidas"],
    }
    with open(carpeta / "metadatos_corte.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
