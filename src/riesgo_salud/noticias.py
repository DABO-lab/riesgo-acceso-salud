"""Agente de noticias: contrasta el índice de riesgo con lo que pasa en la prensa.

Tres pasos, con responsabilidades separadas para que el resultado sea verificable:

1. Buscar (código): noticias recientes de Google Noticias sobre las EPS intervenidas y la crisis
   de salud. Consultas nacionales, iguales para todos los departamentos, para no sesgar el contraste.
2. Leer y clasificar (IA, Gemini): de cada noticia extrae EPS, departamentos, municipios, tipo de
   problema y gravedad. Se guarda el enlace de cada noticia como evidencia.
3. Contrastar (código, no IA): agrega las menciones por departamento y calcula la correlación de
   Spearman con el índice. La IA solo redacta el resumen a partir de esas cifras: no las calcula.

Si no hay GEMINI_API_KEY o algo falla, la etapa se omite y el pipeline sigue: el contraste con
noticias es complementario y nunca bloquea la publicación de un corte.

Uso fuera del pipeline (sobre un corte ya calculado):
    python -m riesgo_salud.noticias --fecha 2026-11-05
"""

from __future__ import annotations

import argparse
import email.utils
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote_plus

import pandas as pd
import requests
from scipy.stats import spearmanr

from .config import cargar_config, ruta

API_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
RSS_GOOGLE = "https://news.google.com/rss/search?q={q}&hl=es-419&gl=CO&ceid=CO:es-419"
TIPOS = [
    "medicamentos",
    "cierre_servicios",
    "deudas_pagos",
    "tutelas_quejas",
    "intervencion_supersalud",
    "protesta",
    "otro",
]


class SinClave(RuntimeError):
    """No hay GEMINI_API_KEY: la etapa se omite."""


def normalizar(texto: str) -> str:
    """Mayúsculas, sin tildes ni signos: "Bogotá, D.C." y "BOGOTA D C" quedan iguales."""
    t = unicodedata.normalize("NFD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", t.upper()).split())


# --- 1. Buscar -------------------------------------------------------------------------------


def consultas(cfg: dict) -> list[str]:
    c = cfg["noticias"]
    eps = [f'"{e}"' if " " in e else e for e in cfg["eps_intervenidas"]["lista"]]
    eps = [("EPS SOS" if e == "SOS" else e) for e in eps]  # "SOS" solo es ambiguo
    return [f"{e} {c['sufijo_eps']}" for e in eps] + list(c["consultas_generales"])


def parsear_rss(xml: str, consulta: str) -> list[dict]:
    """Noticias de un feed RSS de Google Noticias."""
    salida = []
    for item in ET.fromstring(xml).iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fuente = (item.findtext("source") or "").strip()
        if fuente and titulo.endswith(f" - {fuente}"):
            titulo = titulo[: -len(fuente) - 3].strip()
        fecha = item.findtext("pubDate")
        try:
            fecha = email.utils.parsedate_to_datetime(fecha).astimezone(UTC).date().isoformat()
        except (TypeError, ValueError):
            fecha = None
        salida.append(
            {
                "titulo": titulo,
                "fuente": fuente,
                "fecha": fecha,
                "enlace": item.findtext("link"),
                "consulta": consulta,
            }
        )
    return salida


def buscar(cfg: dict, fecha_corte: str, obtener=None) -> list[dict]:
    """Noticias de los últimos `dias_atras` días antes del corte, sin duplicados."""
    c = cfg["noticias"]
    obtener = obtener or (lambda url: requests.get(url, timeout=30).text)
    desde = date.fromisoformat(fecha_corte) - timedelta(days=c["dias_atras"])
    vistas, salida = set(), []
    for q in consultas(cfg):
        url = RSS_GOOGLE.format(q=quote_plus(f"{q} when:{c['dias_atras']}d"))
        try:
            items = parsear_rss(obtener(url), q)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"  [noticias] no se pudo leer la consulta {q!r}: {e}")
            continue
        for it in items:
            clave = normalizar(it["titulo"])[:90]
            if not clave or clave in vistas:
                continue
            if it["fecha"] and (it["fecha"] < desde.isoformat() or it["fecha"] > fecha_corte):
                continue
            vistas.add(clave)
            salida.append(it)
        time.sleep(c.get("pausa_rss_segundos", 1))
    salida.sort(key=lambda x: x["fecha"] or "", reverse=True)
    return salida[: c["max_noticias"]]


# --- 2. Leer y clasificar con Gemini -----------------------------------------------------------


class Gemini:
    """Cliente mínimo de la API de Gemini (nivel gratuito): elige el modelo y respeta los límites."""

    def __init__(self, cfg: dict, clave: str | None = None, sesion=None):
        self.c = cfg["noticias"]
        self.clave = clave or os.environ.get("GEMINI_API_KEY")
        if not self.clave:
            raise SinClave("no hay GEMINI_API_KEY")
        self.http = sesion or requests.Session()
        self.http.headers.update({"x-goog-api-key": self.clave, "Content-Type": "application/json"})
        self.modelos = self._modelos_disponibles()
        self.modelo = self.modelos[0]
        self._ultima = 0.0

    def _modelos_disponibles(self) -> list[str]:
        r = self.http.get(f"{API_GEMINI}/models", params={"pageSize": 200}, timeout=30)
        r.raise_for_status()
        hay = {
            m["name"].split("/", 1)[1]
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        }
        preferidos = [m for m in self.c["modelos_preferidos"] if m in hay]
        # Si cambian los nombres, cualquier "flash" de texto sirve como respaldo
        respaldo = sorted(
            (m for m in hay if "flash" in m and not re.search(r"image|tts|live|audio|preview|exp", m)),
            reverse=True,
        )
        lista = preferidos + [m for m in respaldo if m not in preferidos]
        if not lista:
            raise RuntimeError("Gemini no ofrece ningún modelo flash para generateContent")
        return lista

    def generar(self, prompt: str, esquema: dict | None = None) -> str:
        cuerpo = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
        if esquema:
            cuerpo["generationConfig"].update(
                {"responseMimeType": "application/json", "responseSchema": esquema}
            )
        for intento in range(6):
            espera = self.c["pausa_gemini_segundos"] - (time.time() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.time()
            r = self.http.post(f"{API_GEMINI}/models/{self.modelo}:generateContent", json=cuerpo, timeout=120)
            if r.status_code == 429:  # límite por minuto o cupo diario agotado
                if "per day" in r.text.lower() or "perday" in r.text.lower().replace(" ", ""):
                    self._siguiente_modelo()
                else:
                    time.sleep(20 * (intento + 1))
                continue
            if r.status_code >= 500:
                time.sleep(10 * (intento + 1))
                continue
            r.raise_for_status()
            partes = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in partes)
        raise RuntimeError(f"Gemini no respondió tras varios intentos ({self.modelo})")

    def _siguiente_modelo(self):
        i = self.modelos.index(self.modelo)
        if i + 1 >= len(self.modelos):
            raise RuntimeError("se agotó el cupo diario gratuito de Gemini")
        self.modelo = self.modelos[i + 1]
        print(f"  [noticias] cupo agotado; se cambia al modelo {self.modelo}")


ESQUEMA_CLASIFICACION = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "INTEGER"},
            "relevante": {"type": "BOOLEAN"},
            "eps": {"type": "ARRAY", "items": {"type": "STRING"}},
            "departamentos": {"type": "ARRAY", "items": {"type": "STRING"}},
            "municipios": {"type": "ARRAY", "items": {"type": "STRING"}},
            "tipo": {"type": "STRING", "enum": TIPOS},
            "gravedad": {"type": "INTEGER"},
        },
        "required": ["id", "relevante", "eps", "departamentos", "municipios", "tipo", "gravedad"],
    },
}


def prompt_clasificacion(lote: list[dict], departamentos: list[str], eps: list[str]) -> str:
    lineas = "\n".join(f"[{i}] {n['titulo']} ({n['fuente']}, {n['fecha']})" for i, n in lote)
    return f"""Eres un analista de salud pública en Colombia. Clasifica cada titular de noticia.

Para cada uno responde:
- relevante: true solo si trata de problemas de acceso a la salud en Colombia ligados a EPS, IPS,
  hospitales, medicamentos o la Supersalud. Deportes, política sin efecto en servicios u otros
  países: false.
- eps: EPS mencionadas, escritas exactamente como en esta lista si están en ella: {", ".join(eps)}.
- departamentos: departamentos de Colombia donde ocurre el hecho, escritos como en esta lista:
  {", ".join(departamentos)}. Si un municipio se menciona, incluye su departamento. Si es nacional
  o no se sabe, deja la lista vacía. No adivines.
- municipios: municipios mencionados (vacío si ninguno).
- tipo: uno de {", ".join(TIPOS)}.
- gravedad: 1 = advertencia o anuncio, 2 = afectación en curso, 3 = pacientes sin atención o
  servicios cerrados.
Usa solo lo que dice el titular. Devuelve un elemento por titular con su id.

Titulares:
{lineas}"""


def clasificar(noticias: list[dict], cfg: dict, departamentos: list[str], gemini: Gemini) -> list[dict]:
    canon_dpto = {normalizar(d): d for d in departamentos}
    canon_eps = {normalizar(e): e for e in cfg["eps_intervenidas"]["lista"]}
    tam = cfg["noticias"]["tamano_lote"]
    numeradas = list(enumerate(noticias))
    for ini in range(0, len(numeradas), tam):
        lote = numeradas[ini : ini + tam]
        texto = gemini.generar(
            prompt_clasificacion(lote, departamentos, cfg["eps_intervenidas"]["lista"]), ESQUEMA_CLASIFICACION
        )
        for r in json.loads(texto):
            i = r.get("id")
            if not isinstance(i, int) or not 0 <= i < len(noticias):
                continue
            n = noticias[i]
            n["relevante"] = bool(r.get("relevante"))
            n["eps"] = sorted({canon_eps.get(normalizar(e), e.upper()) for e in r.get("eps", []) if e})
            n["departamentos"] = sorted(
                {canon_dpto[normalizar(d)] for d in r.get("departamentos", []) if normalizar(d) in canon_dpto}
            )
            n["municipios"] = [m for m in r.get("municipios", []) if m]
            n["tipo"] = r.get("tipo") if r.get("tipo") in TIPOS else "otro"
            n["gravedad"] = min(3, max(1, int(r.get("gravedad") or 1)))
        print(f"  [noticias] clasificadas {min(ini + tam, len(noticias))}/{len(noticias)} ({gemini.modelo})")
    for n in noticias:  # las que el modelo no devolvió quedan fuera del contraste
        n.setdefault("relevante", None)
    return noticias


# --- 3. Contrastar (código) ----------------------------------------------------------------------


def contrastar(noticias: list[dict], deptos: pd.DataFrame, cfg: dict) -> dict:
    """Menciones por departamento frente al índice: correlación y casos que coinciden o no."""
    rel = [n for n in noticias if n.get("relevante")]
    filas = []
    for _, d in deptos.iterrows():
        sus = [n for n in rel if d["dpto"] in n.get("departamentos", [])]
        filas.append(
            {
                "dpto": d["dpto"],
                "indice_ponderado": round(float(d["indice_ponderado"]), 2),
                "municipios_muy_alto": int(d["municipios_muy_alto"]),
                "afiliados": int(d["afiliados"]),
                "menciones": len(sus),
                "senal": sum(n["gravedad"] for n in sus),
            }
        )
    t = pd.DataFrame(filas)
    t["afiliados_intervenidas"] = (
        (deptos["afiliados"] * deptos["pct_intervenidas"]).round().astype(int).values
    )

    con_mencion = int((t["menciones"] > 0).sum())
    corr = {
        "departamentos_con_noticias": con_mencion,
        "suficiente": con_mencion >= cfg["noticias"]["min_departamentos"],
    }
    if corr["suficiente"]:
        rho, p = spearmanr(t["indice_ponderado"], t["senal"])
        rho_tam, p_tam = spearmanr(t["afiliados_intervenidas"], t["senal"])
        corr.update(
            {
                "spearman_indice": round(float(rho), 3),
                "p_valor_indice": round(float(p), 4),
                "spearman_tamano": round(float(rho_tam), 3),
                "p_valor_tamano": round(float(p_tam), 4),
                "lectura": lectura_correlacion(float(rho), float(p)),
            }
        )
    else:
        corr["lectura"] = "Muy pocos departamentos con noticias: no alcanza para medir una correlación."

    alto = t["indice_ponderado"] >= t["indice_ponderado"].quantile(2 / 3)
    bajo = t["indice_ponderado"] <= t["indice_ponderado"].quantile(1 / 3)
    umbral = max(1, t.loc[t["senal"] > 0, "senal"].median()) if con_mencion else 1
    t["categoria"] = "sin_contraste"
    t.loc[alto & (t["senal"] >= umbral), "categoria"] = "coinciden"
    t.loc[alto & (t["menciones"] == 0), "categoria"] = "riesgo_silencioso"
    t.loc[bajo & (t["senal"] >= umbral), "categoria"] = "posible_punto_ciego"

    eps = {}
    for n in rel:
        for e in n.get("eps", []):
            eps[e] = eps.get(e, 0) + 1
    intervenidas = set(cfg["eps_intervenidas"]["lista"])
    sobre_intervenidas = sum(1 for n in rel if intervenidas & set(n.get("eps", [])))
    return {
        "noticias_total": len(noticias),
        "noticias_relevantes": len(rel),
        "noticias_nacionales": sum(1 for n in rel if not n.get("departamentos")),
        "pct_sobre_eps_intervenidas": round(sobre_intervenidas / len(rel), 3) if rel else None,
        "por_tipo": pd.Series([n["tipo"] for n in rel], dtype=str).value_counts().to_dict(),
        "menciones_eps": dict(sorted(eps.items(), key=lambda x: -x[1])),
        "correlacion": corr,
        "departamentos": t.sort_values(["senal", "indice_ponderado"], ascending=False).to_dict("records"),
    }


def lectura_correlacion(rho: float, p: float) -> str:
    r = f"{rho:.2f}".replace(".", ",")
    sig = "estadísticamente significativa" if p < 0.05 else "no significativa (p ≥ 0,05)"
    if abs(rho) < 0.1:
        return f"Sin correlación entre noticias e índice (Spearman {r}), {sig}."
    fuerza = "débil" if abs(rho) < 0.3 else "moderada" if abs(rho) < 0.5 else "fuerte"
    sentido = "positiva" if rho > 0 else "negativa"
    return f"Correlación {fuerza} {sentido} (Spearman {r}), {sig}."


def informe(contraste: dict, noticias: list[dict], gemini: Gemini | None) -> str:
    """Resumen en lenguaje sencillo. La IA lo redacta solo con las cifras ya calculadas."""
    base = respaldo_informe(contraste)
    if gemini is None:
        return base
    destacadas = [
        f"- {n['titulo']} ({n['fuente']}, {n['fecha']}; {', '.join(n['departamentos']) or 'nacional'})"
        for n in sorted((n for n in noticias if n.get("relevante")), key=lambda n: -n["gravedad"])[:12]
    ]
    datos = {k: v for k, v in contraste.items() if k != "departamentos"}
    datos["departamentos"] = [d for d in contraste["departamentos"] if d["categoria"] != "sin_contraste"][:15]
    prompt = f"""Redacta en español de Colombia un resumen de 5 a 7 frases, sin títulos ni viñetas,
para un equipo que mide el riesgo de perder el acceso a la salud por municipio.
Reglas estrictas:
- Usa SOLO las cifras y hechos de los datos de abajo. No inventes cifras, causas ni noticias.
- Di con claridad si hay correlación o no entre las noticias y el índice, tal como dice "lectura".
- Si spearman_tamano es mayor que spearman_indice, advierte que las noticias siguen más el tamaño
  de la población que el riesgo.
- Menciona los departamentos que coinciden, los de riesgo silencioso (riesgo alto sin noticias) y
  los posibles puntos ciegos (noticias con riesgo bajo), si los hay.
- Termina con una limitación: la prensa cubre más las ciudades y las EPS grandes.

Datos del contraste: {json.dumps(datos, ensure_ascii=False)}
Titulares más graves:
{chr(10).join(destacadas)}"""
    try:
        return gemini.generar(prompt).strip()
    except Exception as e:  # noqa: BLE001 - el resumen es opcional
        print(f"  [noticias] no se pudo redactar el resumen con IA: {e}")
        return base


def respaldo_informe(c: dict) -> str:
    cats = {}
    for d in c["departamentos"]:
        cats.setdefault(d["categoria"], []).append(d["dpto"].title())
    partes = [
        f"Se revisaron {c['noticias_total']} noticias; {c['noticias_relevantes']} tratan de problemas de acceso a la salud.",
        c["correlacion"]["lectura"],
    ]
    for k, txt in [
        ("coinciden", "Coinciden riesgo alto y noticias en"),
        ("riesgo_silencioso", "Riesgo alto sin noticias (riesgo silencioso) en"),
        ("posible_punto_ciego", "Noticias con riesgo bajo (posible punto ciego) en"),
    ]:
        if cats.get(k):
            partes.append(f"{txt}: {', '.join(cats[k][:8])}.")
    partes.append(
        "La prensa cubre más las ciudades y las EPS grandes: la ausencia de noticias no significa ausencia de problemas."
    )
    return " ".join(partes)


# --- Etapa del pipeline ---------------------------------------------------------------------------


def ejecutar(cfg: dict, fecha: str, gemini: Gemini | None = None, obtener=None) -> dict:
    """Busca, clasifica, contrasta y guarda contraste_noticias.json y noticias.json en el corte."""
    gemini = gemini or Gemini(cfg)  # primero: sin clave no se hace nada más
    salida = ruta(cfg, "resultados", fecha)
    deptos = pd.read_csv(salida / "resumen_departamentos.csv", encoding="utf-8-sig")
    noticias = buscar(cfg, fecha, obtener)
    print(f"  [noticias] {len(noticias)} noticias encontradas")
    if not noticias:
        raise RuntimeError("no se encontraron noticias")
    clasificar(noticias, cfg, sorted(deptos["dpto"]), gemini)
    contraste = contrastar(noticias, deptos, cfg)
    contraste.update(
        {
            "estado": "ok",
            "fecha_corte": fecha,
            "generado": datetime.now(UTC).isoformat(timespec="seconds"),
            "ventana_dias": cfg["noticias"]["dias_atras"],
            "modelo_ia": gemini.modelo,
            "consultas": consultas(cfg),
            "informe": informe(contraste, noticias, gemini),
        }
    )
    (salida / "noticias.json").write_text(
        json.dumps(noticias, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (salida / "contraste_noticias.json").write_text(
        json.dumps(contraste, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [noticias] {contraste['correlacion']['lectura']}")
    return contraste


def etapa(cfg: dict, fecha: str, demo: bool = False) -> dict:
    """Versión segura para el pipeline: si falla o no hay clave, deja constancia y sigue."""
    salida = ruta(cfg, "resultados", fecha)
    if demo or not cfg.get("noticias", {}).get("activo", False):
        return {"estado": "omitido", "motivo": "desactivado o modo demo"}
    try:
        return ejecutar(cfg, fecha)
    except SinClave:
        estado = {"estado": "omitido", "motivo": "no hay GEMINI_API_KEY configurada"}
    except Exception as e:  # noqa: BLE001 - nunca bloquea la publicación del corte
        estado = {"estado": "error", "motivo": f"{type(e).__name__}: {e}"[:300]}
    print(f"  [noticias] {estado['estado']}: {estado['motivo']}")
    if not (salida / "contraste_noticias.json").exists():
        (salida / "contraste_noticias.json").write_text(
            json.dumps({**estado, "fecha_corte": fecha}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return estado


def main(argv=None):
    ap = argparse.ArgumentParser(description="Contraste del índice con noticias recientes (Gemini)")
    ap.add_argument("--fecha", required=True, help="corte ya calculado en resultados/<fecha>/")
    a = ap.parse_args(argv)
    cfg = cargar_config()
    r = ejecutar(cfg, a.fecha)
    print("\n" + r["informe"])


if __name__ == "__main__":
    main()
