"""Fichas de los municipios de mayor riesgo, redactadas por el agente con datos ya calculados.

Cada ficha junta, para un municipio, lo que el pipeline ya sabe de él: índice y componentes, grupo,
EPS principal, oferta de IPS, pobreza (DANE), si es PDET y las noticias del mes que lo mencionan.
La IA solo redacta: no agrega datos. Sin clave de Gemini se arma una ficha con plantilla.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from .config import ruta
from .noticias import normalizar

COMPONENTES = {
    "comp_dependencia": "dependencia de EPS intervenidas",
    "comp_oferta": "baja oferta de IPS",
    "comp_concentracion": "afiliación concentrada en pocas EPS",
    "comp_ruralidad": "ruralidad",
    "comp_subsidiado": "régimen subsidiado",
}

ESQUEMA_FICHA = {
    "type": "OBJECT",
    "properties": {
        "resumen": {"type": "STRING"},
        "por_que": {"type": "ARRAY", "items": {"type": "STRING"}},
        "accion_recomendada": {"type": "STRING"},
        "advertencias": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["resumen", "por_que", "accion_recomendada", "advertencias"],
}

ACCION_GRUPO = {
    1: "Resolver la situación de la EPS principal o preparar la reasignación de afiliados, y reforzar la red pública.",
    2: "Vigilancia preventiva: seguir de cerca la EPS principal y la red de prestadores.",
    3: "Seguimiento normal.",
}


def hechos(m: pd.Series, vul: dict | None, noticias: list[dict]) -> dict:
    """Datos del municipio que puede usar la ficha (y nada más)."""
    comps = sorted(((COMPONENTES[k], round(float(m[k]), 1)) for k in COMPONENTES), key=lambda x: -x[1])
    v = (vul or {}).get(m["cod_mpio"], {})
    nombre = normalizar(m["nom_mpio"])
    propias = [
        n
        for n in noticias
        if n.get("relevante") and any(normalizar(x) == nombre for x in n.get("municipios", []))
    ]
    del_dpto = [
        n
        for n in noticias
        if n.get("relevante") and m["dpto"] in n.get("departamentos", []) and n not in propias
    ]
    return {
        "municipio": str(m["nom_mpio"]).title(),
        "departamento": str(m["dpto"]).title(),
        "cod_mpio": m["cod_mpio"],
        "ranking": int(m["ranking_riesgo"]),
        "indice_riesgo": round(float(m["indice_riesgo"]), 1),
        "nivel_riesgo": m["nivel_riesgo"],
        "grupo": m["nombre_grupo"],
        "afiliados": int(m["afiliados"]),
        "pct_en_eps_intervenidas": round(float(m["pct_intervenidas"]) * 100, 1),
        "eps_principal": m["eps_principal"],
        "pct_eps_principal": round(float(m["pct_eps_principal"]) * 100, 1),
        "eps_principal_intervenida": bool(m["eps_principal_intervenida"]),
        "numero_eps": int(m["n_eps"]),
        "sedes_ips": int(m["sedes_ips"]),
        "ips_por_10mil_afiliados": round(float(m["ips_x_10mil"]), 2),
        "pct_rural": round(float(m["pct_rural"]) * 100, 1),
        "pct_subsidiado": round(float(m["pct_subsidiado"]) * 100, 1),
        "prob_estar_en_top10": round(float(m["prob_top10"]) * 100),
        "componentes_de_mayor_a_menor": comps,
        "ipm_dane_2018": v.get("ipm"),
        "barreras_acceso_salud_dane_2018": v.get("barreras_salud"),
        "municipio_pdet": v.get("pdet"),
        "noticias_del_municipio": [
            {"titulo": n["titulo"], "fuente": n["fuente"], "fecha": n["fecha"], "enlace": n["enlace"]}
            for n in propias[:3]
        ],
        "noticias_del_departamento": [
            {"titulo": n["titulo"], "fuente": n["fuente"], "fecha": n["fecha"], "enlace": n["enlace"]}
            for n in del_dpto[:3]
        ],
    }


def num(x, d: int = 1) -> str:
    """Número con coma decimal, como se escribe en Colombia."""
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def plantilla(h: dict, grupo: int) -> dict:
    c = h["componentes_de_mayor_a_menor"]
    por_que = [
        f"El {num(h['pct_en_eps_intervenidas'], 0)} % de sus afiliados está en EPS intervenidas; la principal es "
        f"{h['eps_principal']} ({num(h['pct_eps_principal'], 0)} %).",
        f"Tiene {num(h['ips_por_10mil_afiliados'], 2)} sedes de IPS por cada 10.000 afiliados.",
        f"Los componentes que más pesan son {c[0][0]} y {c[1][0]}.",
    ]
    if h["ipm_dane_2018"] is not None:
        por_que.append(f"Pobreza multidimensional (DANE 2018): {num(h['ipm_dane_2018'])} %.")
    return {
        "resumen": f"{h['municipio']} ({h['departamento']}) ocupa el puesto {h['ranking']} de riesgo, con un índice de "
        f"{num(h['indice_riesgo'])} sobre 100.",
        "por_que": por_que,
        "accion_recomendada": ACCION_GRUPO.get(grupo, ACCION_GRUPO[3]),
        "advertencias": ["Se cuentan sedes de IPS, no camas ni especialistas, y no se mide la distancia."],
    }


def redactar(h: dict, grupo: int, gemini) -> dict:
    if gemini is None:
        return plantilla(h, grupo)
    prompt = f"""Eres analista de salud pública. Redacta una ficha breve, en español de Colombia y en lenguaje
sencillo, para una secretaría de salud sobre el riesgo de que la población de este municipio pierda el
acceso a la salud.
Reglas estrictas:
- Usa SOLO los datos del JSON. No inventes cifras, causas, nombres de hospitales ni noticias.
- resumen: 2 frases. por_que: 3 o 4 razones concretas con cifras del JSON. accion_recomendada: 1 o 2
  frases, coherentes con esta acción de su grupo: "{ACCION_GRUPO.get(grupo, ACCION_GRUPO[3])}".
- advertencias: 1 o 2 límites de los datos (por ejemplo: se cuentan sedes, no camas; IPM de 2018;
  las noticias son del departamento y no necesariamente del municipio).
- Si hay noticias, puedes mencionarlas solo como contexto y sin exagerar.

Datos: {json.dumps(h, ensure_ascii=False)}"""
    try:
        return {**plantilla(h, grupo), **json.loads(gemini.generar(prompt, ESQUEMA_FICHA))}
    except Exception as e:  # noqa: BLE001 - si falla, queda la plantilla
        print(f"  [fichas] {h['municipio']}: se usa plantilla ({e})")
        return plantilla(h, grupo)


def etapa(cfg: dict, fecha: str, gemini=None, demo: bool = False) -> dict:
    salida = ruta(cfg, "resultados", fecha)
    if demo:
        return {"estado": "omitido", "motivo": "modo demo"}
    try:
        n = cfg.get("fichas", {}).get("municipios", 5)
        mun = pd.read_csv(salida / "municipios_riesgo.csv", dtype={"cod_mpio": str}, encoding="utf-8-sig")
        top = mun.sort_values("ranking_riesgo").head(n)
        vul, noticias = None, []
        if (salida / "vulnerabilidad.json").exists():
            v = json.loads((salida / "vulnerabilidad.json").read_text(encoding="utf-8"))
            vul = {r["cod_mpio"]: r for r in v.get("por_municipio", [])}
        if (salida / "noticias.json").exists():
            noticias = json.loads((salida / "noticias.json").read_text(encoding="utf-8"))
        fichas = []
        for _, m in top.iterrows():
            h = hechos(m, vul, noticias)
            fichas.append({"hechos": h, **redactar(h, int(m["grupo"]), gemini)})
        r = {
            "estado": "ok",
            "fecha_corte": fecha,
            "generado": datetime.now(UTC).isoformat(timespec="seconds"),
            "redactado_por": getattr(gemini, "modelo", None) or "plantilla",
            "fichas": fichas,
        }
        print(f"  [fichas] {len(fichas)} fichas ({r['redactado_por']})")
    except Exception as e:  # noqa: BLE001
        r = {"estado": "error", "motivo": f"{type(e).__name__}: {e}"[:300], "fecha_corte": fecha}
        print(f"  [fichas] error: {r['motivo']}")
    (salida / "fichas_municipios.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return r
