"""Carga lo que la API necesita del último corte y responde las consultas.

De `resultados/<fecha>/` (versionado en el repo) se toman:
- `municipios_riesgo.csv`: la tabla de referencia (índice, nivel, grupo de cada municipio).
- `perfiles_grupos.csv`: nombre y descripción de cada grupo.
- `modelo.pkl`: el modelo de grupos de ese corte (el mismo que quedó en MLflow).

Si existe la variable MODELO_URI (por ejemplo `models:/clusters-riesgo-municipal@produccion`),
el modelo se carga desde MLflow por su alias en lugar del archivo. Así la versión activa es
siempre inequívoca: o el archivo de un corte concreto, o el alias del Model Registry.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import cargar_config, ruta
from ..indice import estimar_indice

COLUMNAS_MUNICIPIO = [
    "cod_mpio", "nom_mpio", "dpto", "afiliados", "eps_principal", "sedes_ips",
    "pct_intervenidas", "hhi", "ips_x_10mil", "pct_rural", "pct_subsidiado",
    "indice_riesgo", "nivel_riesgo", "ranking_riesgo", "prob_top10",
    "grupo", "nombre_grupo", "descripcion_grupo",
]  # fmt: skip


def ultimo_resultado(carpeta: Path) -> Path:
    """La carpeta de corte más reciente que tenga resultados completos."""
    cortes = sorted(p for p in carpeta.glob("????-??-??") if (p / "municipios_riesgo.csv").exists())
    if not cortes:
        raise FileNotFoundError(f"No hay resultados en {carpeta}. Ejecute primero: make pipeline")
    return cortes[-1]


@dataclass
class Servicio:
    cfg: dict
    corte: str
    tabla: pd.DataFrame
    grupos: pd.DataFrame
    modelo: object
    origen_modelo: str

    @property
    def variables(self) -> list[str]:
        return self.cfg["clustering"]["variables"]

    def predecir(self, valores: pd.DataFrame) -> list[dict]:
        est = estimar_indice(valores, self.tabla, self.cfg)
        grupos = self.modelo.predict(valores[self.variables])
        salida = []
        for (_, e), g in zip(est.iterrows(), grupos, strict=True):
            info = self.grupos.loc[int(g)]
            salida.append(
                {
                    "indice_riesgo": round(float(e["indice_riesgo"]), 2),
                    "nivel_riesgo": e["nivel_riesgo"],
                    "componentes": {
                        c.replace("comp_", ""): round(float(e[c]), 2)
                        for c in est.columns
                        if c.startswith("comp_")
                    },
                    "grupo": int(g),
                    "nombre_grupo": info["nombre"],
                    "descripcion_grupo": info["descripcion"],
                }
            )
        return salida

    def municipio(self, cod_mpio: str) -> dict | None:
        fila = self.tabla.loc[self.tabla["cod_mpio"] == cod_mpio, COLUMNAS_MUNICIPIO]
        return None if fila.empty else _registro(fila.iloc[0])

    def ranking(self, dpto: str | None, nivel: str | None, limite: int) -> tuple[int, list[dict]]:
        t = self.tabla
        if dpto:
            t = t[t["dpto_norm"] == _normalizar(dpto)]
        if nivel:
            t = t[t["nivel_riesgo"].str.lower() == nivel.lower()]
        t = t.sort_values("ranking_riesgo")
        return len(t), [_registro(f) for _, f in t.head(limite)[COLUMNAS_MUNICIPIO].iterrows()]


def _normalizar(texto: str) -> str:
    from ..limpieza import normalizar_texto

    return normalizar_texto(texto)


def _registro(fila: pd.Series) -> dict:
    d = fila.to_dict()
    d["eps_principal"] = None if pd.isna(d["eps_principal"]) else d["eps_principal"]
    return d


def cargar_servicio(carpeta_resultados: Path | None = None) -> Servicio:
    cfg = cargar_config()
    carpeta = ultimo_resultado(Path(carpeta_resultados) if carpeta_resultados else ruta(cfg, "resultados"))
    tabla = pd.read_csv(carpeta / "municipios_riesgo.csv", dtype={"cod_mpio": str, "cod_dpto": str})
    tabla = tabla.dropna(subset=cfg["clustering"]["variables"] + ["indice_riesgo"]).reset_index(drop=True)
    tabla["dpto_norm"] = tabla["dpto"].map(_normalizar)
    grupos = pd.read_csv(carpeta / "perfiles_grupos.csv").set_index("grupo")

    uri = os.environ.get("MODELO_URI")
    if uri:
        import mlflow.sklearn

        from ..tracking import uri_tracking

        mlflow.set_tracking_uri(uri_tracking(cfg))
        modelo, origen = mlflow.sklearn.load_model(uri), uri
    else:
        with open(carpeta / "modelo.pkl", "rb") as f:
            modelo = pickle.load(f)
        origen = f"resultados/{carpeta.name}/modelo.pkl"
    return Servicio(
        cfg=cfg, corte=carpeta.name, tabla=tabla, grupos=grupos, modelo=modelo, origen_modelo=origen
    )
