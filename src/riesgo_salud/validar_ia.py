"""Validación de la IA: ¿clasifica bien las noticias? Se compara con una revisión hecha a mano.

Uso:
    # 1. Sacar una muestra al azar de las noticias de un corte para revisarla a mano
    python -m riesgo_salud.validar_ia preparar --fecha 2026-11-12
    # -> resultados/<fecha>/validacion_ia_muestra.xlsx: el equipo llena las columnas humano_*
    # 2. Medir el acuerdo entre la IA y la revisión humana
    python -m riesgo_salud.validar_ia evaluar --fecha 2026-11-12
    # -> resultados/<fecha>/validacion_ia.json (se muestra en el dashboard)

Columnas a llenar en la muestra:
    humano_relevante       si / no
    humano_departamentos   departamentos separados por ";" (vacío si es nacional)
    humano_tipo            medicamentos, cierre_servicios, deudas_pagos, tutelas_quejas,
                           intervencion_supersalud, protesta u otro
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from .config import cargar_config, ruta
from .noticias import TIPOS, normalizar

MUESTRA = "validacion_ia_muestra.xlsx"


def preparar(cfg: dict, fecha: str, n: int = 30, semilla: int = 42) -> pd.DataFrame:
    carpeta = ruta(cfg, "resultados", fecha)
    noticias = json.loads((carpeta / "noticias.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(noticias)
    df = df[df["relevante"].notna()].sample(n=min(n, len(df)), random_state=semilla).reset_index(drop=True)
    salida = pd.DataFrame(
        {
            "id": range(1, len(df) + 1),
            "titulo": df["titulo"],
            "fuente": df["fuente"],
            "fecha": df["fecha"],
            "enlace": df["enlace"],
            "ia_relevante": df["relevante"].map({True: "si", False: "no"}),
            "ia_departamentos": df["departamentos"].map(lambda x: ";".join(x or [])),
            "ia_tipo": df["tipo"],
            "humano_relevante": "",
            "humano_departamentos": "",
            "humano_tipo": "",
        }
    )
    salida.to_excel(carpeta / MUESTRA, index=False, sheet_name="muestra")
    print(f"Muestra de {len(salida)} noticias en {carpeta / MUESTRA}. Llene las columnas humano_*.")
    return salida


def _conjunto(texto) -> frozenset:
    if pd.isna(texto) or not str(texto).strip():
        return frozenset()
    return frozenset(normalizar(x) for x in str(texto).split(";") if x.strip())


def evaluar(cfg: dict, fecha: str) -> dict:
    carpeta = ruta(cfg, "resultados", fecha)
    df = pd.read_excel(carpeta / MUESTRA, dtype=str).fillna("")
    df = df[df["humano_relevante"].str.strip() != ""]
    if df.empty:
        raise SystemExit("La muestra no tiene revisiones humanas: llene la columna humano_relevante.")
    sn = {"si": 1, "sí": 1, "s": 1, "no": 0, "n": 0}
    ia = df["ia_relevante"].str.strip().str.lower().map(sn)
    hu = df["humano_relevante"].str.strip().str.lower().map(sn)
    ok = ia.notna() & hu.notna()
    ia, hu = ia[ok].astype(int), hu[ok].astype(int)

    ambas = df[ok & (ia == 1) & (hu == 1)]
    dep_ok = [
        _conjunto(a) == _conjunto(b)
        for a, b in zip(ambas["ia_departamentos"], ambas["humano_departamentos"], strict=True)
    ]
    tipos_h = ambas["humano_tipo"].str.strip().str.lower()
    con_tipo = ambas[tipos_h.isin(TIPOS)]
    tipo_ok = (
        con_tipo["ia_tipo"].str.strip().str.lower() == con_tipo["humano_tipo"].str.strip().str.lower()
    ).tolist()

    r = {
        "estado": "ok",
        "fecha_corte": fecha,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "revisadas": int(ok.sum()),
        "relevancia": {
            "acuerdo": round(float((ia == hu).mean()), 3),
            "kappa_cohen": round(float(cohen_kappa_score(hu, ia)), 3) if hu.nunique() > 1 else None,
            "falsos_positivos": int(((ia == 1) & (hu == 0)).sum()),
            "falsos_negativos": int(((ia == 0) & (hu == 1)).sum()),
        },
        "departamentos": {
            "evaluadas": len(dep_ok),
            "acuerdo": round(sum(dep_ok) / len(dep_ok), 3) if dep_ok else None,
        },
        "tipo": {
            "evaluadas": len(tipo_ok),
            "acuerdo": round(sum(tipo_ok) / len(tipo_ok), 3) if tipo_ok else None,
        },
    }
    (carpeta / "validacion_ia.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validación de la clasificación de noticias hecha por la IA")
    ap.add_argument("accion", choices=["preparar", "evaluar"])
    ap.add_argument("--fecha", required=True)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args(argv)
    cfg = cargar_config()
    preparar(cfg, a.fecha, a.n) if a.accion == "preparar" else evaluar(cfg, a.fecha)


if __name__ == "__main__":
    main()
