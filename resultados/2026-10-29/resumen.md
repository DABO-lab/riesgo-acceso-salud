# Resultados del corte 2026-10-29

## 1. Índice de riesgo de acceso
El índice va de 0 (menor riesgo) a 100 (mayor riesgo). Combina, en percentiles, estos componentes: dependencia 35%, oferta 30%, concentracion 15%, ruralidad 10%, subsidiado 10%.

| Nivel | Municipios | Afiliados |
|---|---|---|
| Bajo | 337 | 38.780.597 |
| Medio | 448 | 7.228.553 |
| Alto | 224 | 2.688.536 |
| Muy alto | 113 | 1.436.335 |

**Robustez del índice**
- Al mover los pesos al azar 500 veces, la correlación de Spearman
  mediana con el ranking original es 0,983
  (en el 5 % de los peores casos, 0,937).
- Con pesos obtenidos por PCA, la correlación con el índice es 0,626
  y coinciden el 26 % de los municipios del 10 % de mayor riesgo (Jaccard).

### Los 15 municipios con mayor índice de riesgo
| # | Municipio | Departamento | Índice | % EPS intervenidas | IPS por 10.000 | EPS principal |
|---|---|---|---|---|---|---|
| 1 | Argelia | Cauca | 93,0 | 100 % | 0,74 | ASMET SALUD |
| 2 | Leiva | Nariño | 90,1 | 100 % | 1,14 | ASMET SALUD |
| 3 | Mogotes | Santander | 88,5 | 100 % | 1,08 | NUEVA EPS |
| 4 | Florencia | Cauca | 87,6 | 100 % | 1,75 | ASMET SALUD |
| 5 | Solita | Caquetá | 87,0 | 100 % | 1,15 | ASMET SALUD |
| 6 | La Montañita | Caquetá | 86,5 | 100 % | 1,50 | ASMET SALUD |
| 7 | Balboa | Cauca | 86,3 | 100 % | 1,92 | ASMET SALUD |
| 8 | La Belleza | Santander | 85,1 | 100 % | 1,65 | COOSALUD |
| 9 | San Calixto | Norte De Santander | 84,9 | 100 % | 0,97 | NUEVA EPS |
| 10 | Hacarí | Norte De Santander | 84,5 | 100 % | 0,93 | COOSALUD |
| 11 | El Retorno | Guaviare | 84,3 | 100 % | 1,73 | NUEVA EPS |
| 12 | Solano | Caquetá | 84,1 | 100 % | 2,06 | ASMET SALUD |
| 13 | Valparaíso | Caquetá | 83,8 | 100 % | 1,78 | ASMET SALUD |
| 14 | Landázuri | Santander | 83,0 | 100 % | 1,87 | NUEVA EPS |
| 15 | Aratoca | Santander | 82,9 | 100 % | 1,45 | COOSALUD |

## 2. Grupos de municipios (clustering)
Modelo elegido: **kmeans con k = 3**
(silhouette 0,236, Davies-Bouldin 1,50,
estabilidad ARI 0,82, grupo más pequeño 25,7 %).
Se compararon 15 combinaciones de algoritmo y número de grupos.
Cumple la regla de selección: se promovió a producción en MLflow.

| Grupo | Municipios | Afiliados | Índice promedio | Rasgos principales |
|---|---|---|---|---|
| 1 | 446 | 5.277.945 | 63,5 | alta dependencia de EPS intervenidas, afiliación muy concentrada, muy rural |
| 2 | 388 | 5.960.796 | 43,3 | baja dependencia de EPS intervenidas, muy subsidiado |
| 3 | 288 | 38.895.280 | 38,2 | más contributivo, más urbano, afiliación más diversificada |

## 3. Monitoreo
- Primer corte: todavía no hay un corte anterior para comparar.
