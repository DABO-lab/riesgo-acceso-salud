"""Un corte sintético con la MISMA forma que devuelve la API de datos.gov.co.

Es pequeño pero trae a propósito los problemas reales de los datos: nombres
que no coinciden con el DANE, el error ¥/Ñ, una EPS con varios códigos, zonas
con seis nombres, un área no municipalizada, una sede del REPS con un código de
municipio inexistente y una sede duplicada. Así las pruebas corren sin internet.
"""

import pandas as pd
import pytest

from salud.data.catalogos import HOMOLOGACION_MANUAL

# Municipios "reales" del corte sintético: (cod_dpto, dpto, cod_mpio, nom_mpio)
MUNICIPIOS = [
    ("05", "ANTIOQUIA", "05001", "MEDELLÍN"),
    ("05", "ANTIOQUIA", "05664", "SAN PEDRO DE LOS MILAGROS"),
    ("54", "NORTE DE SANTANDER", "54001", "SAN JOSÉ DE CÚCUTA"),
    ("76", "VALLE DEL CAUCA", "76001", "CALI"),
    ("76", "VALLE DEL CAUCA", "76111", "GUADALAJARA DE BUGA"),
    ("52", "NARIÑO", "52001", "PASTO"),
    ("11", "BOGOTÁ, D.C.", "11001", "BOGOTÁ, D.C."),
]

# (dpr_nombre, mnc_nombre) tal como los escribe la BDUA
NOMBRES_BDUA = {
    "05001": ("ANTIOQUIA", "MEDELLIN"),
    "05664": ("ANTIOQUIA", "SAN PEDRO"),  # homologación manual
    "54001": ("NORTE DE SANTANDER", "CUCUTA"),  # homologación manual
    "76001": ("VALLE", "CALI"),  # alias de departamento
    "76111": ("VALLE", "BUGA"),  # homologación manual
    "52001": ("NARI¥O", "PASTO"),  # error ¥ por Ñ
    "11001": ("BOGOTA", "BOGOTA D.C."),  # alias de departamento
}

# Nombre de la EPS en la BDUA -> (ent_id, régimen)
EPS_BDUA = [
    ("NUEVA EPS S.A.", "EPS037", "Contributivo"),
    ("NUEVA EPS S.A. -CM", "EPSS41", "Subsidiado"),
    ("COOSALUD EPS-S", "ESS024", "Subsidiado"),
    ("EMSSANAR S.A.S.", "ESS118", "Subsidiado"),
    ("ASMET SALUD EPS S.A.S.", "ESS062", "Subsidiado"),
    ("EPS FAMISANAR S.A.S.", "EPS017", "Contributivo"),
    ("SERVICIO OCCIDENTAL DE SALUD S.A. - S.O.S.", "EPS018", "Contributivo"),
    ("CAPRESOCA EPS", "EPS025", "Subsidiado"),
    ("EPS SURAMERICANA S.A.", "EPS010", "Contributivo"),
    ("EPS SANITAS S.A.S.", "EPS005", "Contributivo"),
]

ZONAS = ["Urbana", "Urbana-Cabecera Municipal", "Rural", "Rural - Dispersal"]


def _divipola() -> pd.DataFrame:
    filas = [
        {
            "cod_dpto": d,
            "dpto": dn,
            "cod_mpio": m,
            "nom_mpio": mn,
            "tipo_municipio": "Municipio",
            "longitud": "-75,5",
            "latitud": "6,2",
        }
        for d, dn, m, mn in MUNICIPIOS
    ]
    # DIVIPOLA debe contener todos los códigos de la homologación manual
    ya = {f["cod_mpio"] for f in filas}
    for cod in sorted(set(HOMOLOGACION_MANUAL.values()) - ya):
        filas.append(
            {
                "cod_dpto": cod[:2],
                "dpto": f"DPTO {cod[:2]}",
                "cod_mpio": cod,
                "nom_mpio": f"MUNICIPIO {cod}",
                "tipo_municipio": "Municipio",
                "longitud": "-74,0",
                "latitud": "4,6",
            }
        )
    # La API devuelve los códigos sin ceros a la izquierda en algunos casos
    df = pd.DataFrame(filas)
    df["cod_mpio"] = df["cod_mpio"].str.lstrip("0")
    df["cod_dpto"] = df["cod_dpto"].str.lstrip("0")
    return df


def _bdua_eps() -> pd.DataFrame:
    filas = []
    for i, (_cod, (dpto, mpio)) in enumerate(NOMBRES_BDUA.items()):
        for j, (ent, ent_id, reg) in enumerate(EPS_BDUA):
            if (i + j) % 3 == 0:  # no todas las EPS están en todos los municipios
                continue
            zona = ZONAS[(i + j) % len(ZONAS)]
            filas.append(
                {
                    "dpr_nombre": dpto,
                    "mnc_nombre": mpio,
                    "ent_id": ent_id,
                    "ent_nombre": ent,
                    "tps_rgm_nombre": reg,
                    "zns_nombre": zona,
                    "tps_est_afl_nombre": "Activo",
                    "afiliados": str(100 * (i + 1) + 10 * j),
                }
            )
    # Área no municipalizada: se reporta y queda fuera de la tabla municipal
    filas.append(
        {
            "dpr_nombre": "GUAINIA",
            "mnc_nombre": "DPTO. GUAINIA",
            "ent_id": "ESS024",
            "ent_nombre": "COOSALUD EPS-S",
            "tps_rgm_nombre": "Subsidiado",
            "zns_nombre": "Rural",
            "tps_est_afl_nombre": "Activo",
            "afiliados": "37",
        }
    )
    return pd.DataFrame(filas)


def _bdua_demo(eps: pd.DataFrame) -> pd.DataFrame:
    """Vista demográfica que suma EXACTAMENTE lo mismo que la vista por EPS."""
    g = (
        eps.assign(afiliados=eps["afiliados"].astype(int))
        .groupby(["dpr_nombre", "mnc_nombre", "tps_rgm_nombre"], as_index=False)["afiliados"]
        .sum()
    )
    filas = []
    for _, r in g.iterrows():
        mitad = r["afiliados"] // 2
        for sexo, edad, n in [("F", "19 a 45", mitad), ("M", "5 a 15 ", r["afiliados"] - mitad)]:
            filas.append(
                {
                    "dpr_nombre": r["dpr_nombre"],
                    "mnc_nombre": r["mnc_nombre"],
                    "tps_rgm_nombre": r["tps_rgm_nombre"],
                    "tps_gnr_nombre": sexo,
                    "tps_grp_etr_id": edad,
                    "afiliados": str(n),
                }
            )
    return pd.DataFrame(filas)


def _reps() -> pd.DataFrame:
    filas = []
    sedes = {"5001": 6, "5664": 1, "54001": 3, "76001": 4, "76111": 2, "52001": 2, "11001": 8, "27086": 4}
    for cod, n in sedes.items():
        for k in range(n):
            filas.append(
                {
                    "codigoprestador": f"P{cod}{k}",
                    "nombreprestador": f"IPS {cod}-{k}",
                    "codigohabilitacionsede": f"{cod}{k:04d}",
                    "nombresede": f"Sede {k}",
                    "naturalezajuridica": "Pública" if k == 0 else "Privada",
                    "ese": "SI" if k == 0 else "NO",
                    "claseprestador": "Instituciones Prestadoras de Servicios de Salud - IPS",
                    "municipiosede": cod,
                    "fecha_corte_reps": "Fecha corte REPS: Mar 12 2026",
                }
            )
    filas.append(dict(filas[0]))  # una sede duplicada
    return pd.DataFrame(filas)


def construir_corte() -> dict[str, pd.DataFrame]:
    eps = _bdua_eps()
    demo = _bdua_demo(eps)
    contrib = eps["tps_rgm_nombre"] == "Contributivo"
    demo_contrib = demo["tps_rgm_nombre"] == "Contributivo"
    return {
        "bdua_eps_contributivo": eps[contrib].reset_index(drop=True),
        "bdua_eps_subsidiado": eps[~contrib].reset_index(drop=True),
        "bdua_demo_contributivo": demo[demo_contrib].reset_index(drop=True),
        "bdua_demo_subsidiado": demo[~demo_contrib].reset_index(drop=True),
        "reps_ips": _reps(),
        "reps_resumen_clase": pd.DataFrame(
            {
                "claseprestador": ["Instituciones Prestadoras de Servicios de Salud - IPS"],
                "naturalezajuridica": ["Privada"],
                "sedes": ["30"],
            }
        ),
        "divipola": _divipola(),
    }


@pytest.fixture
def corte():
    return construir_corte()
