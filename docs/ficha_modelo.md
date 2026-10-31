# Ficha del modelo (model card)

## Qué hace
Asigna a cada municipio de Colombia:
1. Un **índice de riesgo de acceso a la salud** de 0 a 100 y un **nivel**: Bajo, Medio, Alto o Muy alto.
2. Un **grupo** de municipios con características parecidas, obtenido con clustering. El grupo 1 es el de mayor riesgo promedio.

## Para qué sirve y para qué no
- **Sirve para** priorizar dónde vigilar, dónde reforzar la red pública de IPS y dónde planear la reasignación de afiliados si una EPS falla.
- **No sirve para** evaluar a un paciente individual, ni para afirmar que un municipio "ya perdió" el acceso. Es una herramienta de priorización, no un diagnóstico.

## Datos
- BDUA de la ADRES (contributivo y subsidiado), agregada por municipio, EPS, régimen y zona.
- REPS del Ministerio de Salud: solo sedes de IPS.
- DIVIPOLA del DANE.
- **No se usan datos personales.** Del REPS no se descargan correos, teléfonos ni documentos.

## Índice de riesgo
| Componente | Variable | Sentido | Peso |
|---|---|---|---|
| Dependencia | % de afiliados en EPS intervenidas | más = más riesgo | 35 % |
| Oferta | Sedes de IPS por cada 10.000 afiliados | menos = más riesgo | 30 % |
| Concentración | HHI de EPS | más = más riesgo | 15 % |
| Ruralidad | % de afiliados rurales | más = más riesgo | 10 % |
| Subsidiado | % de afiliados en el régimen subsidiado | más = más riesgo | 10 % |

Cada variable se lleva a percentiles para que todas queden en la misma escala y los extremos no dominen. Los pesos los definió el equipo: dependencia y oferta son el núcleo del problema, y la ruralidad y el régimen indican vulnerabilidad. Para comprobar que la decisión no cambia todo, se hacen dos pruebas:
- **Sensibilidad:** 500 juegos de pesos al azar alrededor de los elegidos (distribución de Dirichlet). Se mide qué tanto cambia el ranking (correlación de Spearman) y el 10 % de mayor riesgo (índice de Jaccard).
- **PCA:** pesos alternativos tomados del primer componente principal.

## Clustering
- **Variables:** % en EPS intervenidas, HHI, IPS por 10.000 afiliados (en logaritmo), % rural y % subsidiado. Se excluye el % de la EPS principal porque tiene una correlación de 0,98 con el HHI.
- **Preparación:** log(1 + x) para la oferta de IPS y estandarización (media 0, desviación 1).
- **Candidatos:** K-means, jerárquico de Ward y mezcla gaussiana, con k = 3 a 7 (15 modelos).
- **Métricas:** silhouette, Davies-Bouldin, Calinski-Harabasz, tamaño del grupo más pequeño y estabilidad (ARI promedio en 20 muestras bootstrap).
- **Regla de selección:** grupo más pequeño de al menos el 5 % de los municipios, estabilidad de al menos 0,70 y, entre esos, el mayor silhouette.
- **Modelo final:** Pipeline de scikit-learn (preprocesamiento + centroide más cercano). Así asigna cualquier municipio o corte nuevo a un grupo. Se registra en el MLflow Model Registry con su firma (*signature*) y un ejemplo de entrada.
- **Promoción controlada:** el alias `produccion` solo se mueve a la nueva versión si el modelo cumple la regla de selección. Si ningún candidato la cumple, la versión queda registrada con la etiqueta `cumple_regla_seleccion = false` y el alias sigue en el modelo anterior.

### Resultado con el corte del 29 de octubre de 2026
- Solo 3 de los 15 candidatos cumplen la regla (K-means con k = 3, 4 y 7). Gana **K-means con k = 3**: silhouette 0,236, Davies-Bouldin 1,50, estabilidad 0,82 y grupo más pequeño con el 25,7 % de los municipios.
- El silhouette de 0,24 indica grupos que se solapan: los municipios forman un continuo. Los grupos sirven para describir perfiles; para priorizar se usa el índice.
- Sensibilidad de los pesos: Spearman mediano 0,983 (0,937 en el 5 % de los peores casos). Con pesos de PCA la correlación baja a 0,63 y solo coincide el 26 % del 10 % de mayor riesgo, porque PCA pondera por covariación (ruralidad, régimen y concentración se mueven juntos) y no por importancia para el acceso.

## Limitaciones conocidas
1. Los datos son agregados por municipio, no por paciente.
2. La oferta se mide en sedes, no en capacidad: no incluye camas, especialistas ni servicios habilitados.
3. No se sabe qué IPS tiene contrato con qué EPS.
4. Solo se cuentan las IPS dentro del municipio. Los municipios junto a una ciudad grande pueden usar las IPS de esa ciudad, así que su riesgo real podría ser menor.
5. La lista de EPS intervenidas cambia con el tiempo y es una decisión del equipo. Con Savia Salud como intervenida, los resultados de Antioquia cambian por completo.
6. El índice no tiene una "respuesta correcta" contra la cual compararlo. Su validez se apoya en la sensibilidad, en la comparación con PCA y en la coherencia de los perfiles.

Cada corte mide estos sesgos de forma automática (`equidad.py` → `resultados/<fecha>/equidad.md`).
Usuario, beneficio y ética: [etica_usuario_beneficio.md](etica_usuario_beneficio.md).

## Mantenimiento
- Se ejecuta cada mes con GitHub Actions.
- **Se reentrena si** alguna variable tiene un PSI mayor a 0,25 frente al corte anterior, si más del 15 % de los municipios cambia de nivel o si cambia la lista de EPS intervenidas.
- Cada versión del modelo queda en MLflow con sus métricas, para poder compararla con la anterior.
