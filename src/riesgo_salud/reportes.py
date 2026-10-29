"""Etapa 8: figuras, archivos para Power BI y resumen automático en Markdown."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

AZUL, NARANJA, AQUA, GRIS, TINTA, TINTA2 = "#2a78d6", "#eb6834", "#1baf7a", "#8c8b86", "#0b0b0b", "#52514e"
COLOR_ALG = {"kmeans": AZUL, "jerarquico": NARANJA, "gmm": AQUA}
NOMBRE_ALG = {"kmeans": "K-means", "jerarquico": "Jerárquico (Ward)", "gmm": "Mezcla gaussiana"}
plt.rcParams.update(
    {
        "figure.dpi": 120,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.titleweight": "bold",
        "font.size": 10,
        "axes.titlesize": 11,
    }
)


def _guardar(fig, carpeta: Path, nombre: str) -> Path:
    p = carpeta / f"{nombre}.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_seleccion(resultados: pd.DataFrame, elegido: pd.Series, cfg: dict, carpeta: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, met, titulo, umbral in [
        (axes[0], "silhouette", "Silhouette (más alto = grupos más separados)", None),
        (axes[1], "estabilidad_ari", "Estabilidad bootstrap (ARI)", cfg["clustering"]["min_estabilidad"]),
    ]:
        for alg in [a for a in COLOR_ALG if a in set(resultados["algoritmo"])]:
            d = resultados[resultados["algoritmo"] == alg]
            ax.plot(d["k"], d[met], marker="o", ms=6, lw=2, color=COLOR_ALG[alg], label=NOMBRE_ALG[alg])
        e = resultados[(resultados.algoritmo == elegido.algoritmo) & (resultados.k == elegido.k)]
        ax.scatter(e["k"], e[met], s=160, facecolors="none", edgecolors=TINTA, linewidths=1.5, zorder=5)
        if umbral is not None:
            ax.axhline(umbral, color=GRIS, ls="--", lw=1)
            ax.text(
                resultados["k"].max(), umbral, " mínimo", va="bottom", ha="right", fontsize=8.5, color=TINTA2
            )
        ax.set(title=titulo, xlabel="Número de grupos (k)", xticks=sorted(resultados["k"].unique()))
    axes[0].legend(frameon=False, fontsize=9)
    axes[0].annotate(
        "modelo elegido",
        (elegido.k, elegido.silhouette),
        xytext=(8, -14),
        textcoords="offset points",
        fontsize=8.5,
        color=TINTA,
    )
    fig.suptitle("Comparación de modelos de clustering", fontweight="bold", x=0.01, ha="left")
    fig.tight_layout()
    return _guardar(fig, carpeta, "01_seleccion_modelo")


def fig_perfiles(perfiles: pd.DataFrame, cfg: dict, carpeta: Path) -> Path:
    variables = cfg["clustering"]["variables"]
    etiquetas = {
        "pct_intervenidas": "% en EPS\nintervenidas",
        "hhi": "Concentración\n(HHI)",
        "ips_x_10mil": "IPS por\n10.000 afil.",
        "pct_rural": "% rural",
        "pct_subsidiado": "% subsidiado",
    }
    Z = perfiles[[f"z_{v}" for v in variables]].to_numpy()
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(perfiles) + 1.6))
    lim = max(1.5, np.abs(Z).max())
    im = ax.imshow(Z, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(len(variables)), [etiquetas.get(v, v) for v in variables], fontsize=9)
    ax.set_yticks(
        range(len(perfiles)),
        [f"Grupo {g}  ·  {m} mun." for g, m in zip(perfiles["grupo"], perfiles["municipios"], strict=True)],
    )
    for i in range(Z.shape[0]):
        for j in range(Z.shape[1]):
            ax.text(
                j,
                i,
                f"{Z[i, j]:+.1f}",
                ha="center",
                va="center",
                fontsize=8.5,
                color="white" if abs(Z[i, j]) > lim * 0.6 else TINTA,
            )
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Desviaciones estándar frente al promedio")
    ax.set_title("Perfil de cada grupo\n(rojo = por encima del promedio, azul = por debajo)", loc="left")
    return _guardar(fig, carpeta, "02_perfiles_grupos")


def fig_mapa(tabla: pd.DataFrame, cfg: dict, carpeta: Path) -> Path:
    niveles = cfg["indice"]["etiquetas_niveles"]
    colores = plt.cm.Oranges(np.linspace(0.3, 0.95, len(niveles)))
    fig, ax = plt.subplots(figsize=(7, 8))
    for nivel, color in zip(niveles, colores, strict=True):
        d = tabla[tabla["nivel_riesgo"].astype(str) == nivel]
        ax.scatter(
            d["longitud"],
            d["latitud"],
            s=np.sqrt(d["afiliados"]) / 6 + 4,
            color=color,
            edgecolor="white",
            linewidth=0.4,
            label=f"{nivel} ({len(d)})",
            alpha=0.9,
        )
    ax.set_aspect("equal")
    ax.set(xlabel="Longitud", ylabel="Latitud")
    ax.set_title("Nivel de riesgo de acceso por municipio (tamaño = afiliados)", loc="left")
    ax.legend(title="Nivel (municipios)", frameon=False, loc="lower left", fontsize=9)
    return _guardar(fig, carpeta, "03_mapa_niveles")


def fig_distribucion(tabla: pd.DataFrame, cfg: dict, carpeta: Path) -> Path:
    cortes = tabla["indice_riesgo"].quantile(cfg["indice"]["cuantiles_niveles"])
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.hist(tabla["indice_riesgo"], bins=40, color=AZUL, edgecolor="white")
    for _q, c in zip(cfg["indice"]["cuantiles_niveles"], cortes, strict=True):
        ax.axvline(c, color=GRIS, ls="--", lw=1)
    etiquetas = cfg["indice"]["etiquetas_niveles"]
    limites = [tabla["indice_riesgo"].min(), *cortes, tabla["indice_riesgo"].max()]
    techo = ax.get_ylim()[1]
    ax.set_ylim(0, techo * 1.18)
    for i, et in enumerate(etiquetas):
        ax.text(
            (limites[i] + limites[i + 1]) / 2,
            techo * 1.12,
            et,
            ha="center",
            va="center",
            fontsize=9,
            color=TINTA2,
        )
    ax.set(xlabel="Índice de riesgo (0 = menor, 100 = mayor)", ylabel="Municipios")
    ax.set_title("Distribución del índice de riesgo de acceso", loc="left")
    ax.grid(axis="x", visible=False)
    return _guardar(fig, carpeta, "04_distribucion_indice")


def tabla_powerbi(tabla: pd.DataFrame, perfiles: pd.DataFrame) -> pd.DataFrame:
    p = perfiles[["grupo", "nombre", "descripcion"]].rename(
        columns={"nombre": "nombre_grupo", "descripcion": "descripcion_grupo"}
    )
    out = tabla.merge(p, on="grupo", how="left")
    out["nivel_riesgo"] = out["nivel_riesgo"].astype(str)
    return out.sort_values("ranking_riesgo")


def resumen_departamentos(tabla: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    muy_alto = cfg["indice"]["etiquetas_niveles"][-1]
    t = tabla.assign(
        _w_int=tabla["pct_intervenidas"] * tabla["afiliados"],
        _w_ind=tabla["indice_riesgo"] * tabla["afiliados"],
        _muy=(tabla["nivel_riesgo"].astype(str) == muy_alto).astype(int),
    )
    g = t.groupby("dpto").agg(
        municipios=("cod_mpio", "size"),
        afiliados=("afiliados", "sum"),
        _w_int=("_w_int", "sum"),
        _w_ind=("_w_ind", "sum"),
        municipios_muy_alto=("_muy", "sum"),
    )
    g["pct_intervenidas"] = g["_w_int"] / g["afiliados"]
    g["indice_ponderado"] = g["_w_ind"] / g["afiliados"]
    return g.drop(columns=["_w_int", "_w_ind"]).sort_values("indice_ponderado", ascending=False).reset_index()


def _fmt(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumen_markdown(fecha, tabla, perfiles, resultados, elegido, metricas_indice, monit, cfg) -> str:
    etiquetas = cfg["indice"]["etiquetas_niveles"]
    niv = (
        tabla.groupby(tabla["nivel_riesgo"].astype(str))
        .agg(municipios=("cod_mpio", "size"), afiliados=("afiliados", "sum"))
        .reindex(etiquetas)
    )
    filas_niv = "\n".join(f"| {n} | {int(r.municipios)} | {_fmt(r.afiliados)} |" for n, r in niv.iterrows())
    top = tabla.nsmallest(15, "ranking_riesgo")
    filas_top = "\n".join(
        f"| {int(r.ranking_riesgo)} | {r.nom_mpio.title()} | {r.dpto.title()} | {_fmt(r.indice_riesgo, 1)} | "
        f"{_fmt(r.pct_intervenidas * 100)} % | {_fmt(r.ips_x_10mil, 2)} | {r.eps_principal} |"
        for r in top.itertuples()
    )
    filas_grupos = "\n".join(
        f"| {int(r.grupo)} | {int(r.municipios)} | {_fmt(r.afiliados)} | {_fmt(r.indice_promedio, 1)} | {r.descripcion} |"
        for r in perfiles.itertuples()
    )
    pesos = ", ".join(f"{k} {v['peso']:.0%}" for k, v in cfg["indice"]["componentes"].items())
    mon = (monit.get("alertas") and "\n".join(f"- {a}" for a in monit["alertas"])) or (
        "- Primer corte: todavía no hay un corte anterior para comparar."
        if monit.get("sin_referencia")
        else "- Sin alertas: los datos se mantienen estables frente al corte anterior."
    )
    return f"""# Resultados del corte {fecha}

## 1. Índice de riesgo de acceso
El índice va de 0 (menor riesgo) a 100 (mayor riesgo). Combina, en percentiles, estos componentes: {pesos}.

| Nivel | Municipios | Afiliados |
|---|---|---|
{filas_niv}

**Robustez del índice**
- Al mover los pesos al azar {cfg["indice"]["sensibilidad"]["simulaciones"]} veces, la correlación de Spearman
  mediana con el ranking original es {_fmt(metricas_indice["sens_spearman_mediana"], 3)}
  (en el 5 % de los peores casos, {_fmt(metricas_indice["sens_spearman_p05"], 3)}).
- Con pesos obtenidos por PCA, la correlación con el índice es {
        _fmt(metricas_indice["pca_spearman_vs_indice"], 3)
    }
  y coinciden el {
        _fmt(metricas_indice["pca_jaccard_top10"] * 100)
    } % de los municipios del 10 % de mayor riesgo (Jaccard).

### Los 15 municipios con mayor índice de riesgo
| # | Municipio | Departamento | Índice | % EPS intervenidas | IPS por 10.000 | EPS principal |
|---|---|---|---|---|---|---|
{filas_top}

## 2. Grupos de municipios (clustering)
Modelo elegido: **{elegido.algoritmo} con k = {int(elegido.k)}**
(silhouette {_fmt(elegido.silhouette, 3)}, Davies-Bouldin {_fmt(elegido.davies_bouldin, 2)},
estabilidad ARI {_fmt(elegido.estabilidad_ari, 2)}, grupo más pequeño {
        _fmt(elegido.min_tamano_grupo * 100, 1)
    } %).
Se compararon {len(resultados)} combinaciones de algoritmo y número de grupos.
{
        "Cumple la regla de selección: se promovió a producción en MLflow."
        if elegido["cumple_regla"]
        else "**Ningún candidato cumplió la regla de selección**: los grupos se describen, pero el modelo NO se promovió a producción."
    }

| Grupo | Municipios | Afiliados | Índice promedio | Rasgos principales |
|---|---|---|---|---|
{filas_grupos}

## 3. Monitoreo
{mon}
"""
