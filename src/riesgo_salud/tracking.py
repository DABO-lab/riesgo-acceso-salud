"""Seguimiento de experimentos con MLflow.

Si MLflow no está instalado, el pipeline sigue funcionando y guarda los registros en un
archivo JSON local (experimentos_locales.jsonl). Así el proyecto nunca se rompe por esto.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import ruta


def uri_tracking(cfg: dict) -> str:
    """Dónde se guardan los experimentos.

    Por defecto, un archivo SQLite en mlflow/mlflow.db (no hace falta levantar ningún servidor).
    Si existe la variable MLFLOW_TRACKING_URI (por ejemplo http://127.0.0.1:5001 con `make mlflow`),
    se usa ese servidor, como en el laboratorio del curso.
    """
    return (
        os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{(ruta(cfg, 'mlflow') / 'mlflow.db').as_posix()}"
    )


class Tracker:
    def __init__(self, cfg: dict, habilitado: bool = True, carpeta_local: Path | None = None):
        self.cfg = cfg
        self.mlflow = None
        self._pila = []
        self.archivo_local = (carpeta_local or ruta(cfg, "resultados")) / "experimentos_locales.jsonl"
        if habilitado:
            try:
                import mlflow

                self.mlflow = mlflow
            except ImportError:
                print("  MLflow no está instalado: los experimentos se guardan en un JSON local.")
        if self.mlflow:
            self.mlflow.set_tracking_uri(uri_tracking(cfg))
            nombre = cfg["mlflow"]["experimento"]
            if self.mlflow.get_experiment_by_name(nombre) is None:
                artefactos = None
                if not os.environ.get("MLFLOW_TRACKING_URI"):
                    artefactos = (ruta(cfg, "mlflow") / "artefactos").as_uri()
                self.mlflow.create_experiment(nombre, artifact_location=artefactos)
            self.mlflow.set_experiment(nombre)

    @property
    def activo(self) -> bool:
        return self.mlflow is not None

    @contextmanager
    def run(self, nombre: str, anidado: bool = False, etiquetas: dict | None = None):
        if self.mlflow:
            with self.mlflow.start_run(run_name=nombre, nested=anidado, tags=etiquetas or {}) as r:
                yield r
        else:
            registro = {
                "run": nombre,
                "inicio": datetime.now().isoformat(timespec="seconds"),
                "etiquetas": etiquetas or {},
                "params": {},
                "metricas": {},
                "artefactos": [],
            }
            self._pila.append(registro)
            try:
                yield registro
            finally:
                self._pila.pop()
                with open(self.archivo_local, "a", encoding="utf-8") as f:
                    f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")

    def params(self, d: dict):
        d = {
            k: (v if isinstance(v, int | float | str | bool) else json.dumps(v, ensure_ascii=False))
            for k, v in d.items()
        }
        if self.mlflow:
            self.mlflow.log_params(d)
        elif self._pila:
            self._pila[-1]["params"].update(d)

    def metricas(self, d: dict):
        d = {k: float(v) for k, v in d.items()}
        if self.mlflow:
            self.mlflow.log_metrics(d)
        elif self._pila:
            self._pila[-1]["metricas"].update(d)

    def etiquetas(self, d: dict):
        if self.mlflow:
            self.mlflow.set_tags(d)
        elif self._pila:
            self._pila[-1]["etiquetas"].update(d)

    def artefacto(self, archivo: Path, carpeta: str | None = None):
        if self.mlflow:
            self.mlflow.log_artifact(str(archivo), artifact_path=carpeta)
        elif self._pila:
            self._pila[-1]["artefactos"].append(str(archivo))

    def registrar_modelo(self, modelo, ejemplo, promover: bool, motivo: str = "") -> str | None:
        """Guarda el modelo con su firma, lo registra como nueva versión y, SOLO si pasó la
        regla de selección (`promover`), le mueve el alias de producción.

        Si no pasa la regla, la versión queda registrada (para poder compararla) pero el alias
        sigue apuntando al modelo anterior: nunca se promueve un modelo sin control de calidad.
        """
        if not self.mlflow:
            return None
        import mlflow.sklearn
        from mlflow.models import infer_signature

        nombre = self.cfg["mlflow"]["modelo_registrado"]
        alias = self.cfg["mlflow"]["alias_produccion"]
        info = mlflow.sklearn.log_model(
            modelo,
            name="modelo",
            registered_model_name=nombre,
            signature=infer_signature(ejemplo, modelo.predict(ejemplo)),
            input_example=ejemplo,
        )
        version = str(info.registered_model_version)
        cliente = self.mlflow.MlflowClient()
        cliente.set_model_version_tag(nombre, version, "cumple_regla_seleccion", str(promover).lower())
        if promover:
            cliente.set_registered_model_alias(nombre, alias, version)
            print(f"  Alias '{alias}' -> versión {version}")
        else:
            print(f"  Versión {version} registrada SIN alias '{alias}': {motivo}")
        return version
