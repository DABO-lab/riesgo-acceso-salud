"""Etapa 3: validaciones de calidad de datos ("contratos de datos").

Cada chequeo devuelve un registro con su resultado. Si un chequeo crítico falla,
el pipeline se detiene: así nunca se entrena un modelo con datos corruptos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .limpieza import ORDEN_EDAD


class ErrorCalidad(Exception):
    """Se lanza cuando falla un chequeo crítico."""


def _chequeo(nombre, ok, detalle, critico=True):
    return {"chequeo": nombre, "ok": bool(ok), "detalle": str(detalle), "critico": critico}


def validar_preparacion(
    bdua_eps, bdua_demo, reps, div, reporte_cruce, cfg, total_anterior: float | None = None
) -> list[dict]:
    v = cfg["validacion"]
    total = float(bdua_eps["afiliados"].sum())
    pct_sin = (
        float(bdua_eps.loc[bdua_eps["estado_cruce"] == "sin_cruce", "afiliados"].sum() / total)
        if total
        else 1
    )
    edades_nuevas = sorted(set(bdua_demo["grupo_edad"]) - set(ORDEN_EDAD))
    faltan_eps = sorted(set(cfg["eps_intervenidas"]["lista"]) - set(bdua_eps["eps"]))
    chequeos = [
        _chequeo(
            "afiliados_sin_nulos_ni_negativos",
            bdua_eps["afiliados"].notna().all() and (bdua_eps["afiliados"] >= 0).all(),
            "la columna afiliados es numérica y no negativa",
        ),
        _chequeo(
            "total_afiliados_minimo",
            total >= v["min_afiliados_total"],
            f"total = {total:,.0f} (mínimo {v['min_afiliados_total']:,})",
        ),
        _chequeo(
            "vistas_bdua_consistentes",
            abs(total - bdua_demo["afiliados"].sum()) < 1,
            f"vista EPS = {total:,.0f}; vista demográfica = {bdua_demo['afiliados'].sum():,.0f}",
        ),
        _chequeo(
            "regimenes_validos",
            set(bdua_eps["regimen"]) <= {"CONTRIBUTIVO", "SUBSIDIADO"},
            sorted(set(bdua_eps["regimen"])),
        ),
        _chequeo("grupos_edad_conocidos", not edades_nuevas, edades_nuevas or "todos conocidos"),
        _chequeo(
            "cruce_divipola",
            pct_sin <= v["max_pct_afiliados_sin_cruce"],
            f"{pct_sin:.4%} de afiliados sin código DIVIPOLA",
        ),
        _chequeo("eps_intervenidas_presentes", not faltan_eps, faltan_eps or "todas presentes"),
        _chequeo("divipola_completa", len(div) >= v["min_municipios"], f"{len(div)} municipios"),
        _chequeo("reps_con_sedes", len(reps) > 0, f"{len(reps):,} sedes de IPS"),
    ]
    if total_anterior:
        var = abs(total - total_anterior) / total_anterior
        chequeos.append(
            _chequeo(
                "variacion_vs_corte_anterior",
                var <= v["max_variacion_vs_corte_anterior"],
                f"variación del total de afiliados = {var:.2%}",
                critico=False,
            )
        )
    return chequeos


def validar_tabla_municipal(tabla: pd.DataFrame, total_bdua: float) -> list[dict]:
    return [
        _chequeo("municipio_unico", tabla["cod_mpio"].is_unique, "una fila por municipio"),
        _chequeo(
            "total_conservado",
            abs(tabla["afiliados"].sum() - total_bdua) < 1,
            f"tabla = {tabla['afiliados'].sum():,.0f}; BDUA municipal = {total_bdua:,.0f}",
        ),
        _chequeo(
            "proporciones_en_rango",
            all(
                tabla[c].dropna().between(0, 1).all()
                for c in ["pct_intervenidas", "pct_rural", "pct_subsidiado", "pct_eps_principal"]
            ),
            "todas las proporciones entre 0 y 1",
        ),
        _chequeo("hhi_en_rango", tabla["hhi"].dropna().between(0, 10000.001).all(), "HHI entre 0 y 10.000"),
        _chequeo(
            "sin_nulos_en_variables_modelo",
            tabla[["pct_intervenidas", "hhi", "ips_x_10mil", "pct_rural", "pct_subsidiado"]]
            .notna()
            .all()
            .all(),
            "variables del modelo completas",
            critico=False,
        ),
    ]


def aplicar(chequeos: list[dict], archivo: Path | None = None) -> None:
    """Guarda el reporte y detiene el pipeline si falla algo crítico."""
    if archivo:
        previo = []
        if archivo.exists():
            previo = json.loads(archivo.read_text(encoding="utf-8"))
        archivo.write_text(json.dumps(previo + chequeos, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in chequeos:
        marca = "OK " if c["ok"] else ("ERR" if c["critico"] else "AVISO")
        print(f"  [{marca}] {c['chequeo']}: {c['detalle']}")
    fallos = [c for c in chequeos if c["critico"] and not c["ok"]]
    if fallos:
        raise ErrorCalidad("Fallaron chequeos críticos: " + ", ".join(c["chequeo"] for c in fallos))
