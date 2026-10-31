# Usuario, beneficio y ética

Este documento responde tres preguntas de la rúbrica: **quién usa la herramienta y qué decide
con ella**, **qué valor genera y cómo se mide**, y **cómo se manejan el sesgo, la privacidad y la
interpretabilidad**. Las cifras son del corte del 29 de octubre de 2026 y se recalculan en cada
corte (`resultados/<fecha>/equidad.md`).

---

## 1. Usuario y decisión

| Usuario | Qué decide con la herramienta | Qué usa |
|---|---|---|
| **Secretarías de salud departamentales y municipales** | Dónde reforzar la red pública (ESE) y dónde preparar la atención si una EPS deja de responder | Ranking, mapa y grupos por departamento (Power BI) |
| **Superintendencia Nacional de Salud** | Qué territorios vigilar primero en el seguimiento de las EPS intervenidas | Ranking nacional, % de afiliados en EPS intervenidas por municipio |
| **Ministerio de Salud y ADRES** | Dónde se necesitaría capacidad de recepción si hay que reasignar afiliados | Afiliados por EPS y municipio, oferta de IPS |
| Veedurías, academia y periodistas (secundario) | Seguimiento ciudadano | Repositorio abierto y API |

**Qué no es:** no evalúa a pacientes ni a EPS individualmente, y no dice que un municipio "ya
perdió" el acceso. Es una herramienta de **priorización territorial**: ordena dónde mirar
primero, y la decisión la toma una persona.

## 2. Proceso actual y diferencia de la propuesta

Hoy la información necesaria existe, pero está dispersa en tres fuentes públicas que no se cruzan
fácilmente:

- **BDUA (ADRES):** afiliados por EPS y municipio.
- **REPS (Ministerio de Salud):** sedes de IPS.
- **DIVIPOLA (DANE):** códigos de municipio.

Cada fuente escribe los nombres de forma distinta. Sin la homologación del proyecto se perdían
**54 municipios con 3,6 millones de afiliados** (`docs/decisiones-y-datos.md`). Además, el
seguimiento de las EPS intervenidas suele mirarse por EPS, no por territorio.

| Hoy | Con el proyecto |
|---|---|
| Cruce manual, puntual y propenso a errores de nombres | Cruce automático con 14 contratos de calidad; si uno crítico falla, no se publica |
| Mirada por EPS | Mirada por municipio: dependencia de EPS intervenidas **frente a** oferta de IPS |
| Sin histórico comparable | Un corte cada mes (día 5), guardado y comparado con el anterior (PSI) |
| Resultado en una hoja de cálculo | Ranking, grupos, mapa, API y tablero; cada versión trazable en MLflow |

## 3. Beneficio e impacto medible

**Lo que muestra el primer corte:**

- **113 municipios en riesgo Muy alto**, con **1,44 millones de afiliados**. En los 15
  primeros, más del 99,8 % de los afiliados está en EPS intervenidas y hay entre 0,7 y 2,1 sedes
  de IPS por cada 10.000 afiliados.
- **446 municipios en el grupo de mayor riesgo** (5,3 millones de afiliados): alta dependencia de
  EPS intervenidas, afiliación concentrada en pocas EPS y ruralidad alta.
- Concentrar la vigilancia en el 10 % de mayor riesgo cubre al 2,9 % de los afiliados del país,
  que es donde una falla de la EPS deja menos alternativas.

**Indicadores para demostrar el valor:**

| Indicador | Cómo se mide | Meta de la prueba de concepto |
|---|---|---|
| Tiempo desde la publicación de los datos hasta el ranking actualizado | Programación del flow (Prefect / GitHub Actions) | Menos de 1 día (hoy: unos 60 segundos de cómputo) |
| Costo de operación | Datos abiertos + GitHub Actions + código abierto | Cero en licencias |
| Afiliados de municipios Muy alto con plan de contingencia | Lo reporta el usuario (secretaría) | Línea base en el piloto |
| Estabilidad del ranking ante cambios de pesos | Spearman en 500 simulaciones (en cada corte) | ≥ 0,90 (hoy 0,98) |
| Validación externa *(siguiente fase)* | Correlación entre el índice y las quejas (PQRD) o tutelas en salud por municipio | Positiva y significativa |

**Escalabilidad:** cubre los 1.122 municipios del país. Agregar una EPS a la lista de intervenidas
es cambiar una línea de `config/config.yaml`. La API permite que otro sistema consulte un
municipio o calcule el riesgo de un escenario ("¿qué pasa si intervienen la EPS X?") con
`POST /predict`.

---

## 4. Ética

### 4.1 Privacidad

- **No se usan datos personales.** La BDUA se descarga ya agregada por municipio, EPS, régimen y
  zona; nunca hay registros por persona. Del REPS se descargan solo las columnas de la sede
  (`COLS_REPS` en `extraccion.py`): ningún correo, teléfono, nombre de representante ni número de
  documento.
- **Minimización:** solo se piden al portal las columnas y agregaciones que usa el modelo, y la
  agregación la hace el propio servidor (`extraccion.consultas`).
- **Celdas pequeñas:** el municipio más pequeño tiene 57 afiliados (Papunahua, Vaupés). Las
  cifras ya son públicas con ese nivel de agregación. El proyecto no publica nada más fino que lo
  que publica la ADRES.
- **La API no recibe datos personales.** El contrato de entrada (Pydantic) solo acepta cinco
  indicadores municipales en rango.
- **Marco:** la Ley 1581 de 2012 (Habeas Data) y la Circular Externa 002 de 2024 de la SIC aplican
  al tratamiento de datos personales. Este proyecto no trata datos personales, pero sigue sus
  principios de finalidad y minimización.

### 4.2 Sesgo y equidad

El modelo no usa atributos protegidos (sexo, etnia, edad de una persona). El riesgo de sesgo
está en **qué territorios quedan por fuera de la atención**. Se separan los sesgos **deliberados**
de los **no deseados**:

**Deliberado:** la ruralidad y el régimen subsidiado suben el índice (10 % cada uno), porque las
poblaciones rurales y subsidiadas tienen menos alternativas si su EPS falla. Es una decisión a
favor de los más vulnerables y se declara.

**No deseados (medidos en cada corte por `equidad.py`):**

| Sesgo | Evidencia (corte 2026-10-29) | Efecto | Mitigación |
|---|---|---|---|
| **Medición de la oferta en poblaciones muy pequeñas** | 76 municipios con menos de 2.000 afiliados tienen una oferta mediana de 7,5 IPS por 10.000, contra 2,9 en el país. Pacoa (Vaupés): 10 sedes para 470 afiliados = 213 por 10.000 | El municipio parece bien atendido aunque esté a días de un hospital: **se subestima el riesgo en territorios dispersos**, sobre todo en la Amazonía y la Orinoquía | Alerta automática. Siguiente fase: oferta por distancia y municipios vecinos (lo pidió el profesor) |
| **Alcance: el índice mide un riesgo específico** | 77 de 491 municipios vulnerables (rurales y subsidiados) quedan en nivel Bajo (673.236 afiliados), porque su EPS principal no está intervenida. La Guajira no tiene ningún municipio en Alto o Muy alto | Leer "Bajo" como "buen acceso" sería un error | Regla de lectura en el tablero y en la API: **Bajo no significa buen acceso**. Lista de estos municipios en cada corte |
| **Ciudades vecinas** | Municipios junto a una ciudad grande pueden salir sobrestimados (Villa del Rosario, Muy alto) o subestimados (Jamundí, Bajo, aunque está en el cuadrante de riesgo del EDA) | Ranking distorsionado en áreas metropolitanas | Siguiente fase: oferta de vecinos y área metropolitana |
| **Población no afiliada invisible** | La BDUA solo cuenta afiliados | Quien no está afiliado no aparece en el índice | Declarado como limitación |
| **Cortes de fechas distintas** | BDUA de octubre de 2026; REPS de marzo de 2026 | La oferta puede estar desactualizada | Fecha de cada fuente en `metadatos_corte.json` |
| **Decisión sobre la lista de EPS intervenidas** | Con Savia Salud como intervenida, Antioquia cambia por completo | El resultado depende de una lista que cambia | Lista en la configuración, revisada en cada corte, y cambio de lista como causal de reentrenamiento |

**Tamaño del municipio.** El índice baja en los municipios grandes (Spearman de −0,27 con el
tamaño): solo el 1 % de los municipios con más de 100.000 afiliados está en Muy alto, contra el
14 % de los que tienen entre 5.000 y 20.000. Es esperable, porque las ciudades tienen más EPS y
más IPS. Por eso el ranking **no** se debe usar para repartir recursos per cápita sin ajustar por
población.

### 4.3 Interpretabilidad

El índice es **aditivo y transparente**: cada componente es un percentil de 0 a 100 multiplicado
por su peso. Cualquier persona puede reconstruir el resultado:

> **Argelia (Cauca), índice 93,0:** dependencia 94,9 × 0,35 + oferta 97,0 × 0,30 +
> concentración 76,3 × 0,15 + ruralidad 93,5 × 0,10 + subsidiado 98,8 × 0,10 = **93,0**

- Los cinco componentes van en `municipios_riesgo.csv` (columnas `comp_*`) y en el tablero, así
  que se ve **por qué** cada municipio está donde está.
- Los grupos del clustering se describen con palabras ("alta dependencia de EPS intervenidas,
  afiliación muy concentrada, muy rural"), no solo con un número.
- **La incertidumbre se muestra.** La columna `prob_top10` dice en cuántas de las 500
  simulaciones de pesos el municipio cae en el 10 % de mayor riesgo. 74 municipios están entre
  20 % y 80 %: su posición depende de los pesos y así se comunica.
- **Lo que no favorece al equipo también se publica:** con pesos de PCA el ranking cambia
  (Spearman 0,63) y el silhouette del clustering es bajo (0,24). Ambos están en la ficha del
  modelo.

### 4.4 Rendición de cuentas y supervisión humana

- **Decide una persona.** La herramienta prioriza y no ejecuta acciones. Esto sigue el criterio
  de transparencia y supervisión humana de la Sentencia T-323 de 2024 de la Corte Constitucional
  y los principios del CONPES 4144 de 2025 (Política Nacional de IA).
- **Trazabilidad:**
  - cada corte guarda los datos crudos, las validaciones (`calidad.json`), la auditoría de
    equidad (`equidad.json`), el monitoreo y el modelo;
  - cada versión del modelo queda en MLflow con sus métricas;
  - el alias de producción solo cambia si el modelo cumple la regla de selección.
- **Reproducible por terceros:** datos abiertos y repositorio público. Cualquiera puede repetir
  el cálculo y reportar un error en GitHub Issues.
- **Responsables:** el equipo mantiene la lista de EPS intervenidas y los pesos (`config.yaml`).
  Cualquier cambio pasa por un pull request revisado y con las pruebas en verde.

### 4.5 Riesgos de mal uso

| Mal uso | Por qué es un problema | Respuesta |
|---|---|---|
| Quitar recursos a municipios en nivel "Bajo" | Bajo solo mide el riesgo por EPS intervenidas (ver 4.2) | Advertencia explícita y lista de vulnerables en Bajo en cada corte |
| Estigmatizar a un municipio o a una EPS | El índice mide exposición, no la calidad de la EPS ni la gestión local | Lenguaje de "riesgo de acceso", no de "mal servicio" |
| Usar el ranking como verdad exacta | Hay incertidumbre por los pesos y por la medición de la oferta | Se publican `prob_top10`, la sensibilidad y las limitaciones |

---

## 5. Para la presentación (en 30 segundos)

1. **Usuario:** secretarías de salud y Supersalud, que necesitan saber **dónde** una falla de las
   EPS intervenidas deja a la gente sin alternativas.
2. **Beneficio:** un ranking mensual, automático y gratuito. Hoy señala 113 municipios y 1,44
   millones de afiliados en riesgo Muy alto.
3. **Ética:**
   - **Privacidad:** cero datos personales.
   - **Interpretabilidad:** índice aditivo que se puede reconstruir a mano, con su incertidumbre.
   - **Sesgo:** una auditoría automática en cada corte, que ya encontró sus propios puntos
     ciegos (territorios dispersos y municipios vulnerables con EPS no intervenidas).
