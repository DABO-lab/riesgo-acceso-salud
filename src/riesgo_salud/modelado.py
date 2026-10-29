"""Etapa 6: agrupación de municipios (clustering) y selección del mejor modelo.

Se comparan tres algoritmos (K-means, jerárquico de Ward y mezcla gaussiana) con k = 3..7.
Cada combinación se evalúa con:
- Silhouette (más alto = grupos más separados), Davies-Bouldin (más bajo = mejor),
  Calinski-Harabasz (más alto = mejor).
- Tamaño mínimo de grupo (evita grupos de 2 o 3 municipios).
- Estabilidad: se re-entrena con 20 muestras bootstrap y se mide el ARI contra la solución original.
El modelo final es un Pipeline de scikit-learn (preprocesamiento + NearestCentroid) que puede
asignar nuevos municipios o nuevos cortes al grupo más cercano.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import NearestCentroid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

DESCRIPTORES = {  # variable: (texto si el grupo está por encima, texto si está por debajo)
    "pct_intervenidas": ("alta dependencia de EPS intervenidas", "baja dependencia de EPS intervenidas"),
    "hhi": ("afiliación muy concentrada", "afiliación más diversificada"),
    "ips_x_10mil": ("más oferta de IPS", "poca oferta de IPS"),
    "pct_rural": ("muy rural", "más urbano"),
    "pct_subsidiado": ("muy subsidiado", "más contributivo"),
}


def preprocesador(cfg: dict) -> Pipeline:
    variables = cfg["clustering"]["variables"]
    log = [v for v in variables if v in cfg["clustering"]["transformacion_log"]]
    resto = [v for v in variables if v not in log]
    ct = ColumnTransformer(
        [
            ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one"), log),
            ("igual", "passthrough", resto),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline([("transformar", ct), ("escalar", StandardScaler())])


def matriz(tabla: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return tabla[cfg["clustering"]["variables"]].astype(float)


def _ajustar(algoritmo: str, k: int, Xs: np.ndarray, semilla: int) -> np.ndarray:
    if algoritmo == "kmeans":
        return KMeans(n_clusters=k, n_init=20, random_state=semilla).fit_predict(Xs)
    if algoritmo == "jerarquico":
        return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Xs)
    if algoritmo == "gmm":
        return GaussianMixture(
            n_components=k,
            covariance_type="full",
            n_init=5,
            max_iter=500,
            reg_covar=1e-4,
            random_state=semilla,
        ).fit_predict(Xs)
    raise ValueError(f"Algoritmo desconocido: {algoritmo}")


def _centroides(Xs: np.ndarray, etiquetas: np.ndarray) -> np.ndarray:
    return np.vstack([Xs[etiquetas == g].mean(axis=0) for g in np.unique(etiquetas)])


def _asignar(Xs: np.ndarray, centroides: np.ndarray) -> np.ndarray:
    d = ((Xs[:, None, :] - centroides[None, :, :]) ** 2).sum(axis=2)
    return d.argmin(axis=1)


def estabilidad(
    algoritmo: str, k: int, Xs: np.ndarray, etiquetas: np.ndarray, n_bootstrap: int, semilla: int
) -> float:
    rng = np.random.default_rng(semilla)
    aris = []
    for b in range(n_bootstrap):
        idx = rng.choice(len(Xs), len(Xs), replace=True)
        lb = _ajustar(algoritmo, k, Xs[idx], semilla + b + 1)
        pred = _asignar(Xs, _centroides(Xs[idx], lb))
        aris.append(adjusted_rand_score(etiquetas, pred))
    return float(np.mean(aris))


def evaluar(algoritmo: str, k: int, Xs: np.ndarray, cfg: dict) -> tuple[np.ndarray, dict]:
    et = _ajustar(algoritmo, k, Xs, cfg["semilla"])
    tam = np.bincount(et, minlength=k) / len(et)
    m = {
        "silhouette": float(silhouette_score(Xs, et)),
        "davies_bouldin": float(davies_bouldin_score(Xs, et)),
        "calinski_harabasz": float(calinski_harabasz_score(Xs, et)),
        "min_tamano_grupo": float(tam.min()),
        "estabilidad_ari": estabilidad(
            algoritmo, k, Xs, et, cfg["clustering"]["n_bootstrap"], cfg["semilla"]
        ),
    }
    return et, m


def experimentos(tabla: pd.DataFrame, cfg: dict, tracker=None) -> pd.DataFrame:
    """Entrena todas las combinaciones algoritmo x k y registra cada una en MLflow."""
    X = matriz(tabla, cfg)
    Xs = preprocesador(cfg).fit_transform(X)
    filas = []
    for alg in cfg["clustering"]["algoritmos"]:
        for k in cfg["clustering"]["valores_k"]:
            _, m = evaluar(alg, k, Xs, cfg)
            fila = {"algoritmo": alg, "k": k, **m}
            filas.append(fila)
            print(
                f"  {alg:<11} k={k}  silhouette={m['silhouette']:.3f}  DB={m['davies_bouldin']:.2f}  "
                f"estabilidad={m['estabilidad_ari']:.2f}  grupo_min={m['min_tamano_grupo']:.1%}"
            )
            if tracker:
                with tracker.run(f"{alg}_k{k}", anidado=True, etiquetas={"tipo": "candidato"}):
                    tracker.params(
                        {"algoritmo": alg, "k": k, "variables": ",".join(cfg["clustering"]["variables"])}
                    )
                    tracker.metricas(m)
    return pd.DataFrame(filas)


def seleccionar(resultados: pd.DataFrame, cfg: dict) -> pd.Series:
    """Regla: cumplir tamaño mínimo y estabilidad, y entre esos, el mayor silhouette.

    Devuelve la fila del modelo elegido con `cumple_regla` = True/False. Si ninguno cumple, se
    elige el mejor balance para describir los grupos, pero `cumple_regla` queda en False y el
    modelo no recibe el alias de producción.
    """
    c = cfg["clustering"]
    ok = resultados[
        (resultados["min_tamano_grupo"] >= c["min_tamano_grupo"])
        & (resultados["estabilidad_ari"] >= c["min_estabilidad"])
    ]
    if ok.empty:
        print(
            "  Ninguna combinación cumple la estabilidad mínima: se elige el mejor balance "
            "silhouette x estabilidad entre las que cumplen el tamaño mínimo."
        )
        ok = resultados[resultados["min_tamano_grupo"] >= c["min_tamano_grupo"]]
        ok = ok if not ok.empty else resultados
        ok = ok.assign(_b=ok["silhouette"] * ok["estabilidad_ari"]).sort_values("_b", ascending=False)
        # Se usa para describir los grupos, pero NO se promueve a producción (ver tracking.py)
        return pd.concat([ok.drop(columns="_b").iloc[0], pd.Series({"cumple_regla": False})])
    orden = {"kmeans": 0, "gmm": 1, "jerarquico": 2}  # en empate, el más simple de explicar
    ok = ok.assign(_o=ok["algoritmo"].map(orden)).sort_values(
        ["silhouette", "estabilidad_ari", "_o"], ascending=[False, False, True]
    )
    return pd.concat([ok.drop(columns="_o").iloc[0], pd.Series({"cumple_regla": True})])


def ajustar_final(tabla_indice: pd.DataFrame, cfg: dict, algoritmo: str, k: int):
    """Entrena el modelo elegido. Los grupos se numeran de 1 (más riesgo) a k (menos riesgo)."""
    X = matriz(tabla_indice, cfg)
    prep = preprocesador(cfg)
    Xs = pd.DataFrame(prep.fit_transform(X), columns=prep.get_feature_names_out(), index=X.index)
    et = _ajustar(algoritmo, k, Xs.to_numpy(), cfg["semilla"])
    media_indice = pd.Series(tabla_indice["indice_riesgo"].to_numpy()).groupby(et).mean()
    orden = {g: i + 1 for i, g in enumerate(media_indice.sort_values(ascending=False).index)}
    grupo = np.array([orden[g] for g in et])
    modelo = Pipeline([("preparar", preprocesador(cfg)), ("asignar", NearestCentroid())]).fit(X, grupo)
    return modelo, pd.Series(grupo, index=tabla_indice.index, name="grupo"), Xs


def perfiles(tabla_indice: pd.DataFrame, grupo: pd.Series, Xs: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Resumen de cada grupo + descripción automática a partir de los centroides estandarizados."""
    t = tabla_indice.assign(grupo=grupo.to_numpy())
    variables = cfg["clustering"]["variables"]
    agg = t.groupby("grupo").agg(
        municipios=("cod_mpio", "size"),
        afiliados=("afiliados", "sum"),
        indice_promedio=("indice_riesgo", "mean"),
        **{v: (v, "median") for v in variables},
    )
    agg["pct_municipios"] = agg["municipios"] / agg["municipios"].sum()
    agg["pct_afiliados"] = agg["afiliados"] / agg["afiliados"].sum()
    muy_alto = cfg["indice"]["etiquetas_niveles"][-1]
    agg["pct_nivel_muy_alto"] = t.groupby("grupo")["nivel_riesgo"].apply(lambda s: (s == muy_alto).mean())
    z = (
        Xs[variables].assign(grupo=grupo.to_numpy()).groupby("grupo").mean()
    )  # centroides en desviaciones estándar
    for v in variables:
        agg[f"z_{v}"] = z[v]
    textos = []
    for _g, fila in z.iterrows():
        rasgos = [
            DESCRIPTORES[v][0] if fila[v] > 0.4 else DESCRIPTORES[v][1]
            for v in fila.abs().sort_values(ascending=False).index[:3]
            if abs(fila[v]) > 0.4
        ]
        textos.append(", ".join(rasgos) if rasgos else "valores cercanos al promedio")
    agg["descripcion"] = textos
    agg["nombre"] = [
        f"Grupo {g}" + (" (mayor riesgo)" if g == 1 else " (menor riesgo)" if g == len(agg) else "")
        for g in agg.index
    ]
    return agg.reset_index()
