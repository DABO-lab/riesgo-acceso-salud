# Diccionario de datos · `municipios_riesgo.csv`

| Columna | Descripción |
|---|---|
| `cod_mpio` | Código DIVIPOLA del municipio (5 dígitos, texto) |
| `cod_dpto`, `dpto`, `nom_mpio` | Código y nombre del departamento y del municipio (DANE) |
| `tipo_municipio` | Municipio, isla o área no municipalizada (DANE) |
| `latitud`, `longitud` | Coordenadas de la cabecera (DANE) |
| `afiliados` | Total de afiliados, contributivo + subsidiado (BDUA) |
| `pct_subsidiado` | Proporción de afiliados en el régimen subsidiado |
| `pct_rural` | Proporción de afiliados en zona rural |
| `pct_intervenidas` | Proporción de afiliados en EPS intervenidas |
| `n_eps` | Número de EPS con afiliados en el municipio |
| `eps_principal`, `pct_eps_principal` | EPS con más afiliados y su participación |
| `eps_principal_intervenida` | La EPS principal está intervenida (True/False) |
| `hhi` | Índice Herfindahl-Hirschman de concentración de EPS (0-10.000; más de 2.500 = muy concentrado) |
| `sedes_ips`, `sedes_ips_publicas`, `sedes_ese` | Sedes de IPS habilitadas: total, públicas y Empresas Sociales del Estado (REPS) |
| `ips_x_10mil` | Sedes de IPS por cada 10.000 afiliados |
| `comp_dependencia` … `comp_subsidiado` | Componentes del índice en percentiles (100 = más riesgo) |
| `indice_riesgo` | Índice de riesgo de acceso (0-100) |
| `nivel_riesgo` | Bajo (30 % de municipios), Medio (40 %), Alto (20 %), Muy alto (10 %) |
| `ranking_riesgo` | Posición nacional (1 = mayor riesgo) |
| `prob_top10` | Proporción de las 500 simulaciones de pesos en que el municipio quedó en el 10 % de mayor riesgo |
| `grupo`, `nombre_grupo`, `descripcion_grupo` | Grupo del clustering (1 = mayor riesgo promedio) y sus rasgos principales |
