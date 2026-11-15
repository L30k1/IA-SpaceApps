# Atención psicológica diaria

## 1. Metadatos del test

- **Nombre.** Registro diario de sueño y desempeño percibido.
- **Frecuencia.** El siguiente cuestionario se habilita 24 horas después del último registro diario de la cuenta. Se recomienda completarlo a una hora comparable respecto al inicio de turno.
- **Tiempo estimado.** Menos de 90 segundos para los cinco reactivos. La medición complementaria se realiza aparte.
- **Variables.** Sueño percibido, energía, interferencia del estrés, claridad y atención percibidas, y esfuerzo para sostener el desempeño habitual.

La redacción es propia de MediSpace. Los dominios se inspiran en el seguimiento de sueño y desempeño de NASA Spaceflight Standard Measures. La escala y la puntuación de esta ficha requieren validación antes de su uso como instrumento de tamizaje operativo. [NASA Spaceflight Standard Measures](https://www.nasa.gov/humans-in-space/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/)

## 2. Reactivos

Escala de acuerdo de 1 a 5 para todos los reactivos. **1** totalmente en desacuerdo, **2** en desacuerdo, **3** ni de acuerdo ni en desacuerdo, **4** de acuerdo y **5** totalmente de acuerdo.

| N.º | Texto | Variable |
| --- | --- | --- |
| 1 | El último periodo de sueño me permitió comenzar el día con descanso. | Sueño reparador |
| 2 | Tengo energía suficiente para mantener mi ritmo habitual de trabajo. | Energía percibida |
| 3 | La carga de estrés actual dificulta que realice mis tareas. | Interferencia del estrés, con puntuación invertida |
| 4 | Puedo mantener la atención y seguir los pasos de mis tareas con claridad. | Claridad mental y atención percibidas |
| 5 | Mantener mi ritmo habitual me exige más esfuerzo de lo normal. | Esfuerzo percibido, con puntuación invertida para compararlo con el reactivo 2 |

El quinto reactivo aporta una comparación descriptiva. Una diferencia puede reflejar cómo la persona interpreta la pregunta, cambios en el trabajo u otras circunstancias que convenga aclarar. La nota opcional permite registrar ese contexto.

## 3. Prueba objetiva complementaria

La PVT-B de 3 minutos presenta estímulos visuales a intervalos variables y registra el tiempo hasta la respuesta. Para comparar dos mediciones, usa una implementación del mismo protocolo con el mismo dispositivo y condiciones de aplicación comparables. Registra la mediana actual y la mediana de una medición de referencia individual, ambas en milisegundos. La prueba se realiza fuera del formulario y se reporta en el Diario de forma opcional. [Estudio de validación del PVT-B](https://pubmed.ncbi.nlm.nih.gov/22025811/)

Las dos medianas se muestran junto al autorreporte para revisión. Registra la hora, turno y condiciones de la prueba en la nota cuando aporten contexto. La aplicación mantiene por separado la medida objetiva y el índice subjetivo.

## 4. Lógica de cálculo y umbrales

| Medida | Cálculo y presentación |
| --- | --- |
| Índice descriptivo | `100 × (R1 + R2 + (6 − R3) + R4 − 4) / 16`. Va de 0 a 100. Un valor mayor representa respuestas más favorables dentro de esta ficha. |
| Diferencia de consistencia | `abs(R2 − (6 − R5))`. Va de 0 a 4 puntos y se muestra sin clasificación. El reactivo 5 queda fuera del índice para evitar ponderar la energía dos veces. |
| Cambio de latencia | `100 × (mediana actual − mediana de referencia) / mediana de referencia`. Un valor positivo indica más tiempo para responder. Se calcula solo si se informan ambas medianas positivas. |
| Datos faltantes | El índice requiere los cinco reactivos. La nota y la medición complementaria son opcionales. |
| Semáforo | Pendiente de validación. La ficha no tiene puntos de corte aprobados para verde, amarillo o rojo. La aplicación muestra valores y permite solicitar a la IA sugerencias basadas en el registro para revisión humana. |

La opción **Guardar y generar seguimiento con IA** envía los reactivos respondidos y el contexto aportado. Las respuestas originales y la orientación quedan en el expediente del titular. [OMS, orientación sobre IA generativa en salud](https://www.who.int/publications/i/item/9789240084759)
