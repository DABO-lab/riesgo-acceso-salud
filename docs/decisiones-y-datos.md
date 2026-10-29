# Decisiones, calidad de datos y diccionario

## Decisiones de diseño

| Decisión | Por qué | Dónde se cambia |
|---|---|---|
| Trabajar con **todo el país** y Antioquia como zoom | Antioquia sola tiene 125 municipios, pocos para el clustering de la fase 2 | `eda.depto_foco` en `config.yaml` |
| Agregar la BDUA **en el servidor** (API SODA) | ~100 mil filas en lugar de ~2 millones | `extraccion.consultas` |
| Guardar cada descarga en `data/raw/<fecha>/` | El análisis no depende del portal y se pueden comparar cortes | `extraccion.extraer` |
| Contar afiliados "Activo" y "Protección Laboral" | Ambos tienen cobertura | — |
| Contar solo sedes de clase **IPS** del REPS | Los 54.657 profesionales independientes inflarían la oferta hospitalaria | `CLASE_IPS` en `extraccion.py` |
| Lista de EPS intervenidas fija por corte | Cambia con el tiempo; se revisa en cada corte | `eps_intervenidas.lista` en `config.yaml` |
| Savia Salud **no** intervenida por defecto | No aparece en el listado de oct-2026 (sí en nov-2025) | agregarla a `eps_intervenidas.lista` |
| Umbral de alta dependencia: 50 % | Clasificación exploratoria del EDA; para priorizar se usa el índice | `eda.umbral_dependencia` |
| Índice con pesos por criterio, no por PCA | Dependencia y oferta son el núcleo del problema; PCA pondera por covariación | `indice.componentes` en `config.yaml` |
| Modelo no supervisado (índice + clustering) | No existe una variable que diga "este municipio perdió acceso" | — |

EPS intervenidas (Vanguardia, 8-oct-2026, con base en la Supersalud): Nueva EPS,
Coosalud, Emssanar, Asmet Salud, Famisanar, SOS y Capresoca.

## Problemas de calidad encontrados y cómo se resuelven

| Problema | Ejemplo | Solución (código) |
|---|---|---|
| Departamentos con otro nombre | `VALLE`, `SAN ANDRES`, `BOGOTA` | `ALIAS_DPTO` en `limpieza.py` |
| Municipios con otro nombre | `CUCUTA` → `SAN JOSE DE CUCUTA`; `BUGA` → `GUADALAJARA DE BUGA` | `HOMOLOGACION_MANUAL` (55 casos) en `limpieza.py` |
| Error de codificación de la Ñ | `NARI¥O`, `EL PIJI¥O DEL CARMEN` | `limpieza.normalizar_texto` |
| Nombres de municipio repetidos entre departamentos | Varios `SAN PEDRO` y `BOLIVAR` | El cruce es por departamento + municipio |
| Áreas sin municipio | `DPTO. GUAINIA`, `DPTO. VAUPES` | Se reportan y quedan fuera de la tabla |
| Una EPS con varios códigos | Nueva EPS: 4 códigos (por régimen y `-CM`) | `REGLAS_EPS` en `limpieza.py` |
| Zona con seis nombres | `Urbana-Cabecera Municipal`, `Rural - Dispersal`... | `limpieza.zona_simple` → URBANA / RURAL |
| Código de municipio inexistente en el REPS | `27086` (4 sedes) | Se reporta y se excluye |
| Coordenadas con coma decimal | `6,246631` | `limpieza.preparar_divipola` |
| Datos personales en el REPS | Correos, teléfonos, cédulas | No se descargan (`COLS_REPS` en `extraccion.py`) |

Sin la homologación manual se perdían 54 municipios con 3,6 millones de afiliados.
Con ella, el 100 % de los municipios de la BDUA queda con su código DIVIPOLA.

## Validaciones automáticas

`validacion.py` revisa cada corte y guarda el resultado en `resultados/<fecha>/calidad.json`.
Si un chequeo **crítico** falla, el pipeline se detiene antes de entrenar:

- afiliados no nulos ni negativos, y total nacional de al menos 45 millones;
- las dos vistas de la BDUA (por EPS y demográfica) suman lo mismo;
- solo dos regímenes y ningún grupo de edad desconocido;
- como máximo 0,1 % de afiliados sin código DIVIPOLA;
- todas las EPS intervenidas aparecen en la BDUA;
- DIVIPOLA completa y REPS con sedes;
- la tabla municipal tiene un municipio por fila, conserva el total de afiliados y sus proporciones y HHI están en rango.

Los no críticos (variación del total frente al corte anterior mayor al 10 %, nulos en las
variables del modelo) solo generan un aviso. Hay pruebas con datos rotos a propósito en
`tests/test_limpieza.py`.

El diccionario de columnas está en [diccionario_datos.md](diccionario_datos.md).

## Tamaño de las fuentes (revisado el 19 y el 25 de octubre de 2026)

| Base | Corte | Tamaño original | Lo que se descarga |
|---|---|---|---|
| BDUA contributivo | 2-oct-2026 | 637.506 filas · 23,1 M afiliados | ~28.000 filas (EPS) + ~26.000 (demografía) |
| BDUA subsidiado | 3-oct-2026 | 1.341.642 filas · 27,0 M afiliados | ~25.000 filas (EPS) + ~27.000 (demografía) |
| REPS | 12-mar-2026 | 76.821 sedes · 19.551 IPS | 19.551 filas |
| DIVIPOLA | ene-2025 | 1.122 municipios | 1.122 filas |

## Limitaciones

1. **Datos agregados.** La BDUA no tiene registros por paciente: el análisis es municipal.
2. **Oferta aproximada.** El REPS cuenta sedes, no capacidad, ni qué IPS contrata con qué EPS.
3. **Municipios vecinos.** Solo se cuentan las IPS dentro del municipio (Jamundí, Girón,
   Villa del Rosario, Madrid y Mosquera están junto a una ciudad grande).
4. **Cortes distintos.** BDUA de octubre de 2026 y REPS de marzo de 2026.
5. **Lista de EPS intervenidas cambiante.** La decisión sobre Savia Salud cambia Antioquia por completo.
6. **Sin histórico en el portal.** Las tendencias solo salen de acumular cortes en `data/raw/`.

## Fuentes

- [BDUA régimen contributivo – ADRES](https://www.datos.gov.co/d/tq4m-hmg2)
- [BDUA régimen subsidiado – ADRES](https://www.datos.gov.co/d/d7a5-cnra)
- [Registro Especial de Prestadores (REPS) – MinSalud](https://www.datos.gov.co/d/c36g-9fc2)
- [DIVIPOLA – DANE](https://www.datos.gov.co/d/gdxc-w37w)
- Vanguardia, EPS intervenidas, 8 de octubre de 2026.
- La Silla Vacía, interventores de las 8 EPS, noviembre de 2025.
