"""Única fuente de verdad del proyecto.

Todas las rutas, identificadores de datasets, listas y umbrales viven aquí.
Si un script y un notebook necesitan el mismo valor, los dos lo importan de
este archivo: así nunca se desincronizan.

Lo que cambia entre cortes (la fecha, la lista de EPS intervenidas, el
departamento del zoom) se puede sobrescribir con variables de entorno, sin
tocar el código. Ejemplo en PowerShell:

    $env:FECHA_CORTE = "2026-10-25"; make clean
"""

import os
from datetime import date
from pathlib import Path

# Raíz del repo: dos niveles arriba de este archivo (src/salud/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- Rutas (relativas a la raíz del repo, nunca absolutas) -------------------
# data/raw/<fecha>/  → los datos tal como llegan del portal, uno por corte. Intocables.
# data/processed/    → los datos limpios y la tabla analítica.
DATA_DIR = Path(os.getenv("SALUD_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

# Fecha del corte: por defecto, hoy. Para reprocesar un corte anterior se fija
# FECHA_CORTE=AAAA-MM-DD. El paso de limpieza usa el corte más reciente que
# exista en data/raw/ si no se indica ninguno.
FECHA_CORTE = os.getenv("FECHA_CORTE") or None
FECHA_HOY = date.today().isoformat()

# --- Fuentes: API SODA de datos.gov.co ---------------------------------------
BASE_URL = "https://www.datos.gov.co/resource/"
DATASETS = {
    "bdua_contributivo": "tq4m-hmg2",  # ADRES
    "bdua_subsidiado": "d7a5-cnra",  # ADRES
    "reps": "c36g-9fc2",  # MinSalud
    "divipola": "gdxc-w37w",  # DANE
}
PAGE_SIZE = 50_000
MAX_REINTENTOS = 4
TIMEOUT_SEGUNDOS = 180

# Columnas que se piden a la API. La BDUA se agrega EN EL SERVIDOR por estas
# columnas: en vez de ~2 millones de filas llegan ~100 mil.
COLS_EPS = [
    "dpr_nombre",
    "mnc_nombre",
    "ent_id",
    "ent_nombre",
    "tps_rgm_nombre",
    "zns_nombre",
    "tps_est_afl_nombre",
]
COLS_DEMO = ["dpr_nombre", "mnc_nombre", "tps_rgm_nombre", "tps_gnr_nombre", "tps_grp_etr_id"]
# Del REPS NO se piden correos, teléfonos, direcciones ni documentos (Ley 1581 de 2012).
COLS_REPS = [
    "codigoprestador",
    "nombreprestador",
    "codigohabilitacionsede",
    "nombresede",
    "naturalezajuridica",
    "ese",
    "claseprestador",
    "municipiosede",
    "fecha_corte_reps",
]
CLASE_IPS = "Instituciones Prestadoras de Servicios de Salud - IPS"

# Nombre de archivo de cada tabla cruda dentro de data/raw/<fecha>/
TABLAS_CRUDAS = [
    "bdua_eps_contributivo",
    "bdua_eps_subsidiado",
    "bdua_demo_contributivo",
    "bdua_demo_subsidiado",
    "reps_ips",
    "reps_resumen_clase",
    "divipola",
]

# --- Parámetros del análisis -------------------------------------------------
# EPS bajo medida de intervención de la Supersalud.
# Fuente: Vanguardia, 8-oct-2026, con base en la Supersalud. VERIFICAR en cada corte.
EPS_INTERVENIDAS_BASE = frozenset(
    {"NUEVA EPS", "COOSALUD", "EMSSANAR", "ASMET SALUD", "FAMISANAR", "SOS", "CAPRESOCA"}
)
# Savia Salud (EPS principal en 73 de los 125 municipios de Antioquia) figuraba
# como intervenida en nov-2025 y no aparece en el listado de oct-2026.
INCLUIR_SAVIA_COMO_INTERVENIDA = os.getenv("INCLUIR_SAVIA", "0") == "1"
EPS_INTERVENIDAS = (
    EPS_INTERVENIDAS_BASE | {"SAVIA SALUD"} if INCLUIR_SAVIA_COMO_INTERVENIDA else EPS_INTERVENIDAS_BASE
)

# Departamento para el zoom del EDA (None = ninguno)
DEPTO_FOCO = os.getenv("DEPTO_FOCO", "ANTIOQUIA") or None

# Umbral para la clasificación exploratoria (todavía no es el índice final)
UMBRAL_DEPENDENCIA_INTERVENIDAS = 0.50  # >= 50 % de afiliados en EPS intervenidas
HHI_MUY_CONCENTRADO = 2500

# Grupos de edad de la BDUA, en orden. Si la ADRES agrega uno nuevo, la
# validación de limpieza se detiene y pide actualizar esta lista.
ORDEN_EDAD = [
    "< 1",
    "1 a 5",
    "5 a 15",
    "15 a 19",
    "19 a 45",
    "45 a 50",
    "50 a 55",
    "55 a 60",
    "60 a 65",
    "65 a 70",
    "70 a 75",
    "> 75",
]


def ruta_raw(fecha: str) -> Path:
    return RAW_DIR / fecha


def ultimo_corte() -> str:
    """Devuelve la fecha del corte a procesar.

    Prioridad: FECHA_CORTE (variable de entorno) y, si no está, la carpeta más
    reciente de data/raw/. Falla con un mensaje claro si no hay ninguna.
    """
    if FECHA_CORTE:
        return FECHA_CORTE
    cortes = sorted(p.name for p in RAW_DIR.glob("????-??-??") if p.is_dir())
    if not cortes:
        raise FileNotFoundError(f"No hay cortes en {RAW_DIR}. Ejecute primero: make extract")
    return cortes[-1]
