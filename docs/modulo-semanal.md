# Atención psicológica semanal

## 1. Metadatos del test

- **Nombre.** Registro semanal de ánimo, desempeño y cohesión.
- **Frecuencia.** Una vez por semana. Cada registro abarca los siete días anteriores.
- **Tiempo estimado.** Entre 5 y 7 minutos con la nota de contexto. La prueba complementaria se realiza aparte.
- **Dominios.** Ánimo e interés, estrés operativo, sueño y desempeño, y cohesión de equipo.

La ficha usa reactivos originales de MediSpace. Sus dominios se inspiran en el seguimiento aeroespacial de ánimo, sueño y equipo y en los constructos de PHQ-9, GAD-7 y POMS. La redacción, el periodo de siete días y la puntuación corresponden a esta ficha y requieren validación propia. [NASA Spaceflight Standard Measures](https://www.nasa.gov/reference/standard-measures/), [NASA, informe de evidencia sobre equipos](https://ntrs.nasa.gov/citations/20220007465), [PHQ-9](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/), [GAD-7](https://pubmed.ncbi.nlm.nih.gov/16717171/)

## 2. Reactivos

Responde en cuántos de los últimos siete días ocurrió cada situación. **1** ningún día, **2** de 1 a 2 días, **3** de 3 a 4 días, **4** de 5 a 6 días y **5** los 7 días.

| N.º | Texto | Variable |
| --- | --- | --- |
| 1 | Encontré interés en mis tareas o actividades de descanso. | Interés |
| 2 | El desánimo interfirió con mi rutina. | Interferencia del desánimo, invertido |
| 3 | Terminé el turno con ánimo para retomar mis actividades habituales. | Ánimo al terminar el turno |
| 4 | Me costó dejar de pensar en posibles fallas después del turno. | Preocupación operativa, invertido |
| 5 | La tensión dificultó que me relajara fuera de turno. | Tensión fuera de turno, invertido |
| 6 | Pude mantener un ritmo de trabajo que me resultó manejable. | Manejo de la carga percibida |
| 7 | Tuve energía suficiente para mantener mi ritmo habitual. | Energía percibida |
| 8 | El sueño me permitió recuperarme entre turnos. | Recuperación por sueño |
| 9 | Me resultó fácil mantener la atención en mis tareas. | Atención percibida |
| 10 | Sentí que podía contar con la tripulación durante las tareas. | Apoyo percibido |
| 11 | Me resultó fácil comunicarme con el equipo sobre el trabajo. | Comunicación |
| 12 | Evité actividades del equipo aun cuando quería participar. | Retraimiento, invertido |
| 13 | Me costó sostener mi nivel de energía durante las tareas habituales. | Esfuerzo percibido, invertido para comparar con 7 |

Si un reactivo depende de una situación que no ocurrió, la nota puede aclarar el contexto de la respuesta. La misión y la nota son campos opcionales. Si hay una sola misión en curso con fechas completas, MediSpace la propone en el formulario.

## 3. Prueba objetiva complementaria

El formulario admite la mediana actual y la mediana de referencia individual de una PVT-B de 3 minutos realizada aparte. Registra ambas en milisegundos con el mismo protocolo, dispositivo y condiciones comparables. La medición se presenta junto al autorreporte y conserva su unidad original. [Estudio de validación del PVT-B](https://pubmed.ncbi.nlm.nih.gov/22025811/)

## 4. Lógica de cálculo y umbrales

Para cada dominio se aplica `25 × (promedio de tres reactivos ajustados − 1)`. Un valor mayor representa respuestas más favorables dentro del dominio. La transformación de un reactivo invertido es `6 − respuesta`.

| Medida | Cálculo |
| --- | --- |
| Ánimo e interés | 1, 2 invertido y 3. |
| Estrés operativo | 4 invertido, 5 invertido y 6. |
| Sueño y desempeño | 7, 8 y 9. |
| Cohesión de equipo | 10, 11 y 12 invertido. |
| Comparación de energía | `abs(R7 − (6 − R13))`, de 0 a 4 puntos. El reactivo 13 queda fuera de los índices. |
| Cambio de latencia | `100 × (mediana actual − mediana de referencia) / mediana de referencia`. Un porcentaje positivo indica que aumentó el tiempo de respuesta. |
| Cuarto de misión | Con inicio y fin válidos, `avance = días UTC transcurridos / duración en días`. Los intervalos son primero de 0 a menos de 25 %, segundo de 25 a menos de 50 %, tercero de 50 a menos de 75 % y cuarto de 75 a 100 %. Fuera de las fechas o sin duración calculable se omite el cuarto. |
| Semáforo | Pendiente de validación. Los dominios, el cuarto y los cambios de latencia se presentan como datos para el seguimiento, sin asignar categorías de riesgo. |

Si la persona solicita seguimiento con IA, el modelo recibe las respuestas, puntuaciones descriptivas, nota, medición complementaria y cuarto de misión cuando esté disponible. El registro y el seguimiento quedan en `semanal_psicologico` en el JSON del titular. El cuarto de misión aporta contexto temporal y las acciones quedan para revisión del equipo responsable.
