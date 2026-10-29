"""Datos sintéticos con la MISMA estructura que la API de datos.gov.co.

Sirven para las pruebas automáticas y para el modo demo (`--demo`), sin conexión a internet.
Los valores son inventados: nunca se usan para conclusiones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .extraccion import CLASE_IPS
from .limpieza import AREAS_NO_MUNICIPALIZADAS, HOMOLOGACION_MANUAL, ORDEN_EDAD

DPTOS = {
    "05": "ANTIOQUIA",
    "08": "ATLÁNTICO",
    "11": "BOGOTÁ, D.C.",
    "13": "BOLÍVAR",
    "15": "BOYACÁ",
    "17": "CALDAS",
    "18": "CAQUETÁ",
    "19": "CAUCA",
    "20": "CESAR",
    "23": "CÓRDOBA",
    "25": "CUNDINAMARCA",
    "27": "CHOCÓ",
    "47": "MAGDALENA",
    "50": "META",
    "52": "NARIÑO",
    "54": "NORTE DE SANTANDER",
    "66": "RISARALDA",
    "68": "SANTANDER",
    "70": "SUCRE",
    "73": "TOLIMA",
    "76": "VALLE DEL CAUCA",
    "91": "AMAZONAS",
    "94": "GUAINÍA",
    "97": "VAUPÉS",
}
# Nombre del departamento tal como lo escribe la BDUA
DPTO_BDUA = {"76": "VALLE", "11": "BOGOTA D.C."}

# (código, nombre BDUA, régimen, nombre canónico)
EPS_CATALOGO = [
    ("EPS037", "NUEVA EPS S.A.", "Contributivo"),
    ("EPSS41", "NUEVA EPS S.A.", "Subsidiado"),
    ("EPS041", "NUEVA EPS S.A. -CM", "Contributivo"),
    ("EPS010", "EPS SURAMERICANA S.A.", "Contributivo"),
    ("EPSS10", "EPS SURAMERICANA S.A. -CM", "Subsidiado"),
    ("EPS005", "ENTIDAD PROMOTORA DE SALUD SANITAS S.A.S.", "Contributivo"),
    ("EPS002", "SALUD TOTAL ENTIDAD PROMOTORA DE SALUD", "Contributivo"),
    ("ESS024", "COOSALUD EPS S.A.", "Subsidiado"),
    ("ESSC24", "COOSALUD EPS S.A. -CM", "Contributivo"),
    ("ESS207", "ASOCIACION MUTUAL SER EMPRESA SOLIDARIA DE SALUD", "Subsidiado"),
    ("EPS017", "EPS FAMISANAR S.A.S.", "Contributivo"),
    ("EPSS40", 'ALIANZA MEDELLIN ANTIOQUIA EPS S.A.S. "SAVIA SALUD EPS"', "Subsidiado"),
    ("ESS118", "EMSSANAR S.A.S.", "Subsidiado"),
    ("ESS062", "ASMET SALUD EPS S.A.S.", "Subsidiado"),
    ("CCF055", "PROTEGER EPS S.A.S.", "Subsidiado"),
    ("EPS018", "ENTIDAD PROMOTORA DE SALUD SERVICIO OCCIDENTAL DE SALUD S.A. S.O.S.", "Contributivo"),
    ("EPS025", "CAPRESOCA E.P.S.", "Subsidiado"),
    ("EPSI05", "ENTIDAD PROMOTORA DE SALUD MALLAMAS EPSI", "Subsidiado"),
]
ZONAS_URB = ["Urbana", "Urbana-Cabecera Municipal", "Urbana - Centro Poblado"]
ZONAS_RUR = ["Rural", "Rural - Dispersal", "Rural - Resto Rural"]


def generar_raw(n_municipios: int = 300, semilla: int = 0, choque: float = 0.0) -> dict[str, pd.DataFrame]:
    """Genera las 7 tablas crudas. `choque` > 0 desplaza la afiliación hacia EPS intervenidas
    (sirve para probar el monitoreo de cambios entre cortes)."""
    rng = np.random.default_rng(semilla)

    # --- DIVIPOLA: los códigos de la homologación manual + municipios inventados
    municipios = []  # (cod_mpio, cod_dpto, nombre DIVIPOLA, dpto BDUA, municipio BDUA)
    for (d_bdua, m_bdua), cod in HOMOLOGACION_MANUAL.items():
        municipios.append((cod, cod[:2], f"MUNICIPIO {cod}", d_bdua, m_bdua))
    usados = {m[0] for m in municipios}
    cods_dpto = sorted(DPTOS)
    i, objetivo = 0, max(n_municipios, len(municipios) + 5)
    while len(municipios) < objetivo:
        dp = cods_dpto[i % len(cods_dpto)]
        cod = f"{dp}{900 - i // len(cods_dpto):03d}"
        i += 1
        if cod in usados:
            continue
        usados.add(cod)
        nombre = f"MUNICIPIO {cod}"
        municipios.append((cod, dp, nombre, DPTO_BDUA.get(dp, DPTOS[dp]), nombre))
    centro = {dp: (rng.uniform(-2, 11), rng.uniform(-78, -68)) for dp in DPTOS}
    div = pd.DataFrame(
        [
            {
                "cod_dpto": dp,
                "dpto": DPTOS[dp],
                "cod_mpio": cod,
                "nom_mpio": nom,
                "tipo_municipio": "Municipio",
                "latitud": f"{centro[dp][0] + rng.normal(0, 0.6):.6f}".replace(".", ","),
                "longitud": f"{centro[dp][1] + rng.normal(0, 0.6):.6f}".replace(".", ","),
            }
            for cod, dp, nom, _, _ in municipios
        ]
    )

    # --- BDUA
    eps_rows, demo_rows = [], []
    intervenidas_idx = [
        k
        for k, e in enumerate(EPS_CATALOGO)
        if any(
            x in e[1]
            for x in ["NUEVA", "COOSALUD", "FAMISANAR", "EMSSANAR", "ASMET", "OCCIDENTAL", "CAPRESOCA"]
        )
    ]
    for _cod, _dp, _, d_bdua, m_bdua in municipios:
        total = int(np.clip(rng.lognormal(9.3, 1.1), 300, 3_000_000))
        n_eps = int(rng.integers(2, 7))
        elegidas = rng.choice(len(EPS_CATALOGO), n_eps, replace=False)
        pesos = rng.dirichlet(np.full(n_eps, rng.uniform(0.3, 2.0)))
        if choque:
            pesos = pesos * np.where(np.isin(elegidas, intervenidas_idx), 1 + choque, 1)
            pesos = pesos / pesos.sum()
        p_rural = rng.beta(2, 2.5)
        for k, w in zip(elegidas, pesos, strict=True):
            ent_id, ent_nombre, regimen = EPS_CATALOGO[k]
            n = int(round(total * w))
            if n == 0:
                continue
            n_rur = int(round(n * p_rural))
            for zona, cantidad in ((rng.choice(ZONAS_URB), n - n_rur), (rng.choice(ZONAS_RUR), n_rur)):
                if cantidad > 0:
                    eps_rows.append(
                        {
                            "dpr_nombre": d_bdua,
                            "mnc_nombre": m_bdua,
                            "ent_id": ent_id,
                            "ent_nombre": ent_nombre,
                            "tps_rgm_nombre": regimen,
                            "zns_nombre": zona,
                            "tps_est_afl_nombre": "Activo",
                            "afiliados": cantidad,
                        }
                    )
    # áreas no municipalizadas (como en la BDUA real)
    for d, _m in AREAS_NO_MUNICIPALIZADAS:
        eps_rows.append(
            {
                "dpr_nombre": d,
                "mnc_nombre": f"DPTO. {d}",
                "ent_id": "EPSS41",
                "ent_nombre": "NUEVA EPS S.A.",
                "tps_rgm_nombre": "Subsidiado",
                "zns_nombre": "Rural",
                "tps_est_afl_nombre": "Activo",
                "afiliados": 150,
            }
        )
    eps = pd.DataFrame(eps_rows)
    tot = eps.groupby(["dpr_nombre", "mnc_nombre", "tps_rgm_nombre"])["afiliados"].sum()
    for (d, m, rg), t in tot.items():
        partes = rng.multinomial(int(t), np.full(24, 1 / 24))
        j = 0
        for sexo in ("Femenino", "Masculino"):
            for edad in ORDEN_EDAD:
                demo_rows.append(
                    {
                        "dpr_nombre": d,
                        "mnc_nombre": m,
                        "tps_rgm_nombre": rg,
                        "tps_gnr_nombre": sexo,
                        "tps_grp_etr_id": edad,
                        "afiliados": int(partes[j]),
                    }
                )
                j += 1
    demo = pd.DataFrame(demo_rows)

    # --- REPS: al menos una sede por municipio
    tot_mun = (
        eps.merge(
            pd.DataFrame(
                [(c, d, m) for c, _, _, d, m in municipios], columns=["cod", "dpr_nombre", "mnc_nombre"]
            ),
            on=["dpr_nombre", "mnc_nombre"],
        )
        .groupby("cod")["afiliados"]
        .sum()
    )
    reps_rows, sede = [], 0
    for cod, af in tot_mun.items():
        n_sedes = max(1, int(rng.poisson(af / 10000 * rng.gamma(2.5, 1.2))))
        for _ in range(n_sedes):
            sede += 1
            publica = rng.random() < 0.2
            reps_rows.append(
                {
                    "codigoprestador": f"{cod}{sede:05d}",
                    "nombreprestador": f"IPS {sede}",
                    "codigohabilitacionsede": f"{cod}{sede:07d}",
                    "nombresede": f"SEDE {sede}",
                    "naturalezajuridica": "Pública" if publica else "Privada",
                    "ese": "SI" if publica else "NO",
                    "claseprestador": CLASE_IPS,
                    "municipiosede": cod,
                    "fecha_corte_reps": "Fecha corte REPS: sintético",
                }
            )
    reps_rows.append({**reps_rows[0], "codigohabilitacionsede": "270860000001", "municipiosede": "27086"})
    reps = pd.DataFrame(reps_rows)
    resumen = pd.DataFrame(
        [
            {
                "claseprestador": CLASE_IPS,
                "naturalezajuridica": "Privada",
                "sedes": int((reps["naturalezajuridica"] == "Privada").sum()),
            },
            {
                "claseprestador": CLASE_IPS,
                "naturalezajuridica": "Pública",
                "sedes": int((reps["naturalezajuridica"] == "Pública").sum()),
            },
            {
                "claseprestador": "Profesional Independiente",
                "naturalezajuridica": "Privada",
                "sedes": len(reps) * 3,
            },
        ]
    )

    def mitad(df, rg):
        return df[df["tps_rgm_nombre"] == rg].reset_index(drop=True).astype(str)

    return {
        "eps_contributivo": mitad(eps, "Contributivo"),
        "eps_subsidiado": mitad(eps, "Subsidiado"),
        "demo_contributivo": mitad(demo, "Contributivo"),
        "demo_subsidiado": mitad(demo, "Subsidiado"),
        "reps_ips": reps.astype(str),
        "reps_resumen": resumen.astype(str),
        "divipola": div.astype(str),
    }
