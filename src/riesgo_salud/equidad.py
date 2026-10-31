"""Auditoría de equidad y sesgos del índice, en cada corte.

El índice no clasifica personas, pero sí decide qué territorios se miran primero. Un error
sistemático deja a un grupo de municipios por fuera de la atención. Esta etapa mide, con los
mismos datos del corte, los sesgos que el equipo identificó (ver docs/etica_usuario_beneficio.md):

1. Tamaño del municipio: ¿el índice favorece o castiga a los municipios grandes o pequeños?
2. Población muy pequeña: con pocos afiliados, una sola sede de IPS dispara la oferta por
   10.000 afiliados y el municipio parece bien atendido aunque esté lejos de todo.
3. Vulnerables con nivel Bajo: municipios muy rurales y muy subsidiados que salen en Bajo
   porque su EPS no está intervenida. Bajo no significa buen acceso.
4. Incertidumbre: municipios cuya entrada al 10 % de mayor riesgo depende de los pesos.
5. Peso de cada variable de vulnerabilidad en el ranking (correlación de Spearman).

No usa ni produce datos personales. Solo alerta: la decisión sobre qué hacer es del usuario.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BANDAS_TAMANO = [0, 5_000, 20_000, 100_000, np.inf]
NOMBRES_BANDA = ["< 5.000", "5.000-20.000", "20.000-100.000", "> 100.000"]
COLUMNAS_LISTA = ["cod_mpio", "nom_mpio", "dpto", "afiliados", "indice_riesgo", "nivel_riesgo"]


def _spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def _lista(df: pd.DataFrame, extra: list[str], orden: str, n: int = 15) -> list[dict]:
    cols = [c for c in COLUMNAS_LISTA + extra if c in df.columns]
    return df.sort_values(orden, ascending=False)[cols].head(n).round(3).to_dict("records")


def auditar(tabla: pd.DataFrame, cfg: dict) -> dict:
    """Recibe la tabla final del corte (una fila por municipio con índice, nivel y prob_top10)."""
    c = cfg.get("equidad", {})
    umbral_pequena = c.get("poblacion_pequena", 2000)
    rural_min, subs_min = c.get("vulnerable_rural", 0.5), c.get("vulnerable_subsidiado", 0.8)
    inc_min, inc_max = c.get("incertidumbre_top10", [0.2, 0.8])
    t = tabla.copy()
    alertas: list[str] = []

    # 1. Tamaño
    t["banda"] = pd.cut(t["afiliados"], BANDAS_TAMANO, labels=NOMBRES_BANDA, right=False)
    por_tamano = (
        t.groupby("banda", observed=True)
        .agg(
            municipios=("cod_mpio", "size"),
            indice_promedio=("indice_riesgo", "mean"),
            pct_muy_alto=("nivel_riesgo", lambda s: float((s == "Muy alto").mean())),
            ips_x_10mil_mediana=("ips_x_10mil", "median"),
        )
        .round(3)
        .reset_index()
    )
    por_tamano["banda"] = por_tamano["banda"].astype(str)

    # 2. Población muy pequeña: oferta inflada
    pequenos = t[t["afiliados"] < umbral_pequena]
    mediana_nacional = float(t["ips_x_10mil"].median())
    mediana_pequenos = float(pequenos["ips_x_10mil"].median()) if len(pequenos) else float("nan")
    if len(pequenos) and mediana_pequenos > 2 * mediana_nacional:
        alertas.append(
            f"{len(pequenos)} municipios con menos de {_fmt(umbral_pequena)} afiliados tienen una oferta "
            f"mediana de {_fmt(mediana_pequenos, 1)} IPS por 10.000, contra {_fmt(mediana_nacional, 1)} en el "
            "país: "
            "su componente de oferta subestima el riesgo (no mide distancia)."
        )

    # 3. Vulnerables con nivel Bajo
    vulnerables = t[(t["pct_rural"] >= rural_min) & (t["pct_subsidiado"] >= subs_min)]
    vulnerables_bajo = vulnerables[vulnerables["nivel_riesgo"] == "Bajo"]
    if len(vulnerables_bajo):
        alertas.append(
            f"{len(vulnerables_bajo)} de {len(vulnerables)} municipios vulnerables (rural >= "
            f"{_pct(rural_min)} y subsidiado >= {_pct(subs_min)}) quedan en nivel Bajo: su riesgo por EPS "
            "intervenidas es bajo, pero no se debe leer como buen acceso."
        )

    # 4. Incertidumbre del top 10 %
    inciertos = (
        t[(t["prob_top10"] > inc_min) & (t["prob_top10"] < inc_max)] if "prob_top10" in t else t.iloc[:0]
    )

    # 5. Qué tanto pesa cada rasgo de vulnerabilidad en el ranking
    correlaciones = {
        "log_afiliados": _spearman(t["indice_riesgo"], np.log1p(t["afiliados"])),
        "pct_rural": _spearman(t["indice_riesgo"], t["pct_rural"]),
        "pct_subsidiado": _spearman(t["indice_riesgo"], t["pct_subsidiado"]),
        "pct_intervenidas": _spearman(t["indice_riesgo"], t["pct_intervenidas"]),
    }

    # Cobertura territorial: departamentos sin ningún municipio en Alto o Muy alto
    altos = t[t["nivel_riesgo"].isin(["Alto", "Muy alto"])]
    sin_alto = sorted(set(t["dpto"]) - set(altos["dpto"]))

    return {
        "municipios": int(len(t)),
        "por_tamano": por_tamano.to_dict("records"),
        "poblacion_pequena": {
            "umbral_afiliados": umbral_pequena,
            "municipios": int(len(pequenos)),
            "ips_x_10mil_mediana": round(mediana_pequenos, 3),
            "ips_x_10mil_mediana_nacional": round(mediana_nacional, 3),
            "lista": _lista(pequenos, ["ips_x_10mil", "sedes_ips"], "ips_x_10mil"),
        },
        "vulnerables_bajo": {
            "vulnerables": int(len(vulnerables)),
            "en_nivel_bajo": int(len(vulnerables_bajo)),
            "afiliados": int(vulnerables_bajo["afiliados"].sum()),
            "lista": _lista(
                vulnerables_bajo, ["pct_rural", "pct_subsidiado", "pct_intervenidas"], "afiliados"
            ),
        },
        "incertidumbre_top10": {
            "rango": [inc_min, inc_max],
            "municipios": int(len(inciertos)),
            "lista": _lista(inciertos, ["prob_top10"], "indice_riesgo"),
        },
        "spearman_indice": {k: round(v, 3) for k, v in correlaciones.items()},
        "departamentos_sin_alto": sin_alto,
        "alertas": alertas,
    }


def metricas(r: dict) -> dict:
    """Números para MLflow: así se ve en el tiempo si un sesgo crece o se corrige."""
    return {
        "eq_vulnerables_en_bajo": r["vulnerables_bajo"]["en_nivel_bajo"],
        "eq_pequenos_oferta_inflada": r["poblacion_pequena"]["municipios"],
        "eq_inciertos_top10": r["incertidumbre_top10"]["municipios"],
        **{f"eq_spearman_{k}": v for k, v in r["spearman_indice"].items()},
    }


def _fmt(x, d=0) -> str:
    """Números en formato colombiano: 1.234.567 y 0,98."""
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x) -> str:
    return f"{_fmt(100 * x, 0)} %"


def _nombre(x: str) -> str:
    return x.title() if x.isupper() else x


def informe_markdown(r: dict) -> str:
    tam = "\n".join(
        f"| {f['banda']} | {_fmt(f['municipios'])} | {_fmt(f['indice_promedio'], 1)} | "
        f"{_pct(f['pct_muy_alto'])} | {_fmt(f['ips_x_10mil_mediana'], 1)} |"
        for f in r["por_tamano"]
    )
    pq = r["poblacion_pequena"]
    vb = r["vulnerables_bajo"]
    vb_lista = "\n".join(
        f"| {_nombre(f['nom_mpio'])} | {_nombre(f['dpto'])} | {_fmt(f['afiliados'])} | "
        f"{_fmt(f['indice_riesgo'], 1)} | {_pct(f['pct_rural'])} | {_pct(f['pct_subsidiado'])} |"
        for f in vb["lista"][:10]
    )
    inc = r["incertidumbre_top10"]
    sp = r["spearman_indice"]
    alertas = "\n".join(f"- {a}" for a in r["alertas"]) or "- Sin alertas."
    return f"""# Auditoría de equidad del corte

## Alertas
{alertas}

## 1. Índice según el tamaño del municipio
| Afiliados | Municipios | Índice promedio | % en Muy alto | IPS por 10.000 (mediana) |
|---|---|---|---|---|
{tam}

## 2. Municipios muy pequeños (menos de {_fmt(pq["umbral_afiliados"])} afiliados)
{pq["municipios"]} municipios. Oferta mediana: {_fmt(pq["ips_x_10mil_mediana"], 1)} IPS por 10.000 afiliados
(país: {_fmt(pq["ips_x_10mil_mediana_nacional"], 1)}). Una sola sede en un municipio de 500 personas equivale
a 20 por 10.000: la medida no ve la distancia ni el tiempo de viaje.

## 3. Municipios vulnerables en nivel Bajo
{vb["en_nivel_bajo"]} de {vb["vulnerables"]} municipios vulnerables ({_fmt(vb["afiliados"])} afiliados).
El índice mide el riesgo que crea la intervención de EPS; estos municipios pueden tener problemas
de acceso por otras causas.

| Municipio | Departamento | Afiliados | Índice | % rural | % subsidiado |
|---|---|---|---|---|---|
{vb_lista}

## 4. Incertidumbre
{inc["municipios"]} municipios tienen una probabilidad de estar en el 10 % de mayor riesgo entre
{_pct(inc["rango"][0])} y {_pct(inc["rango"][1])} al mover los pesos: su posición depende de la decisión del equipo.

## 5. Correlación del índice con cada rasgo (Spearman)
- % en EPS intervenidas: {_fmt(sp["pct_intervenidas"], 2)}
- % rural: {_fmt(sp["pct_rural"], 2)}
- % subsidiado: {_fmt(sp["pct_subsidiado"], 2)}
- Tamaño (log de afiliados): {_fmt(sp["log_afiliados"], 2)}

Departamentos sin ningún municipio en Alto o Muy alto: {", ".join(_nombre(d) for d in r["departamentos_sin_alto"]) or "ninguno"}.
"""


def guardar(r: dict, carpeta: Path) -> None:
    (carpeta / "equidad.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "equidad.md").write_text(informe_markdown(r), encoding="utf-8")
