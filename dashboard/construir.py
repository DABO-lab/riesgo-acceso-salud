"""Arma el sitio estático del dashboard a partir de resultados/<fecha>/.

Uso:
    python dashboard/construir.py            # genera _site/
    python dashboard/construir.py --salida X  # en otra carpeta

No necesita dependencias: solo copia el dashboard y los resultados de cada corte, y escribe
datos/cortes.json con la lista de cortes (el más reciente primero). GitHub Actions lo corre
cada vez que el pipeline guarda un corte nuevo y publica _site/ en GitHub Pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_DASHBOARD = Path(__file__).resolve().parent
PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Archivos de cada corte que usa el dashboard (el modelo .pkl no se publica)
ARCHIVOS = [
    "municipios_riesgo.csv",
    "resumen_departamentos.csv",
    "resumen_eps.csv",
    "perfiles_grupos.csv",
    "comparacion_modelos.csv",
    "reporte_cruce_divipola.csv",
    "calidad.json",
    "monitoreo.json",
    "metadatos_corte.json",
    "metricas_indice.json",
    "equidad.json",
    "contraste_noticias.json",
    "noticias.json",
    "vulnerabilidad.json",
    "fichas_municipios.json",
    "validacion_ia.json",
]
OBLIGATORIOS = {"municipios_riesgo.csv", "calidad.json", "metadatos_corte.json"}


def construir(salida: Path) -> list[dict]:
    if salida.exists():
        shutil.rmtree(salida)
    (salida / "datos").mkdir(parents=True)

    # app.js y estilos.css se enlazan con ?v=<huella> para que el navegador no use una versión
    # vieja guardada en caché después de cada publicación
    html = (CARPETA_DASHBOARD / "index.html").read_text(encoding="utf-8")
    for nombre in ("app.js", "estilos.css"):
        contenido = (CARPETA_DASHBOARD / nombre).read_bytes()
        (salida / nombre).write_bytes(contenido)
        huella = hashlib.sha256(contenido).hexdigest()[:10]
        html = html.replace(f'"{nombre}"', f'"{nombre}?v={huella}"')
    (salida / "index.html").write_text(html, encoding="utf-8")
    (salida / ".nojekyll").write_text("")

    cortes = []
    carpeta_resultados = RAIZ / "resultados"
    for carpeta in sorted(carpeta_resultados.iterdir(), reverse=True):
        if not (carpeta.is_dir() and PATRON_FECHA.match(carpeta.name)):
            continue
        presentes = {a for a in ARCHIVOS if (carpeta / a).exists()}
        if not OBLIGATORIOS <= presentes:
            print(f"  - {carpeta.name}: incompleto, se omite")
            continue
        destino = salida / "datos" / carpeta.name
        destino.mkdir()
        for archivo in presentes:
            shutil.copy2(carpeta / archivo, destino / archivo)

        calidad = json.loads((carpeta / "calidad.json").read_text(encoding="utf-8"))
        cortes.append(
            {
                "fecha": carpeta.name,
                "archivos": sorted(presentes),
                "chequeos": len(calidad),
                "chequeos_ok": sum(1 for c in calidad if c.get("ok")),
            }
        )
        print(f"  + {carpeta.name}: {len(presentes)} archivos")

    if not cortes:
        raise SystemExit("No hay cortes completos en resultados/: nada que publicar.")

    (salida / "datos" / "cortes.json").write_text(
        json.dumps({"cortes": cortes}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cortes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", default=str(RAIZ / "_site"))
    args = parser.parse_args()
    cortes = construir(Path(args.salida))
    print(f"Sitio listo en {args.salida} con {len(cortes)} cortes (último: {cortes[0]['fecha']}).")


if __name__ == "__main__":
    main()
