"""Etapa 5: índice de riesgo de acceso a la salud (0-100).

Cómo se construye:
1. Cada variable se convierte a percentil (0-100) entre municipios. Así todas quedan en la
   misma escala y los valores extremos (por ejemplo 270 IPS por 10.000) no dominan.
2. Las variables donde "más es mejor" (oferta de IPS) se invierten: 100 - percentil.
3. Se promedian con los pesos de config.yaml.
Además se calcula una versión con pesos de PCA y una prueba de sensibilidad de los pesos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


def componentes(tabla: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Matriz de componentes en percentiles, orientados para que 100 = más riesgo."""
    out = pd.DataFrame(index=tabla.index)
    for nombre, c in cfg["indice"]["componentes"].items():
        pct = tabla[c["variable"]].rank(pct=True, method="average") * 100
        out[f"comp_{nombre}"] = 100 - pct if c["sentido"] == "negativo" else pct
    return out


def pesos_config(cfg: dict) -> pd.Series:
    w = pd.Series({f"comp_{k}": v["peso"] for k, v in cfg["indice"]["componentes"].items()})
    return w / w.sum()


def asignar_niveles(indice: pd.Series, cfg: dict) -> pd.Series:
    cortes = indice.quantile(cfg["indice"]["cuantiles_niveles"]).to_numpy()
    etiquetas = cfg["indice"]["etiquetas_niveles"]
    pos = np.searchsorted(cortes, indice.to_numpy(), side="right")
    return pd.Series(
        pd.Categorical([etiquetas[p] for p in pos], categories=etiquetas, ordered=True), index=indice.index
    )


def calcular_indice(tabla: pd.DataFrame, cfg: dict, pesos: pd.Series | None = None) -> pd.DataFrame:
    base = tabla.dropna(subset=[c["variable"] for c in cfg["indice"]["componentes"].values()]).copy()
    comp = componentes(base, cfg)
    w = pesos if pesos is not None else pesos_config(cfg)
    base = base.join(comp)
    base["indice_riesgo"] = comp[w.index].to_numpy() @ w.to_numpy()
    base["nivel_riesgo"] = asignar_niveles(base["indice_riesgo"], cfg)
    base["ranking_riesgo"] = base["indice_riesgo"].rank(ascending=False, method="min").astype(int)
    return base


def pesos_pca(tabla_indice: pd.DataFrame, cfg: dict) -> tuple[pd.Series, float]:
    """Pesos alternativos: cargas absolutas del primer componente principal."""
    cols = list(pesos_config(cfg).index)
    X = StandardScaler().fit_transform(tabla_indice[cols])
    pca = PCA(n_components=1, random_state=cfg["semilla"]).fit(X)
    cargas = pd.Series(pca.components_[0], index=cols)
    if cargas.sum() < 0:
        cargas = -cargas
    w = cargas.abs() / cargas.abs().sum()
    return w, float(pca.explained_variance_ratio_[0])


def _rangos(m: np.ndarray) -> np.ndarray:
    return pd.DataFrame(m).rank(axis=0).to_numpy()


def sensibilidad(tabla_indice: pd.DataFrame, cfg: dict) -> tuple[dict, pd.Series]:
    """Perturba los pesos al azar (Dirichlet) y mide qué tanto cambia el ranking."""
    s = cfg["indice"]["sensibilidad"]
    w = pesos_config(cfg)
    rng = np.random.default_rng(cfg["semilla"])
    W = rng.dirichlet(w.to_numpy() * s["concentracion_dirichlet"], size=s["simulaciones"])
    C = tabla_indice[w.index].to_numpy()
    sims = C @ W.T  # municipios x simulaciones
    base = tabla_indice["indice_riesgo"].to_numpy()
    rb = pd.Series(base).rank().to_numpy()
    rs = _rangos(sims)
    rho = np.array([np.corrcoef(rb, rs[:, j])[0, 1] for j in range(rs.shape[1])])
    q90 = np.quantile(sims, 0.9, axis=0)
    en_top = sims >= q90  # municipio en el 10 % de mayor riesgo
    top_base = base >= np.quantile(base, 0.9)
    jacc = np.array(
        [(en_top[:, j] & top_base).sum() / (en_top[:, j] | top_base).sum() for j in range(en_top.shape[1])]
    )
    metricas = {
        "sens_spearman_mediana": float(np.median(rho)),
        "sens_spearman_p05": float(np.quantile(rho, 0.05)),
        "sens_jaccard_top10_mediana": float(np.median(jacc)),
    }
    prob_top = pd.Series(en_top.mean(axis=1), index=tabla_indice.index, name="prob_top10")
    return metricas, prob_top


def comparar_con_pca(tabla_indice: pd.DataFrame, cfg: dict) -> dict:
    w_pca, var = pesos_pca(tabla_indice, cfg)
    alt = tabla_indice[w_pca.index].to_numpy() @ w_pca.to_numpy()
    rho = pd.Series(alt).rank().corr(tabla_indice["indice_riesgo"].reset_index(drop=True).rank())
    top_a = alt >= np.quantile(alt, 0.9)
    top_b = tabla_indice["indice_riesgo"].to_numpy() >= tabla_indice["indice_riesgo"].quantile(0.9)
    return {
        "pca_varianza_explicada": var,
        "pca_spearman_vs_indice": float(rho),
        "pca_jaccard_top10": float((top_a & top_b).sum() / (top_a | top_b).sum()),
        "pesos_pca": {k.replace("comp_", ""): round(float(v), 3) for k, v in w_pca.items()},
    }


def estimar_indice(valores: pd.DataFrame, referencia: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Índice y nivel de municipios NUEVOS (o con indicadores hipotéticos) frente a un corte de referencia.

    Cada variable se ubica en el percentil que ocuparía entre los municipios de `referencia`, con
    la misma regla de `componentes` (rango promedio): para un municipio que ya está en la referencia
    devuelve exactamente su índice. Los niveles usan los cortes por cuantiles de la referencia.
    Lo usa la API para responder "¿qué riesgo tendría un municipio con estos indicadores?".
    """
    out = pd.DataFrame(index=valores.index)
    n = len(referencia)
    for nombre, c in cfg["indice"]["componentes"].items():
        ref = np.sort(referencia[c["variable"]].to_numpy(dtype=float))
        x = valores[c["variable"]].to_numpy(dtype=float)
        menores = np.searchsorted(ref, x, side="left")
        iguales = np.searchsorted(ref, x, side="right") - menores
        pct = (menores + (iguales + 1) / 2) / n * 100
        out[f"comp_{nombre}"] = 100 - pct if c["sentido"] == "negativo" else pct
    w = pesos_config(cfg)
    out["indice_riesgo"] = out[w.index].to_numpy() @ w.to_numpy()
    cortes = referencia["indice_riesgo"].quantile(cfg["indice"]["cuantiles_niveles"]).to_numpy()
    etiquetas = cfg["indice"]["etiquetas_niveles"]
    out["nivel_riesgo"] = [etiquetas[p] for p in np.searchsorted(cortes, out["indice_riesgo"], side="right")]
    return out
