# Guía para el tablero en Power BI

## Archivos a cargar (carpeta `resultados/<fecha>/`)
| Archivo | Qué tiene | Relación |
|---|---|---|
| `municipios_riesgo.csv` | Una fila por municipio: indicadores, índice, nivel, grupo, coordenadas | Tabla principal |
| `perfiles_grupos.csv` | Una fila por grupo: tamaño, promedios y descripción | `grupo` ↔ `municipios_riesgo[grupo]` |
| `resumen_departamentos.csv` | Una fila por departamento | `dpto` ↔ `municipios_riesgo[dpto]` |
| `resumen_eps.csv` | Afiliados por EPS y si está intervenida | Sin relación (tabla de apoyo) |

En Power BI: **Obtener datos → Texto/CSV**. Al importar, la columna `cod_mpio` debe quedar como **Texto**, no como número, para no perder el cero inicial.

## Página 1 · Panorama nacional
- **Tarjetas:**
    - Municipios en nivel "Muy alto".
    - Afiliados en nivel "Muy alto".
    - % nacional en EPS intervenidas. Es una medida: `DIVIDE(SUMX(municipios_riesgo, [pct_intervenidas]*[afiliados]), SUM([afiliados]))`.
- **Mapa** (objeto visual *Mapa*):
    - Latitud = `latitud`, Longitud = `longitud`.
    - Leyenda = `nivel_riesgo`, con colores de claro a oscuro: Bajo, Medio, Alto, Muy alto.
    - Tamaño = `afiliados`.
- **Segmentadores:** `dpto`, `nivel_riesgo`, `nombre_grupo`.

## Página 2 · Ranking
- **Tabla** ordenada por `ranking_riesgo` con estas columnas:
    - `nom_mpio`, `dpto`, `indice_riesgo`, `nivel_riesgo`.
    - `pct_intervenidas`, `ips_x_10mil`, `eps_principal`.
    - `prob_top10`: qué tan seguro es que el municipio esté en el 10 % de mayor riesgo.
- **Barras horizontales:** `indice_ponderado` por departamento (de `resumen_departamentos.csv`).

## Página 3 · Grupos
- **Tabla de `perfiles_grupos.csv`:** `nombre`, `municipios`, `afiliados`, `indice_promedio`, `descripcion`.
- **Gráfico de dispersión:**
    - X = `ips_x_10mil`, Y = `pct_intervenidas`.
    - Leyenda = `nombre_grupo`, Tamaño = `afiliados`.

## Actualización mensual
Cada mes, GitHub Actions crea una carpeta nueva en `resultados/`. Para actualizar el tablero, en Power BI se cambia la ruta en **Transformar datos → Configuración de origen de datos** y se da clic en **Actualizar**.
