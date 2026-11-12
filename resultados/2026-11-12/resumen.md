# Resultados del corte 2026-11-12

## 1. Índice de riesgo de acceso
El índice va de 0 (menor riesgo) a 100 (mayor riesgo). Combina, en percentiles, estos componentes: dependencia 35%, oferta 30%, concentracion 15%, ruralidad 10%, subsidiado 10%.

| Nivel | Municipios | Afiliados |
|---|---|---|
| Bajo | 337 | 38.797.172 |
| Medio | 448 | 7.225.494 |
| Alto | 224 | 2.688.502 |
| Muy alto | 113 | 1.440.693 |

**Robustez del índice**
- Al mover los pesos al azar 500 veces, la correlación de Spearman
  mediana con el ranking original es 0,983
  (en el 5 % de los peores casos, 0,937).
- Con pesos obtenidos por PCA, la correlación con el índice es 0,627
  y coinciden el 26 % de los municipios del 10 % de mayor riesgo (Jaccard).

### Los 15 municipios con mayor índice de riesgo
| # | Municipio | Departamento | Índice | % EPS intervenidas | IPS por 10.000 | EPS principal |
|---|---|---|---|---|---|---|
| 1 | Argelia | Cauca | 92,9 | 100 % | 0,74 | ASMET SALUD |
| 2 | Leiva | Nariño | 89,9 | 100 % | 1,14 | ASMET SALUD |
| 3 | Mogotes | Santander | 88,6 | 100 % | 1,08 | NUEVA EPS |
| 4 | La Montañita | Caquetá | 88,3 | 100 % | 1,51 | ASMET SALUD |
| 5 | Florencia | Cauca | 87,7 | 100 % | 1,75 | ASMET SALUD |
| 6 | Solita | Caquetá | 86,8 | 100 % | 1,15 | ASMET SALUD |
| 7 | La Belleza | Santander | 85,2 | 100 % | 1,65 | COOSALUD |
| 8 | San Calixto | Norte De Santander | 84,8 | 100 % | 0,97 | NUEVA EPS |
| 9 | Hacarí | Norte De Santander | 84,4 | 100 % | 0,93 | COOSALUD |
| 10 | Balboa | Cauca | 84,2 | 100 % | 1,92 | ASMET SALUD |
| 11 | El Retorno | Guaviare | 84,1 | 100 % | 1,73 | NUEVA EPS |
| 12 | Solano | Caquetá | 83,9 | 100 % | 2,05 | ASMET SALUD |
| 13 | Valparaíso | Caquetá | 83,5 | 100 % | 1,79 | ASMET SALUD |
| 14 | Landázuri | Santander | 82,8 | 100 % | 1,87 | NUEVA EPS |
| 15 | Aratoca | Santander | 82,7 | 100 % | 1,45 | COOSALUD |

## 2. Grupos de municipios (clustering)
Modelo elegido: **kmeans con k = 3**
(silhouette 0,236, Davies-Bouldin 1,50,
estabilidad ARI 0,83, grupo más pequeño 25,3 %).
Se compararon 15 combinaciones de algoritmo y número de grupos.
Cumple la regla de selección: se promovió a producción en MLflow.

| Grupo | Municipios | Afiliados | Índice promedio | Rasgos principales |
|---|---|---|---|---|
| 1 | 450 | 5.351.219 | 63,6 | alta dependencia de EPS intervenidas, afiliación muy concentrada |
| 2 | 388 | 5.951.596 | 43,2 | baja dependencia de EPS intervenidas, muy subsidiado |
| 3 | 284 | 38.849.046 | 37,8 | más contributivo, más urbano, afiliación más diversificada |

## 3. Monitoreo
- Sin alertas: los datos se mantienen estables frente al corte anterior.
