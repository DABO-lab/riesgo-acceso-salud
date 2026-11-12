"""Agente de noticias sin internet: el RSS y Gemini se simulan."""

import json

import pandas as pd
import pytest

from riesgo_salud import noticias

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Pacientes de Asmet Salud sin medicamentos en Popayán - El Tiempo</title>
<link>https://ejemplo.co/1</link><pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate><source>El Tiempo</source></item>
<item><title>Pacientes de Asmet Salud sin medicamentos en Popayán - Semana</title>
<link>https://ejemplo.co/1b</link><pubDate>Mon, 03 Nov 2026 11:00:00 GMT</pubDate><source>Semana</source></item>
<item><title>Nueva EPS cierra convenio con hospital de Cúcuta - La Opinión</title>
<link>https://ejemplo.co/2</link><pubDate>Sun, 02 Nov 2026 09:00:00 GMT</pubDate><source>La Opinión</source></item>
<item><title>Final del fútbol colombiano - Caracol</title>
<link>https://ejemplo.co/3</link><pubDate>Sat, 01 Nov 2026 09:00:00 GMT</pubDate><source>Caracol</source></item>
<item><title>Noticia vieja de Coosalud - El Heraldo</title>
<link>https://ejemplo.co/4</link><pubDate>Mon, 01 Sep 2026 09:00:00 GMT</pubDate><source>El Heraldo</source></item>
</channel></rss>"""


class GeminiFalso:
    """Imita al cliente: clasifica por palabras clave y redacta un resumen fijo."""

    modelo = "gemini-falso"

    def generar(self, prompt, esquema=None):
        if esquema is None:
            return "Resumen de prueba."
        filas = [ln for ln in prompt.splitlines() if ln.startswith("[")]
        salida = []
        for ln in filas:
            i = int(ln[1 : ln.index("]")])
            if "Asmet" in ln:
                r = {
                    "relevante": True,
                    "eps": ["Asmet Salud"],
                    "departamentos": ["cauca"],
                    "tipo": "medicamentos",
                    "gravedad": 3,
                }
            elif "Nueva EPS" in ln:
                r = {
                    "relevante": True,
                    "eps": ["NUEVA EPS"],
                    "departamentos": ["Norte de Santander"],
                    "tipo": "cierre_servicios",
                    "gravedad": 2,
                }
            else:
                r = {"relevante": False, "eps": [], "departamentos": [], "tipo": "otro", "gravedad": 1}
            salida.append({"id": i, "municipios": [], **r})
        return json.dumps(salida)


@pytest.fixture
def cfg_noticias(cfg_copia):
    cfg_copia["noticias"].update({"consultas_generales": [], "pausa_rss_segundos": 0, "min_departamentos": 2})
    cfg_copia["eps_intervenidas"]["lista"] = ["NUEVA EPS", "ASMET SALUD"]
    return cfg_copia


def test_parsear_rss_quita_la_fuente_del_titulo():
    items = noticias.parsear_rss(RSS, "q")
    assert items[0]["titulo"] == "Pacientes de Asmet Salud sin medicamentos en Popayán"
    assert items[0]["fuente"] == "El Tiempo"
    assert items[0]["fecha"] == "2026-11-03"


def test_buscar_quita_duplicados_y_noticias_viejas(cfg_noticias):
    res = noticias.buscar(cfg_noticias, "2026-11-05", obtener=lambda url: RSS)
    titulos = [n["titulo"] for n in res]
    assert len(titulos) == len(set(titulos)) == 3  # duplicado y la de septiembre fuera
    assert all(n["fecha"] >= "2026-10-06" for n in res)


def test_consultas_desambiguan_sos(cfg_copia):
    q = noticias.consultas(cfg_copia)
    assert any(c.startswith("EPS SOS") for c in q)
    assert any('"NUEVA EPS"' in c for c in q)


def test_clasificar_y_contrastar(cfg_noticias):
    deptos = pd.DataFrame(
        {
            "dpto": ["CAUCA", "NORTE DE SANTANDER", "ANTIOQUIA", "BOGOTÁ, D.C.", "GUAVIARE"],
            "municipios": [42, 40, 125, 1, 4],
            "afiliados": [1_400_000, 1_600_000, 6_500_000, 8_000_000, 86_000],
            "municipios_muy_alto": [11, 2, 5, 0, 3],
            "pct_intervenidas": [0.7, 0.5, 0.3, 0.2, 1.0],
            "indice_ponderado": [49.0, 40.0, 30.0, 10.0, 66.0],
        }
    )
    lista = noticias.buscar(cfg_noticias, "2026-11-05", obtener=lambda url: RSS)
    noticias.clasificar(lista, cfg_noticias, sorted(deptos["dpto"]), GeminiFalso())
    asmet = next(n for n in lista if "Asmet" in n["titulo"])
    assert asmet["departamentos"] == ["CAUCA"]  # normaliza mayúsculas y tildes
    assert asmet["eps"] == ["ASMET SALUD"]

    c = noticias.contrastar(lista, deptos, cfg_noticias)
    assert c["noticias_relevantes"] == 2
    assert c["correlacion"]["suficiente"]
    assert -1 <= c["correlacion"]["spearman_indice"] <= 1
    cat = {d["dpto"]: d["categoria"] for d in c["departamentos"]}
    assert cat["CAUCA"] == "coinciden"
    assert cat["GUAVIARE"] == "riesgo_silencioso"
    assert c["pct_sobre_eps_intervenidas"] == 1.0


def test_etapa_sin_clave_no_rompe_el_pipeline(cfg_noticias, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg_noticias["rutas"]["base"] = str(tmp_path)
    cfg_noticias["noticias"]["activo"] = True
    estado = noticias.etapa(cfg_noticias, "2026-11-05")
    assert estado["estado"] == "omitido"
    guardado = json.loads(
        (tmp_path / "resultados" / "2026-11-05" / "contraste_noticias.json").read_text("utf-8")
    )
    assert guardado["estado"] == "omitido"


def test_lectura_correlacion():
    assert "Sin correlación" in noticias.lectura_correlacion(0.05, 0.8)
    assert "no significativa" in noticias.lectura_correlacion(0.25, 0.2)
    assert "moderada positiva" in noticias.lectura_correlacion(0.45, 0.01)
