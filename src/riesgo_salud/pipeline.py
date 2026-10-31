"""Pipeline completo: de los datos abiertos a los grupos de riesgo, con MLflow y monitoreo.

Uso:
    python -m riesgo_salud.pipeline                    # corte de hoy con datos reales
    python -m riesgo_salud.pipeline --fecha 2026-10-25 # un corte específico (usa la caché si existe)
    python -m riesgo_salud.pipeline --demo --rapido    # prueba con datos sintéticos, sin internet
"""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
import time
from datetime import date

import pandas as pd

from . import extraccion, features, indice, limpieza, modelado, monitoreo, reportes, sintetico, validacion
from .config import cargar_config, ruta
from .tracking import Tracker


def _titulo(texto: str) -> None:
    print(f"\n=== {texto} " + "=" * max(0, 60 - len(texto)))


def modo_demo(cfg: dict, rapido: bool) -> dict:
    cfg["rutas"]["resultados"] = "resultados_demo"
    cfg["rutas"]["raw"] = "data/raw_demo"
    cfg["mlflow"]["experimento"] += "-demo"
    cfg["mlflow"]["modelo_registrado"] += "-demo"
    cfg["validacion"].update({"min_afiliados_total": 0, "min_municipios": 50})
    if rapido:
        cfg["clustering"].update({"valores_k": [3, 4, 5], "n_bootstrap": 5})
        cfg["indice"]["sensibilidad"]["simulaciones"] = 100
    return cfg


# --- Etapas ------------------------------------------------------------------------------
# Cada etapa es una función: `ejecutar` las encadena en un script y `flujo.py` las convierte en
# tasks de Prefect (con reintentos, logs y artifacts). Ninguna lógica se duplica.


def etapa_extraccion(
    cfg: dict,
    fecha: str,
    demo: bool = False,
    forzar_descarga: bool = False,
    n_demo: int = 300,
    choque_demo: float = 0.0,
) -> dict:
    """1. Datos crudos del corte: de la caché en data/raw/<fecha>/, de datos.gov.co o sintéticos."""
    _titulo(f"1. Extracción ({'datos sintéticos' if demo else 'datos.gov.co'}) · corte {fecha}")
    carpeta_raw = ruta(cfg, "raw", fecha)
    raw = extraccion.leer_raw(carpeta_raw) if not forzar_descarga else None
    if raw is None and demo:
        raw = sintetico.generar_raw(n_demo, semilla=cfg["semilla"], choque=choque_demo)
        for n, df in raw.items():
            df.to_csv(carpeta_raw / f"{n}.csv", index=False)
        extraccion.guardar_metadatos(carpeta_raw, cfg, fecha, raw, origen="sintetico")
    elif raw is None:
        raw = extraccion.extraer(cfg, fecha, forzar=forzar_descarga)
    else:
        print(f"  Se usa el corte guardado en {carpeta_raw}")
    print("  Filas: " + ", ".join(f"{k}={len(v):,}" for k, v in raw.items()))
    return raw


def etapa_preparacion(cfg: dict, fecha: str, raw: dict) -> dict:
    """2-3. Limpieza, homologación DIVIPOLA, validaciones y tabla municipal.

    Si un chequeo crítico falla, lanza validacion.ErrorCalidad y nada se entrena.
    """
    salida = ruta(cfg, "resultados", fecha)
    for viejo in ("calidad.json", "experimentos_locales.jsonl"):
        (salida / viejo).unlink(missing_ok=True)

    _titulo("2. Limpieza, homologación DIVIPOLA y validaciones")
    div = limpieza.preparar_divipola(raw["divipola"])
    bdua_eps, bdua_demo, cruce = limpieza.limpiar_bdua(raw, div, cfg["eps_intervenidas"]["lista"])
    reps, info_reps = limpieza.limpiar_reps(raw, div)
    print(cruce.to_string(index=False))
    anterior = monitoreo.corte_anterior(ruta(cfg, "resultados"), fecha)
    total_ant = None
    if anterior:
        total_ant = pd.read_csv(ruta(cfg, "resultados", anterior) / "municipios_riesgo.csv")[
            "afiliados"
        ].sum()
    validacion.aplicar(
        validacion.validar_preparacion(bdua_eps, bdua_demo, reps, div, cruce, cfg, total_ant),
        salida / "calidad.json",
    )
    proc = ruta(cfg, "procesados", fecha)
    bdua_eps.to_csv(proc / "bdua_eps_limpia.csv", index=False)
    reps.to_csv(proc / "reps_ips_limpio.csv", index=False)
    limpieza.resumen_eps(bdua_eps).to_csv(salida / "resumen_eps.csv", index=False)
    cruce.to_csv(salida / "reporte_cruce_divipola.csv", index=False)

    _titulo("3. Tabla analítica municipal")
    tabla = features.construir_tabla_municipal(bdua_eps, reps, div)
    total_mun = bdua_eps.loc[bdua_eps["cod_mpio"].notna(), "afiliados"].sum()
    validacion.aplicar(validacion.validar_tabla_municipal(tabla, total_mun), salida / "calidad.json")
    print(f"  {len(tabla):,} municipios · {tabla['afiliados'].sum():,.0f} afiliados")
    return {
        "tabla": tabla,
        "anterior": anterior,
        "resumen_eps": limpieza.resumen_eps(bdua_eps),
        "cruce": cruce,
        "info_reps": info_reps,
    }


def etapa_indice(cfg: dict, tabla: pd.DataFrame) -> dict:
    """4. Índice de riesgo, sensibilidad de los pesos y comparación con PCA."""
    _titulo("4. Índice de riesgo de acceso")
    ti = indice.calcular_indice(tabla, cfg)
    m_sens, prob_top = indice.sensibilidad(ti, cfg)
    m_pca = indice.comparar_con_pca(ti, cfg)
    ti["prob_top10"] = prob_top
    metricas = {**m_sens, **{k: v for k, v in m_pca.items() if k != "pesos_pca"}}
    print("  " + ", ".join(f"{k}={v:.3f}" for k, v in metricas.items()))
    print(f"  Pesos PCA: {m_pca['pesos_pca']}")
    return {"ti": ti, "metricas": metricas, "pesos_pca": m_pca["pesos_pca"]}


def etapa_modelado(cfg: dict, fecha: str, ti: pd.DataFrame, metricas_indice: dict, tracker: Tracker) -> dict:
    """5. Los candidatos de clustering, la selección y el registro del modelo (dentro de un run de MLflow)."""
    _titulo("5. Modelos de clustering (MLflow)")
    salida = ruta(cfg, "resultados", fecha)
    tracker.params(
        {
            "fecha_corte": fecha,
            "eps_intervenidas": cfg["eps_intervenidas"]["lista"],
            "pesos_indice": {k: v["peso"] for k, v in cfg["indice"]["componentes"].items()},
            "municipios": len(ti),
            "semilla": cfg["semilla"],
        }
    )
    tracker.metricas({**metricas_indice, "afiliados_total": float(ti["afiliados"].sum())})
    resultados = modelado.experimentos(ti, cfg, tracker)
    elegido = modelado.seleccionar(resultados, cfg)
    print(f"  -> Modelo elegido: {elegido.algoritmo} con k={int(elegido.k)}")
    modelo, grupo, Xs = modelado.ajustar_final(ti, cfg, elegido.algoritmo, int(elegido.k))
    ti["grupo"] = grupo
    perf = modelado.perfiles(ti, grupo, Xs, cfg)
    tracker.params({"modelo_algoritmo": elegido.algoritmo, "modelo_k": int(elegido.k)})
    finales = ["silhouette", "davies_bouldin", "calinski_harabasz", "estabilidad_ari", "min_tamano_grupo"]
    tracker.metricas({f"final_{k}": float(elegido[k]) for k in finales})
    cumple = bool(elegido["cumple_regla"])
    tracker.etiquetas({"cumple_regla_seleccion": str(cumple).lower()})
    version = tracker.registrar_modelo(
        modelo,
        modelado.matriz(ti, cfg).head(5),
        promover=cumple,
        motivo="ningún candidato cumplió el tamaño mínimo de grupo y la estabilidad mínima",
    )
    if version:
        print(f"  Modelo registrado en MLflow: {cfg['mlflow']['modelo_registrado']} v{version}")
    with open(salida / "modelo.pkl", "wb") as f:
        pickle.dump(modelo, f)
    return {
        "ti": ti,
        "resultados": resultados,
        "elegido": elegido,
        "modelo": modelo,
        "perfiles": perf,
        "version": version,
    }


def etapa_monitoreo(
    cfg: dict, fecha: str, ti: pd.DataFrame, modelo, anterior: str | None, tracker: Tracker
) -> dict:
    """6. Comparación con el corte anterior: PSI, cambios de nivel y de grupo, campeón vs. retador."""
    _titulo("6. Monitoreo frente al corte anterior")
    salida = ruta(cfg, "resultados", fecha)
    if anterior:
        ant = pd.read_csv(
            ruta(cfg, "resultados", anterior) / "municipios_riesgo.csv", dtype={"cod_mpio": str}
        )
        monit = monitoreo.comparar(ant, ti, cfg, anterior, fecha)
        previo = ruta(cfg, "resultados", anterior) / "modelo.pkl"
        if previo.exists():  # modelo anterior ("campeón") frente al nuevo ("retador")
            with open(previo, "rb") as f:
                modelo_ant = pickle.load(f)
            monit.update(monitoreo.concordancia(modelo_ant, modelo, modelado.matriz(ti, cfg)))
        tracker.metricas({f"psi_{k}": v for k, v in monit["psi"].items()})
        tracker.metricas({"pct_cambio_nivel": monit["pct_municipios_cambian_nivel"]})
    else:
        monit = {"sin_referencia": True, "fecha_actual": fecha, "alertas": [], "reentrenar": False}
    monitoreo.guardar(monit, salida)
    print(monitoreo.informe_markdown(monit))
    return monit


def etapa_reportes(
    cfg: dict, fecha: str, indice_res: dict, modelo_res: dict, monit: dict, tracker: Tracker
) -> pd.DataFrame:
    """7. Figuras, CSV para Power BI y resumen en Markdown; todo queda como artifact del run."""
    _titulo("7. Reportes y archivos para Power BI")
    salida = ruta(cfg, "resultados", fecha)
    ti, perf = modelo_res["ti"], modelo_res["perfiles"]
    resultados, elegido = modelo_res["resultados"], modelo_res["elegido"]
    metricas_indice = indice_res["metricas"]
    fig_dir = ruta(cfg, "resultados", fecha, "figuras")
    figuras = [
        reportes.fig_seleccion(resultados, elegido, cfg, fig_dir),
        reportes.fig_perfiles(perf, cfg, fig_dir),
        reportes.fig_mapa(ti, cfg, fig_dir),
        reportes.fig_distribucion(ti, cfg, fig_dir),
    ]
    final = reportes.tabla_powerbi(ti, perf)
    final.to_csv(salida / "municipios_riesgo.csv", index=False, encoding="utf-8-sig")
    perf.to_csv(salida / "perfiles_grupos.csv", index=False, encoding="utf-8-sig")
    resultados.to_csv(salida / "comparacion_modelos.csv", index=False)
    reportes.resumen_departamentos(ti, cfg).to_csv(
        salida / "resumen_departamentos.csv", index=False, encoding="utf-8-sig"
    )
    (salida / "metricas_indice.json").write_text(
        json.dumps({**metricas_indice, "pesos_pca": indice_res["pesos_pca"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    resumen = reportes.resumen_markdown(fecha, ti, perf, resultados, elegido, metricas_indice, monit, cfg)
    (salida / "resumen.md").write_text(resumen, encoding="utf-8")
    shutil.copy(ruta(cfg, "raw", fecha) / "metadatos_corte.json", salida / "metadatos_corte.json")
    for p in [
        *figuras,
        salida / "municipios_riesgo.csv",
        salida / "perfiles_grupos.csv",
        salida / "comparacion_modelos.csv",
        salida / "resumen.md",
        salida / "calidad.json",
        salida / "monitoreo.json",
    ]:
        tracker.artefacto(p)
    return final


def nuevo_tracker(cfg: dict, fecha: str, usar_mlflow: bool) -> Tracker:
    return Tracker(cfg, habilitado=usar_mlflow, carpeta_local=ruta(cfg, "resultados", fecha))


def etiquetas_run(fecha: str, demo: bool) -> dict:
    return {"tipo": "pipeline", "fecha_corte": fecha, "origen": "sintetico" if demo else "datos.gov.co"}


def ejecutar(
    cfg: dict,
    fecha: str,
    demo: bool = False,
    usar_mlflow: bool = True,
    forzar_descarga: bool = False,
    n_demo: int = 300,
    choque_demo: float = 0.0,
) -> dict:
    """El pipeline completo como script (sin orquestador). Ver flujo.py para la versión con Prefect."""
    t0 = time.time()
    raw = etapa_extraccion(cfg, fecha, demo, forzar_descarga, n_demo, choque_demo)
    prep = etapa_preparacion(cfg, fecha, raw)
    ind = etapa_indice(cfg, prep["tabla"])
    tracker = nuevo_tracker(cfg, fecha, usar_mlflow)
    with tracker.run(f"pipeline_{fecha}", etiquetas=etiquetas_run(fecha, demo)):
        mod = etapa_modelado(cfg, fecha, ind["ti"], ind["metricas"], tracker)
        monit = etapa_monitoreo(cfg, fecha, mod["ti"], mod["modelo"], prep["anterior"], tracker)
        final = etapa_reportes(cfg, fecha, ind, mod, monit, tracker)
    salida = ruta(cfg, "resultados", fecha)
    print(f"\nListo en {time.time() - t0:.0f} s. Resultados en: {salida}")
    return resultado(final, prep, ind, mod, monit, salida)


def resultado(final, prep, ind, mod, monit, salida) -> dict:
    return {
        "tabla": final,
        "perfiles": mod["perfiles"],
        "comparacion": mod["resultados"],
        "elegido": mod["elegido"],
        "metricas_indice": ind["metricas"],
        "monitoreo": monit,
        "salida": salida,
        "modelo": mod["modelo"],
        "resumen_eps": prep["resumen_eps"],
        "cruce": prep["cruce"],
        "info_reps": prep["info_reps"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pipeline de riesgo de acceso a la salud")
    ap.add_argument("--config", default=None)
    ap.add_argument("--fecha", default=date.today().isoformat(), help="fecha del corte (AAAA-MM-DD)")
    ap.add_argument("--demo", action="store_true", help="usar datos sintéticos (sin internet)")
    ap.add_argument("--rapido", action="store_true", help="menos combinaciones (para pruebas)")
    ap.add_argument("--sin-mlflow", action="store_true")
    ap.add_argument("--forzar-descarga", action="store_true")
    a = ap.parse_args(argv)
    cfg = cargar_config(a.config)
    if a.demo:
        cfg = modo_demo(cfg, a.rapido)
    r = ejecutar(cfg, a.fecha, demo=a.demo, usar_mlflow=not a.sin_mlflow, forzar_descarga=a.forzar_descarga)
    if r["monitoreo"].get("reentrenar"):
        print("::warning::El monitoreo recomienda revisar y reentrenar el modelo.")


if __name__ == "__main__":
    main()
