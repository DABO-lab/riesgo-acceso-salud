"""Tablas de referencia revisadas a mano.

Esto es conocimiento del dominio, no lógica: por eso vive separado de clean.py.
Cuando aparezca un municipio "sin cruce" o una EPS nueva, se corrige AQUÍ y
nada más.
"""

# Departamentos que la BDUA escribe distinto al DANE (ya normalizados)
ALIAS_DPTO = {
    "VALLE": "VALLE DEL CAUCA",
    "SAN ANDRES": "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA",
    "BOGOTA": "BOGOTA D C",
}

# (departamento BDUA, municipio BDUA) -> código DIVIPOLA.
# Revisado uno a uno contra DIVIPOLA (DANE). Sin esta tabla se perdían
# 54 municipios con 3,6 millones de afiliados (Cúcuta, Cartagena, Tumaco, Buga...).
HOMOLOGACION_MANUAL = {
    ("ANTIOQUIA", "ANTIOQUIA"): "05042",  # Santa Fe de Antioquia
    ("ANTIOQUIA", "BOLIVAR"): "05101",  # Ciudad Bolívar
    ("ANTIOQUIA", "CARMEN DE VIBORAL"): "05148",
    ("ANTIOQUIA", "DON MATIAS"): "05237",
    ("ANTIOQUIA", "SAN ANDRES"): "05647",  # San Andrés de Cuerquia
    ("ANTIOQUIA", "SAN PEDRO"): "05664",  # San Pedro de los Milagros (San Pedro de Urabá viene aparte)
    ("ANTIOQUIA", "SANTUARIO"): "05697",
    ("ANTIOQUIA", "SAN VICENTE"): "05674",  # San Vicente Ferrer
    ("AMAZONAS", "MIRITIÑPARANA"): "91460",
    ("AMAZONAS", "PTO SANTANDER"): "91669",
    ("ATLANTICO", "POLO NUEVO"): "08558",
    ("BOLIVAR", "CARTAGENA"): "13001",
    ("BOLIVAR", "MOMPOS"): "13468",
    ("BOYACA", "GUICAN"): "15332",
    ("BOYACA", "TUTASA"): "15839",  # Tutazá
    ("CALDAS", "SAN JOSE DE CALDAS"): "17665",
    ("CAQUETA", "SAN JOSE DE FRAGUA"): "18610",
    ("CAUCA", "PATIA (EL BORDO)"): "19532",
    ("CAUCA", "PIENDAMO"): "19548",
    ("CAUCA", "SOTARA"): "19760",
    ("CESAR", "CODAZZI"): "20013",
    ("CESAR", "LA PAZ  ROBLES"): "20621",
    ("CHOCO", "BELEN DE BAJIRA"): "27493",
    ("CHOCO", "CANTON DE SAN PABLO"): "27135",
    ("CHOCO", "EL CARMEN"): "27245",  # El Carmen de Atrato
    ("CHOCO", "ITSMINA"): "27361",
    ("CORDOBA", "PURISIMA"): "23586",
    ("CUNDINAMARCA", "EL PEÑOL"): "25258",  # El Peñón
    ("CUNDINAMARCA", "S.ANTONIO TEQUENDAMA"): "25645",
    ("CUNDINAMARCA", "SAN JUAN DE RIO SECO"): "25662",
    ("CUNDINAMARCA", "UBATE"): "25843",
    ("GUAINIA", "BARRANCO MINAS"): "94343",
    ("GUAINIA", "MORICHAL NUEVO"): "94888",
    ("MAGDALENA", "CERRO SAN ANTONIO"): "47161",
    ("MAGDALENA", "EL PIJI¥O DEL CARMEN"): "47545",
    ("MAGDALENA", "SABANA DE SAN ANGEL"): "47660",
    ("MAGDALENA", "SAN SEBASTIAN BUENAVIST"): "47692",
    ("META", "LA URIBE"): "50370",
    ("META", "SAN CARLOS GUAROA"): "50680",
    ("META", "VISTA HERMOSA"): "50711",
    ("NARINO", "CUASPUD"): "52224",
    ("NARINO", "EL TABLON"): "52258",
    ("NARINO", "FRANCIS PIZARRO"): "52520",
    ("NARINO", "LEYVA"): "52405",
    ("NARINO", "TUMACO"): "52835",
    ("NORTE DE SANTANDER", "CUCUTA"): "54001",
    ("RISARALDA", "DOS QUEBRADAS"): "66170",
    ("SANTANDER", "EL CARMEN"): "68235",  # El Carmen de Chucurí
    ("SUCRE", "SINCE"): "70742",
    ("SUCRE", "TOLU"): "70820",
    ("SUCRE", "TOLUVIEJO"): "70823",
    ("TOLIMA", "GUAYABAL"): "73055",  # Armero (cabecera: Guayabal)
    ("TOLIMA", "MARIQUITA"): "73443",
    ("TOLIMA", "VILLA HERMOSA"): "73870",
    ("VALLE", "BUGA"): "76111",
}

# Áreas sin código municipal: se reportan y quedan fuera de la tabla municipal
AREAS_NO_MUNICIPALIZADAS = {("GUAINIA", "DPTO GUAINIA"), ("VAUPES", "DPTO VAUPES")}

# (palabra clave en el nombre normalizado, nombre canónico). EL ORDEN IMPORTA:
# gana la primera regla que coincida.
REGLAS_EPS = [
    ("NUEVA EPS", "NUEVA EPS"),
    ("COOSALUD", "COOSALUD"),
    ("MUTUAL SER", "MUTUAL SER"),
    ("SALUD TOTAL", "SALUD TOTAL"),
    ("EMSSANAR", "EMSSANAR"),
    ("SAVIA", "SAVIA SALUD"),
    ("SANITAS", "SANITAS"),
    ("ASMET", "ASMET SALUD"),
    ("PROTEGER", "PROTEGER"),
    ("CAPITAL SALUD", "CAPITAL SALUD"),
    ("SURAMERICANA", "SURA"),
    ("FAMISANAR", "FAMISANAR"),
    ("COMPENSAR", "COMPENSAR"),
    ("SERVICIO OCCIDENTAL", "SOS"),
    ("CAPRESOCA", "CAPRESOCA"),
    ("MALLAMAS", "MALLAMAS"),
    ("FAMILIAR DE COLOMBIA", "FAMILIAR DE COLOMBIA"),
    ("CABILDOS INDIGENAS DEL CESAR", "DUSAKAWI"),
    ("ANAS WAY", "ANAS WAYUU"),
    ("INDIGENA DEL CAUCA", "AIC"),
    ("PIJAOS", "PIJAOS SALUD"),
    ("ORIENTE COL", "COMFAORIENTE"),
    ("VALLE DEL C", "COMFENALCO VALLE"),
    ("DEL CHOCO", "COMFACHOCO"),
    ("SALUD MIA", "SALUD MIA"),
    ("ALIANSALUD", "ALIANSALUD"),
    ("FERROCARRILES", "FERROCARRILES"),
    ("EMPRESAS PUBLICAS DE MEDELLIN", "EPM"),
]
