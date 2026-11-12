"""Cruce del índice con la vulnerabilidad social, con una rúbrica fijada de antemano.

Fuentes oficiales, descargadas en cada corte (nada se copia a mano ni lo busca la IA):
- DANE: medida de pobreza multidimensional municipal de fuente censal (CNPV 2018): IPM total,
  urbano y rural, y la privación "barreras de acceso a servicios de salud".
- Agencia de Renovación del Territorio: los 170 municipios PDET (datos.gov.co).

Las hipótesis, las pruebas y los umbrales están en config.yaml (vulnerabilidad.rubrica) y se
registraron antes de calcular cualquier cruce. Este módulo solo las evalúa. La IA (opcional)
redacta la lectura con los resultados ya calculados.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import requests
from scipy.stats import binomtest, fisher_exact, spearmanr

from .config import ruta

HOJA_IPM = "4_IPM Mpio dominios"
HOJA_PRIVACIONES = "6_Privaciones IPM Dpt-Mpio"


def _coma(x) -> str:
    return str(x).replace(".", ",")


def sin_nan(x):
    """JSON válido: los NaN de pandas (municipios sin dato, como los creados después del censo) -> null."""
    if isinstance(x, dict):
        return {k: sin_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [sin_nan(v) for v in x]
    if isinstance(x, float) and np.isnan(x):
        return None
    return x


# --- Fuentes -----------------------------------------------------------------------------------


def leer_ipm(contenido: bytes) -> pd.DataFrame:
    """IPM municipal y privaciones de salud desde el anexo del DANE (xlsx)."""
    ipm = pd.read_excel(io.BytesIO(contenido), sheet_name=HOJA_IPM, dtype={"ID": str})
    ipm = ipm[ipm["ID"].astype(str).str.fullmatch(r"\d{5}")]
    ipm = ipm.rename(
        columns={
            "ID": "cod_mpio",
            "IPM": "ipm",
            "Cabeceras": "ipm_cabecera",
            "IPM Centros poblados y rural disperso": "ipm_rural",
        }
    )[["cod_mpio", "ipm", "ipm_cabecera", "ipm_rural"]]
    priv = pd.read_excel(io.BytesIO(contenido), sheet_name=HOJA_PRIVACIONES, header=1, dtype={"ID": str})
    priv = priv[priv["ID"].astype(str).str.fullmatch(r"\d{5}")].drop_duplicates("ID")
    priv = priv.rename(
        columns={
            "ID": "cod_mpio",
            "Barreras de acceso a servicios de salud": "barreras_salud",
            "Sin aseguramiento en salud": "sin_aseguramiento",
        }
    )[["cod_mpio", "barreras_salud", "sin_aseguramiento"]]
    salida = ipm.merge(priv, on="cod_mpio", how="left")
    for c in salida.columns[1:]:
        salida[c] = pd.to_numeric(salida[c], errors="coerce")
    return salida


def descargar(cfg: dict, fecha: str) -> tuple[pd.DataFrame, set[str]]:
    """Descarga (o lee de la caché del corte) el IPM del DANE y la lista PDET."""
    f = cfg["vulnerabilidad"]["fuentes"]
    carpeta = ruta(cfg, "raw", fecha)
    xlsx = carpeta / "dane_ipm_municipal_2018.xlsx"
    if not xlsx.exists():
        r = requests.get(f["ipm_url"], timeout=180, headers={"User-Agent": "riesgo-acceso-salud"})
        r.raise_for_status()
        xlsx.write_bytes(r.content)
    ipm = leer_ipm(xlsx.read_bytes())

    pdet_csv = carpeta / "pdet.csv"
    if not pdet_csv.exists():
        url = f"{cfg['fuente']['base_url']}{f['pdet_dataset']}.json"
        r = requests.get(url, params={"$limit": 5000}, timeout=120)
        r.raise_for_status()
        pd.DataFrame(r.json()).to_csv(pdet_csv, index=False)
    pdet_df = pd.read_csv(pdet_csv, dtype=str)
    col = next(c for c in pdet_df.columns if c.lower() in ("cod_muni", "codigomunicipio", "cod_mpio"))
    pdet = set(pdet_df[col].str.zfill(5))
    return ipm, pdet


# --- Evaluación de la rúbrica ---------------------------------------------------------------------


def _veredicto(rho: float, p: float, h: dict, alfa: float) -> str:
    if p < alfa and rho >= h["se_cumple_si_rho_mayor_o_igual"]:
        return "se_cumple"
    if p < alfa and rho >= h["debil_si_rho_mayor_o_igual"]:
        return "debil"
    return "no_se_cumple"


def evaluar(municipios: pd.DataFrame, ipm: pd.DataFrame, pdet: set[str], cfg: dict) -> dict:
    """Evalúa H1-H4 tal como quedaron registradas en config.yaml."""
    rub = cfg["vulnerabilidad"]["rubrica"]
    alfa = rub["alfa"]
    m = municipios.copy()
    m["cod_mpio"] = m["cod_mpio"].astype(str).str.zfill(5)
    t = m.merge(ipm, on="cod_mpio", how="left")
    t["pdet"] = t["cod_mpio"].isin(pdet)
    res = {"municipios": int(len(t)), "con_ipm": int(t["ipm"].notna().sum()), "pdet": int(t["pdet"].sum())}

    hip = {}
    for clave in ("H1_pobreza", "H3_barreras_salud"):
        h = rub[clave]
        d = t[["indice_riesgo", h["variable"]]].dropna()
        rho, p = spearmanr(d["indice_riesgo"], d[h["variable"]])
        hip[clave] = {
            "descripcion": h["descripcion"],
            "prueba": "Correlación de Spearman",
            "estadistico": round(float(rho), 3),
            "p_valor": float(f"{p:.3g}"),
            "n": int(len(d)),
            "umbral": f"rho ≥ {h['se_cumple_si_rho_mayor_o_igual']} y p < {alfa}",
            "resultado": _veredicto(float(rho), float(p), h, alfa),
        }

    h = rub["H2_pdet"]
    muy = t["nivel_riesgo"] == "Muy alto"
    a, b = int((t["pdet"] & muy).sum()), int((t["pdet"] & ~muy).sum())
    c, d = int((~t["pdet"] & muy).sum()), int((~t["pdet"] & ~muy).sum())
    p_pdet, p_resto = a / max(a + b, 1), c / max(c + d, 1)
    razon = p_pdet / p_resto if p_resto else float("inf")
    _, p = fisher_exact([[a, b], [c, d]], alternative="greater")
    hip["H2_pdet"] = {
        "descripcion": h["descripcion"],
        "prueba": "Prueba exacta de Fisher (una cola)",
        "estadistico": round(float(razon), 2),
        "p_valor": float(f"{p:.3g}"),
        "detalle": f"Muy alto: {a} de {a + b} PDET ({_coma(f'{p_pdet:.1%}')}) frente a {c} de {c + d} no PDET"
        f" ({_coma(f'{p_resto:.1%}')})",
        "umbral": f"razón ≥ {h['razon_minima']} y p < {alfa}",
        "resultado": "se_cumple" if (razon >= h["razon_minima"] and p < alfa) else "no_se_cumple",
    }

    h = rub["H4_doble_vulnerabilidad"]
    d4 = t.dropna(subset=["ipm"]).copy()
    q = h["cuantil"]
    alto_r = d4["indice_riesgo"] >= d4["indice_riesgo"].quantile(q)
    alto_p = d4["ipm"] >= d4["ipm"].quantile(q)
    observados = int((alto_r & alto_p).sum())
    prob = float(alto_r.mean() * alto_p.mean())
    esperados = prob * len(d4)
    p = binomtest(observados, len(d4), prob, alternative="greater").pvalue
    razon = observados / esperados if esperados else float("inf")
    doble = d4[alto_r & alto_p].sort_values("indice_riesgo", ascending=False)
    hip["H4_doble_vulnerabilidad"] = {
        "descripcion": h["descripcion"],
        "prueba": "Prueba binomial frente a la independencia (una cola)",
        "estadistico": round(float(razon), 2),
        "p_valor": float(f"{p:.3g}"),
        "detalle": f"{observados} municipios observados frente a {esperados:.0f} esperados por azar",
        "umbral": f"observados/esperados ≥ {h['razon_minima']} y p < {alfa}",
        "resultado": "se_cumple" if (razon >= h["razon_minima"] and p < alfa) else "no_se_cumple",
    }
    res["hipotesis"] = hip
    res["fecha_registro_rubrica"] = rub["fecha_registro"]

    cols = ["cod_mpio", "nom_mpio", "dpto", "indice_riesgo", "nivel_riesgo", "ipm", "afiliados", "pdet"]
    res["doble_vulnerabilidad"] = {
        "municipios": observados,
        "afiliados": int(doble["afiliados"].sum()),
        "pdet": int(doble["pdet"].sum()),
        "lista": [
            {k: (bool(v) if isinstance(v, (bool, np.bool_)) else v) for k, v in r.items()}
            for r in doble[cols].head(40).round({"indice_riesgo": 1, "ipm": 1}).to_dict("records")
        ],
    }
    res["por_grupo"] = (
        t.groupby("nombre_grupo")
        .agg(
            municipios=("cod_mpio", "size"),
            ipm_mediana=("ipm", "median"),
            barreras_mediana=("barreras_salud", "median"),
            pct_pdet=("pdet", "mean"),
        )
        .round(3)
        .reset_index()
        .to_dict("records")
    )
    res["por_municipio"] = (
        t[["cod_mpio", "ipm", "barreras_salud", "pdet"]]
        .assign(ipm=lambda x: x["ipm"].round(1), barreras_salud=lambda x: x["barreras_salud"].round(1))
        .to_dict("records")
    )
    return res


ETIQUETA = {"se_cumple": "se cumple", "debil": "relación débil", "no_se_cumple": "no se cumple"}


def respaldo_informe(r: dict) -> str:
    d = r["doble_vulnerabilidad"]
    partes = [
        f"Rúbrica registrada el {r['fecha_registro_rubrica']}, antes de calcular el cruce.",
        *(
            f"{k.split('_', 1)[0]} — {h['descripcion']}: {ETIQUETA[h['resultado']]}"
            f" (valor {_coma(h['estadistico'])}, p = {_coma(h['p_valor'])})."
            for k, h in r["hipotesis"].items()
        ),
        f"{d['municipios']} municipios están a la vez en el 20 % más alto de riesgo y de pobreza,"
        f" con {d['afiliados']:,} afiliados.".replace(",", "."),
        "El IPM es del censo 2018: describe la pobreza estructural, no la situación de 2026.",
    ]
    return " ".join(partes)


def informe(r: dict, gemini) -> str:
    base = respaldo_informe(r)
    if gemini is None:
        return base
    datos = {k: v for k, v in r.items() if k not in ("por_municipio",)}
    datos["doble_vulnerabilidad"] = {
        **r["doble_vulnerabilidad"],
        "lista": r["doble_vulnerabilidad"]["lista"][:10],
    }
    prompt = f"""Redacta en español de Colombia un párrafo de 5 a 7 frases, sin títulos ni viñetas, para
personas no técnicas, sobre si el riesgo de perder el acceso a la salud coincide con la vulnerabilidad
social de los municipios.
Reglas estrictas:
- Usa SOLO los datos de abajo. No inventes cifras, causas ni ejemplos.
- Para cada hipótesis di si se cumple, es débil o no se cumple, en palabras sencillas (sin nombres
  de variables ni "p_valor"; puedes decir "es estadísticamente significativo").
- Aclara que las reglas se fijaron antes de ver los datos.
- Nombra 3 municipios de doble vulnerabilidad si los hay.
- Termina con la limitación: el IPM es del censo 2018.

Datos: {json.dumps(datos, ensure_ascii=False, default=str)}"""
    try:
        return gemini.generar(prompt).strip()
    except Exception as e:  # noqa: BLE001 - la lectura es opcional
        print(f"  [vulnerabilidad] no se pudo redactar la lectura con IA: {e}")
        return base


def etapa(cfg: dict, fecha: str, gemini=None, demo: bool = False) -> dict:
    """Etapa segura del pipeline: si una fuente falla, deja constancia y no bloquea el corte."""
    salida = ruta(cfg, "resultados", fecha)
    if demo:
        return {"estado": "omitido", "motivo": "modo demo"}
    try:
        municipios = pd.read_csv(
            salida / "municipios_riesgo.csv", dtype={"cod_mpio": str}, encoding="utf-8-sig"
        )
        ipm, pdet = descargar(cfg, fecha)
        r = evaluar(municipios, ipm, pdet, cfg)
        r.update(
            {
                "estado": "ok",
                "fecha_corte": fecha,
                "generado": datetime.now(UTC).isoformat(timespec="seconds"),
                "fuentes": {
                    "ipm": "DANE, medida de pobreza multidimensional municipal de fuente censal 2018",
                    "pdet": "Agencia de Renovación del Territorio, municipios PDET (datos.gov.co)",
                },
                "modelo_ia": getattr(gemini, "modelo", None),
            }
        )
        r["informe"] = informe(r, gemini)
        for k, h in r["hipotesis"].items():
            print(
                f"  [vulnerabilidad] {k}: {ETIQUETA[h['resultado']]} ({h['estadistico']}, p={h['p_valor']})"
            )
    except Exception as e:  # noqa: BLE001 - complementario: nunca bloquea la publicación
        r = {"estado": "error", "motivo": f"{type(e).__name__}: {e}"[:300], "fecha_corte": fecha}
        print(f"  [vulnerabilidad] error: {r['motivo']}")
    (salida / "vulnerabilidad.json").write_text(
        json.dumps(sin_nan(r), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
    )
    return r
