"""Auditoría de equidad: detecta los sesgos que el equipo documentó, con casos construidos a mano."""

import numpy as np
import pandas as pd
import pytest

from riesgo_salud import equidad


def _tabla(n=200, semilla=0):
    rng = np.random.default_rng(semilla)
    afiliados = rng.integers(3_000, 300_000, n)
    t = pd.DataFrame(
        {
            "cod_mpio": [f"{i:05d}" for i in range(n)],
            "nom_mpio": [f"MPIO {i}" for i in range(n)],
            "dpto": rng.choice(["A", "B", "C"], n),
            "afiliados": afiliados,
            "pct_rural": rng.uniform(0, 0.4, n),
            "pct_subsidiado": rng.uniform(0.2, 0.7, n),
            "pct_intervenidas": rng.uniform(0, 1, n),
            "ips_x_10mil": rng.uniform(1, 4, n),
            "sedes_ips": rng.integers(1, 30, n),
            "prob_top10": 0.0,
        }
    )
    t["indice_riesgo"] = 100 * t["pct_intervenidas"]
    t["nivel_riesgo"] = pd.cut(
        t["indice_riesgo"], [-1, 30, 70, 90, 101], labels=["Bajo", "Medio", "Alto", "Muy alto"]
    ).astype(str)
    return t


@pytest.fixture
def cfg_eq():
    return {
        "equidad": {
            "poblacion_pequena": 2000,
            "vulnerable_rural": 0.5,
            "vulnerable_subsidiado": 0.8,
            "incertidumbre_top10": [0.2, 0.8],
        }
    }


def test_sin_sesgos_construidos_no_hay_alertas(cfg_eq):
    r = equidad.auditar(_tabla(), cfg_eq)
    assert r["alertas"] == []
    assert r["municipios"] == 200
    assert r["spearman_indice"]["pct_intervenidas"] == pytest.approx(1.0)


def test_detecta_oferta_inflada_en_municipios_muy_pequenos(cfg_eq):
    t = _tabla()
    t.loc[:9, "afiliados"] = 400
    t.loc[:9, "ips_x_10mil"] = 25.0  # una sede para 400 personas
    r = equidad.auditar(t, cfg_eq)
    assert r["poblacion_pequena"]["municipios"] == 10
    assert any("subestima" in a for a in r["alertas"])


def test_detecta_vulnerables_en_nivel_bajo(cfg_eq):
    t = _tabla()
    bajos = t.index[t["nivel_riesgo"] == "Bajo"][:5]
    t.loc[bajos, ["pct_rural", "pct_subsidiado"]] = [0.9, 0.95]
    r = equidad.auditar(t, cfg_eq)
    assert r["vulnerables_bajo"]["en_nivel_bajo"] == 5
    assert any("no se debe leer como buen acceso" in a for a in r["alertas"])


def test_cuenta_municipios_inciertos_y_departamentos_sin_alto(cfg_eq):
    t = _tabla()
    t.loc[:6, "prob_top10"] = 0.5
    t.loc[t["dpto"] == "C", ["indice_riesgo", "nivel_riesgo"]] = [10.0, "Bajo"]
    r = equidad.auditar(t, cfg_eq)
    assert r["incertidumbre_top10"]["municipios"] == 7
    assert r["departamentos_sin_alto"] == ["C"]


def test_guarda_json_y_markdown_legibles(cfg_eq, tmp_path):
    r = equidad.auditar(_tabla(), cfg_eq)
    equidad.guardar(r, tmp_path)
    assert (tmp_path / "equidad.json").exists()
    md = (tmp_path / "equidad.md").read_text(encoding="utf-8")
    assert "Auditoría de equidad" in md and "Sin alertas" in md
    assert set(equidad.metricas(r)) >= {"eq_vulnerables_en_bajo", "eq_inciertos_top10"}
