"""Descarga las 7 tablas crudas desde la API de datos.gov.co.

Cada tabla se guarda en data/raw/<fecha>/<tabla>.csv. Si el archivo ya existe,
se lee de disco y no se vuelve a descargar: el análisis no depende de que el
portal esté disponible, y cada corte queda guardado para compararlo después.

Uso:  uv run python -m salud.data.extract
"""

import json
import time

import pandas as pd
import requests

from salud.config import (
    BASE_URL,
    CLASE_IPS,
    COLS_DEMO,
    COLS_EPS,
    COLS_REPS,
    DATASETS,
    EPS_INTERVENIDAS,
    FECHA_CORTE,
    FECHA_HOY,
    MAX_REINTENTOS,
    PAGE_SIZE,
    TIMEOUT_SEGUNDOS,
    ruta_raw,
)


def soda_get(dataset_id: str, params: dict, page_size: int = PAGE_SIZE, pausa: int = 5) -> pd.DataFrame:
    """Descarga paginada desde la API SODA, con reintentos si la conexión falla."""
    frames, offset = [], 0
    while True:
        p = {**params, "$limit": page_size, "$offset": offset}
        for intento in range(MAX_REINTENTOS):
            try:
                r = requests.get(f"{BASE_URL}{dataset_id}.json", params=p, timeout=TIMEOUT_SEGUNDOS)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if intento == MAX_REINTENTOS - 1:
                    raise
                print(f"  reintento {intento + 1} por: {e}")
                time.sleep(pausa * (intento + 1))
        lote = r.json()
        if not lote:
            break
        frames.append(pd.DataFrame(lote))
        offset += page_size
        if len(lote) < page_size:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def params_agregados(columnas: list[str]) -> dict:
    """Pide al servidor la 'tabla dinámica': suma de afiliados agrupada por columnas."""
    cols = ",".join(columnas)
    return {"$select": f"{cols},sum(cantidad::number) as afiliados", "$group": cols, "$order": cols}


def consultas() -> dict[str, tuple[str, dict]]:
    """Las 7 consultas del proyecto: nombre de archivo -> (dataset, parámetros)."""
    return {
        "bdua_eps_contributivo": (DATASETS["bdua_contributivo"], params_agregados(COLS_EPS)),
        "bdua_eps_subsidiado": (DATASETS["bdua_subsidiado"], params_agregados(COLS_EPS)),
        "bdua_demo_contributivo": (DATASETS["bdua_contributivo"], params_agregados(COLS_DEMO)),
        "bdua_demo_subsidiado": (DATASETS["bdua_subsidiado"], params_agregados(COLS_DEMO)),
        "reps_ips": (
            DATASETS["reps"],
            {
                "$select": ",".join(COLS_REPS),
                "$where": f"claseprestador='{CLASE_IPS}'",
                "$order": "codigohabilitacionsede",
            },
        ),
        "reps_resumen_clase": (
            DATASETS["reps"],
            {
                "$select": "claseprestador,naturalezajuridica,count(*) as sedes",
                "$group": "claseprestador,naturalezajuridica",
                "$order": "claseprestador,naturalezajuridica",
            },
        ),
        "divipola": (DATASETS["divipola"], {"$order": "cod_mpio"}),
    }


def descargar(nombre: str, dataset_id: str, params: dict, carpeta) -> pd.DataFrame:
    ruta = carpeta / f"{nombre}.csv"
    if ruta.exists():
        df = pd.read_csv(ruta, dtype=str)
        print(f"{nombre:<26} (caché) {len(df):>8,} filas")
        return df
    t0 = time.time()
    df = soda_get(dataset_id, params)
    df.to_csv(ruta, index=False)
    print(f"{nombre:<26}         {len(df):>8,} filas  ({time.time() - t0:.0f} s)")
    return df


def main() -> None:
    fecha = FECHA_CORTE or FECHA_HOY
    carpeta = ruta_raw(fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    print(f"Corte {fecha} → {carpeta}")

    filas = {}
    for nombre, (dataset_id, params) in consultas().items():
        filas[nombre] = int(len(descargar(nombre, dataset_id, params, carpeta)))

    # Metadatos del corte: qué se pidió, cuándo y con qué supuestos (trazabilidad)
    meta = {
        "fecha_corte": fecha,
        "datasets": DATASETS,
        "filas": filas,
        "eps_intervenidas": sorted(EPS_INTERVENIDAS),
    }
    (carpeta / "metadatos_corte.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Metadatos guardados en", carpeta / "metadatos_corte.json")


if __name__ == "__main__":
    main()
