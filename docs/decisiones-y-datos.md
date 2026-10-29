# Decisiones, calidad de datos y diccionario

## Decisiones de diseño

| Decisión | Por qué | Dónde se cambia |
|---|---|---|
| Trabajar con **todo el país** y Antioquia como zoom | Antioquia sola tiene 125 municipios, pocos para el clustering de la fase 2 | `DEPTO_FOCO` en `config.py` |
| Agregar la BDUA **en el servidor** (API SODA) | ~100 mil filas en lugar de ~2 millones | `extract.params_agregados` |
| Guardar cada descarga en `data/raw/<fecha>/` | El análisis no depende del portal y se pueden comparar cortes | `extract.descargar` |
| Contar afiliados "Activo" y "Protección Laboral" | Ambos tienen cobertura | — |
| Contar solo sedes de clase **IPS** del REPS | Los 54.657 profesionales independientes inflarían la oferta hospitalaria | `CLASE_IPS` en `config.py` |
| Lista de EPS intervenidas fija por corte | Cambia con el tiempo; se revisa en cada corte | `EPS_INTERVENIDAS_BASE` en `config.py` |
| Savia Salud **no** intervenida por defecto | No aparece en el listado de oct-2026 (sí en nov-2025) | `INCLUIR_SAVIA=1` |
| Umbral de alta dependencia: 50 % | Clasificación exploratoria; el índice final es de la fase 2 | `UMBRAL_DEPENDENCIA_INTERVENIDAS` |

EPS intervenidas (Vanguardia, 8-oct-2026, con base en la Supersalud): Nueva EPS,
Coosalud, Emssanar, Asmet Salud, Famisanar, SOS y Capresoca.

## Problemas de calidad encontrados y cómo se resuelven

| Problema | Ejemplo | Solución (código) |
|---|---|---|
| Departamentos con otro nombre | `VALLE`, `SAN ANDRES`, `BOGOTA` | `ALIAS_DPTO` en `catalogos.py` |
| Municipios con otro nombre | `CUCUTA` → `SAN JOSE DE CUCUTA`; `BUGA` → `GUADALAJARA DE BUGA` | `HOMOLOGACION_MANUAL` (55 casos) en `catalogos.py` |
| Error de codificación de la Ñ | `NARI¥O`, `EL PIJI¥O DEL CARMEN` | `clean.normalizar_texto` |
| Nombres de municipio repetidos entre departamentos | Varios `SAN PEDRO` y `BOLIVAR` | El cruce es por departamento + municipio |
| Áreas sin municipio | `DPTO. GUAINIA`, `DPTO. VAUPES` | Se reportan y quedan fuera de la tabla |
| Una EPS con varios códigos | Nueva EPS: 4 códigos (por régimen y `-CM`) | `REGLAS_EPS` en `catalogos.py` |
| Zona con seis nombres | `Urbana-Cabecera Municipal`, `Rural - Dispersal`... | `clean.zona_simple` → URBANA / RURAL |
| Código de municipio inexistente en el REPS | `27086` (4 sedes) | Se reporta y se excluye |
| Coordenadas con coma decimal | `6,246631` | `clean.preparar_divipola` |
| Datos personales en el REPS | Correos, teléfonos, cédulas | No se descargan (`COLS_REPS`) |

Sin la homologación manual se perdían 54 municipios con 3,6 millones de afiliados.
Con ella, el 100 % de los municipios de la BDUA queda con su código DIVIPOLA.

## Validaciones automáticas

`clean.validar` y `features.construir_tabla_municipal` detienen el proceso con un
mensaje que dice qué revisar si:

- hay afiliados nulos o negativos, o un régimen distinto de contributivo y subsidiado;
- aparece un grupo de edad que no está en `ORDEN_EDAD`;
- una EPS intervenida no aparece en la BDUA (regla de `REGLAS_EPS` desactualizada);
- algún municipio de la BDUA queda sin cruce con DIVIPOLA;
- las dos vistas de la BDUA (por EPS y demográfica) no suman lo mismo;
- un código de la homologación manual no existe en DIVIPOLA;
- la tabla municipal repite municipios, pierde afiliados o tiene indicadores fuera de rango.

Cada validación tiene una prueba con datos rotos a propósito en `tests/test_clean.py`.

## Diccionario de la tabla municipal

`data/processed/tabla_municipal_<fecha>.{parquet,csv}` — una fila por municipio de DIVIPOLA.

| Columna | Definición |
|---|---|
| `cod_mpio`, `cod_dpto` | Código DIVIPOLA del municipio (5 dígitos) y del departamento |
| `dpto`, `nom_mpio`, `tipo_municipio` | Nombres oficiales del DANE |
| `latitud`, `longitud` | Coordenadas de la cabecera |
| `afiliados` | Total de afiliados (contributivo + subsidiado) |
| `pct_subsidiado`, `pct_rural` | Proporción de afiliados en el régimen subsidiado y en zona rural |
| `pct_intervenidas` | Proporción de afiliados en EPS intervenidas |
| `n_eps` | Número de EPS con afiliados en el municipio |
| `hhi` | Índice Herfindahl-Hirschman (0–10.000; > 2.500 = muy concentrado) |
| `eps_principal`, `pct_eps_principal` | EPS con más afiliados y su participación |
| `sedes_ips`, `sedes_ips_publicas`, `sedes_ese` | Sedes de IPS habilitadas: total, públicas y de Empresas Sociales del Estado |
| `ips_x_10mil` | Sedes de IPS por cada 10.000 afiliados |
| `sin_ips` | `True` si el municipio no tiene ninguna sede de IPS |
| `cuadrante` | Clasificación exploratoria: dependencia (≥ 50 %) × oferta (≤ mediana) |

**HHI.** Se eleva al cuadrado la participación (en %) de cada EPS y se suma.
Con 60 % y 40 %: 60² + 40² = 5.200. Con una sola EPS: 10.000.

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
