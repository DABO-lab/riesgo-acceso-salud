"""Etapa 7: monitoreo entre cortes mensuales (detección de cambios o "drift").

Compara el corte actual con el anterior:
- PSI (Population Stability Index) de cada variable del modelo:
  < 0,10 estable · 0,10-0,25 cambio moderado · > 0,25 cambio fuerte (se recomienda reentrenar).
- Cuántos municipios cambian de nivel de riesgo y de grupo.
- Variación del total de afiliados y de la lista de EPS intervenidas.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def psi(referencia: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    ref, act = referencia.dropna().to_numpy(float), actual.dropna().to_numpy(float)
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(cortes) < 3:
        return 0.0
    cortes[0], cortes[-1] = -np.inf, np.inf
    p = np.histogram(ref, cortes)[0] / len(ref)
    q = np.histogram(act, cortes)[0] / len(act)
    p, q = np.clip(p, 1e-4, None), np.clip(q, 1e-4, None)
    return float(np.sum((q - p) * np.log(q / p)))


def corte_anterior(carpeta_resultados: Path, fecha: str) -> str | None:
    fechas = sorted(
        p.name
        for p in carpeta_resultados.iterdir()
        if p.is_dir() and (p / "municipios_riesgo.csv").exists() and p.name < fecha
    )
    return fechas[-1] if fechas else None


def comparar(anterior: pd.DataFrame, actual: pd.DataFrame, cfg: dict, fecha_ant: str, fecha: str) -> dict:
    mcfg = cfg["monitoreo"]
    variables = cfg["clustering"]["variables"] + ["indice_riesgo"]
    psis = {v: psi(anterior[v], actual[v]) for v in variables if v in anterior and v in actual}
    m = anterior[["cod_mpio", "nivel_riesgo", "grupo"]].merge(
        actual[["cod_mpio", "nivel_riesgo", "grupo"]], on="cod_mpio", suffixes=("_ant", "_act")
    )
    cambio_nivel = float((m["nivel_riesgo_ant"].astype(str) != m["nivel_riesgo_act"].astype(str)).mean())
    cambio_grupo = float((m["grupo_ant"] != m["grupo_act"]).mean())
    tot_a, tot_b = anterior["afiliados"].sum(), actual["afiliados"].sum()
    alertas = []
    for v, val in psis.items():
        if val > mcfg["psi_critico"]:
            alertas.append(f"Cambio FUERTE en {v} (PSI = {val:.3f}): se recomienda reentrenar el modelo.")
        elif val > mcfg["psi_alerta"]:
            alertas.append(f"Cambio moderado en {v} (PSI = {val:.3f}).")
    if cambio_nivel > mcfg["max_pct_cambio_nivel"]:
        alertas.append(f"{cambio_nivel:.1%} de los municipios cambió de nivel de riesgo.")
    reentrenar = any(v > mcfg["psi_critico"] for v in psis.values())
    return {
        "fecha_anterior": fecha_ant,
        "fecha_actual": fecha,
        "psi": psis,
        "pct_municipios_cambian_nivel": cambio_nivel,
        "pct_municipios_cambian_grupo": cambio_grupo,
        "variacion_total_afiliados": float((tot_b - tot_a) / tot_a) if tot_a else None,
        "alertas": alertas,
        "reentrenar": reentrenar,
    }


def concordancia(modelo_anterior, modelo_nuevo, X: pd.DataFrame) -> dict:
    """Qué tanto coinciden los grupos del modelo del mes pasado y del nuevo sobre los datos actuales."""
    from sklearn.metrics import adjusted_rand_score

    a, b = modelo_anterior.predict(X), modelo_nuevo.predict(X)
    return {
        "ari_modelo_anterior_vs_nuevo": float(adjusted_rand_score(a, b)),
        "pct_mismo_grupo_modelo_anterior": float((a == b).mean()),
    }


def informe_markdown(r: dict) -> str:
    if r.get("sin_referencia"):
        return (
            f"# Monitoreo del corte {r['fecha_actual']}\n\n"
            "Este es el primer corte guardado: todavía no hay un corte anterior para comparar.\n"
        )
    filas = "\n".join(
        f"| {v} | {p:.3f} | {'fuerte' if p > 0.25 else 'moderado' if p > 0.10 else 'estable'} |"
        for v, p in r["psi"].items()
    )
    alertas = "\n".join(f"- {a}" for a in r["alertas"]) or "- Sin alertas: los datos se mantienen estables."
    return f"""# Monitoreo del corte {r["fecha_actual"]} frente a {r["fecha_anterior"]}

**¿Reentrenar el modelo?** {"Sí" if r["reentrenar"] else "No"}

| Variable | PSI | Lectura |
|---|---|---|
{filas}

- Municipios que cambiaron de nivel de riesgo: {r["pct_municipios_cambian_nivel"]:.1%}
- Municipios que cambiaron de grupo: {r["pct_municipios_cambian_grupo"]:.1%}
- Variación del total de afiliados: {r["variacion_total_afiliados"]:.2%}
- Concordancia entre el modelo anterior y el nuevo (ARI): {r.get("ari_modelo_anterior_vs_nuevo", float("nan")):.2f}

## Alertas
{alertas}
"""


def guardar(r: dict, carpeta: Path) -> None:
    (carpeta / "monitoreo.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "monitoreo.md").write_text(informe_markdown(r), encoding="utf-8")
