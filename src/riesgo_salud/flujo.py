"""Orquestación del pipeline con Prefect.

El mismo pipeline de `pipeline.py`, pero cada etapa es una *task* de Prefect: queda con estado
(Completed, Failed, Retrying), logs, duración y reintentos visibles en la interfaz. Al final se
publican *artifacts* legibles (calidad, resumen y monitoreo) en el run del flow.

Uso:
    uv run python -m riesgo_salud.flujo                       # corte de hoy, una vez
    uv run python -m riesgo_salud.flujo --fecha 2026-10-29    # un corte específico
    uv run python -m riesgo_salud.flujo --demo                # datos sintéticos, sin internet
    uv run python -m riesgo_salud.flujo --programar           # deployment: el día 5 de cada mes
    uv run prefect server start                               # interfaz en http://127.0.0.1:4200

Decisiones:
- Solo la extracción se reintenta (3 veces, con espera creciente): las fallas de red o del portal
  son transitorias. Un error de calidad de datos es determinista y NO se reintenta: detiene el flow.
- Idempotencia: la fecha del corte es la llave. Repetir un run reescribe los mismos archivos de
  `resultados/<fecha>/` en lugar de duplicarlos.
- Reentrenar no es promover: el modelo nuevo solo recibe el alias `produccion` si cumple la regla
  de selección (tracking.py), y el monitoreo solo alerta.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.cache_policies import NO_CACHE
from prefect.schedules import Cron

from . import monitoreo, pipeline, validacion
from .config import cargar_config, ruta

# NO_CACHE: los argumentos son DataFrames y la configuración; cada corte se recalcula completo
# y la caché de los datos crudos ya la maneja la extracción (data/raw/<fecha>/).
_task = {"cache_policy": NO_CACHE, "log_prints": True}


@task(name="extraccion", retries=3, retry_delay_seconds=[10, 30, 60], **_task)
def t_extraccion(cfg, fecha, demo, forzar_descarga, n_demo):
    return pipeline.etapa_extraccion(cfg, fecha, demo, forzar_descarga, n_demo)


@task(name="limpieza-validacion-tabla", **_task)
def t_preparacion(cfg, fecha, raw):
    return pipeline.etapa_preparacion(cfg, fecha, raw)


@task(name="indice-riesgo", **_task)
def t_indice(cfg, tabla):
    return pipeline.etapa_indice(cfg, tabla)


@task(name="clustering-mlflow-registro", **_task)
def t_modelado(cfg, fecha, ti, metricas, tracker):
    return pipeline.etapa_modelado(cfg, fecha, ti, metricas, tracker)


@task(name="monitoreo", **_task)
def t_monitoreo(cfg, fecha, ti, modelo, anterior, tracker):
    return pipeline.etapa_monitoreo(cfg, fecha, ti, modelo, anterior, tracker)


@task(name="reportes", **_task)
def t_reportes(cfg, fecha, ind, mod, monit, tracker):
    return pipeline.etapa_reportes(cfg, fecha, ind, mod, monit, tracker)


@task(name="artifacts", **_task)
def t_artifacts(cfg, fecha, monit, elegido):
    """Evidencia durable y legible en la interfaz de Prefect."""
    salida = ruta(cfg, "resultados", fecha)
    calidad = json.loads((salida / "calidad.json").read_text(encoding="utf-8"))
    create_table_artifact(
        key="calidad-datos",
        table=[{k: str(v) for k, v in c.items()} for c in calidad],
        description=f"Contratos de datos del corte {fecha}",
    )
    create_markdown_artifact(
        key="resumen-corte",
        markdown=(salida / "resumen.md").read_text(encoding="utf-8"),
        description=f"Índice, grupos y monitoreo del corte {fecha}",
    )
    create_markdown_artifact(
        key="monitoreo",
        markdown=monitoreo.informe_markdown(monit),
        description="PSI y cambios frente al corte anterior",
    )
    return {
        "modelo": f"{elegido['algoritmo']} k={int(elegido['k'])}",
        "promovido": bool(elegido["cumple_regla"]),
    }


@flow(name="riesgo-acceso-salud", log_prints=True)
def flujo(
    fecha: str | None = None,
    demo: bool = False,
    rapido: bool = False,
    usar_mlflow: bool = True,
    forzar_descarga: bool = False,
    n_demo: int = 300,
) -> dict:
    """Extracción → limpieza y validaciones → índice → clustering en MLflow → monitoreo → reportes."""
    logger = get_run_logger()
    fecha = fecha or date.today().isoformat()
    cfg = cargar_config()
    if demo:
        cfg = pipeline.modo_demo(cfg, rapido)

    raw = t_extraccion(cfg, fecha, demo, forzar_descarga, n_demo)
    try:
        prep = t_preparacion(cfg, fecha, raw)
    except validacion.ErrorCalidad:
        logger.error(
            "Los datos no pasaron los contratos de calidad: no se entrena. Ver resultados/%s/calidad.json",
            fecha,
        )
        raise
    ind = t_indice(cfg, prep["tabla"])

    tracker = pipeline.nuevo_tracker(cfg, fecha, usar_mlflow)
    # El run de MLflow envuelve las tasks que registran en él (se ejecutan en este mismo hilo)
    with tracker.run(
        f"pipeline_{fecha}", etiquetas={**pipeline.etiquetas_run(fecha, demo), "orquestador": "prefect"}
    ):
        mod = t_modelado(cfg, fecha, ind["ti"], ind["metricas"], tracker)
        monit = t_monitoreo(cfg, fecha, mod["ti"], mod["modelo"], prep["anterior"], tracker)
        final = t_reportes(cfg, fecha, ind, mod, monit, tracker)
    estado = t_artifacts(cfg, fecha, monit, mod["elegido"])

    if monit.get("reentrenar"):
        logger.warning("El monitoreo recomienda revisar y reentrenar: %s", "; ".join(monit["alertas"]))
    if not estado["promovido"]:
        logger.warning("El modelo nuevo no cumplió la regla de selección: el alias de producción no se movió")
    salida = ruta(cfg, "resultados", fecha)
    logger.info("Corte %s listo: %d municipios en %s", fecha, len(final), salida)
    return pipeline.resultado(final, prep, ind, mod, monit, salida)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pipeline orquestado con Prefect")
    ap.add_argument("--fecha", default=None, help="fecha del corte (AAAA-MM-DD); vacío = hoy")
    ap.add_argument("--demo", action="store_true", help="datos sintéticos, sin internet")
    ap.add_argument("--rapido", action="store_true", help="menos combinaciones (para pruebas)")
    ap.add_argument("--sin-mlflow", action="store_true")
    ap.add_argument(
        "--programar",
        action="store_true",
        help="deployment local que corre el día 5 de cada mes a las 8:00 (hora de Colombia)",
    )
    a = ap.parse_args(argv)
    if a.programar:
        # Queda escuchando: Prefect lanza el flow según el cron. Ctrl+C para detenerlo.
        flujo.serve(
            name="corte-mensual",
            schedule=Cron("0 8 5 * *", timezone="America/Bogota"),
            parameters={"usar_mlflow": not a.sin_mlflow},
            tags=["mensual", "datos.gov.co"],
        )
    else:
        flujo(fecha=a.fecha, demo=a.demo, rapido=a.rapido, usar_mlflow=not a.sin_mlflow)


if __name__ == "__main__":
    main()
