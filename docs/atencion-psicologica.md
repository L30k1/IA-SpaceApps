# Base de diseño para Atención psicológica

La IA diseña y estructura instrumentos de tamizaje preventivo, encuestas de monitoreo operativo y pruebas de rendimiento cognitivo para entornos aislados, confinados y extremos (ICE). Sus propuestas se destinan a revisión por el equipo responsable. Su función se limita al diseño y al seguimiento. Los diagnósticos, la atención clínica y las decisiones de aptitud corresponden a profesionales.

## Marcos de referencia

- **NASA Behavioral Health and Performance (BHP).** Usar la documentación pública del Centro Espacial Johnson sobre salud conductual y desempeño individual y grupal. Aplicar el contexto de ISS, Artemis y misiones proyectadas a Marte según la evidencia disponible para cada entorno. [NASA BHP](https://www.nasa.gov/reference/jsc-behavioral-health/)
- **NASA Spaceflight Standard Measures.** Considerar el registro comparable de sueño, estado de ánimo, rendimiento cognitivo y cohesión, incluida la comparación entre medidas subjetivas y objetivas. [NASA Spaceflight Standard Measures](https://www.nasa.gov/humans-in-space/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/)
- **Misiones análogas.** Considerar Mars500 (IBMP/ESA, 520 días), HI-SEAS, HERA y estaciones antárticas como Concordia y McMurdo. Identificar el entorno original y las limitaciones para trasladar resultados de un análogo a otra misión. [NASA Human Factors and Behavioral Performance](https://www.nasa.gov/hrp/human-factors-and-behavioral-performance/)

| Instrumento | Variables que orientan el diseño |
| --- | --- |
| PHQ-9 | Interés, estado de ánimo, fatiga, apetito, autoevaluación y cambios psicomotores. [Estudio original](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/) |
| GAD-7 | Nerviosismo, preocupación difícil de controlar, inquietud e irritabilidad. [Estudio original](https://pubmed.ncbi.nlm.nih.gov/16717171/) |
| STAI | Diferencia entre ansiedad rasgo y ansiedad estado tras una falla técnica, una EVA o una emergencia. |
| POMS | Tensión, depresión, hostilidad, vigor, fatiga y confusión. |
| PSQI y KSS | Latencia, despertares, eficiencia y percepción del descanso, y somnolencia subjetiva. |
| PVT | Tiempo de reacción y lapsos de atención. Registrar la versión, duración, dispositivo y definición de lapso. La solicitud propone lapsos de más de 500 ms y una prueba breve de 60 segundos. Verificar la combinación para la versión elegida antes de aplicarla. |

Cada ítem, escala, métrica y umbral debe tener una fuente dentro de estos marcos. Toda adaptación debe indicar su origen y estado de validación. Verificar permisos antes de reproducir ítems de instrumentos estandarizados.

## Fenómenos e indicadores a considerar

| Fenómeno propuesto | Indicadores que se pidió monitorear |
| --- | --- |
| Síntomas depresivos y fenómeno del tercer cuarto (Bechtel y Berning) | Pérdida de interés en tareas o recreación, sensación de estancamiento, desmotivación y baja energía. Comparar cambios en moral o tensión interpersonal con la fase de la misión. Tratar el tercer cuarto como una hipótesis para observar, sin dar por hecho que ocurra. |
| Ansiedad operativa, hipervigilancia y pánico situacional | Dificultad para relajarse fuera de turno, preocupación reiterada por fallos técnicos, tensión física reportada y sensación de perder el control. Registrar la relación temporal con eventos como despresurización, incendios o cortes de comunicación. |
| Astenización espacial (literatura Roscosmos e IBMP) | Fatiga mental ante tareas sencillas, sensibilidad a ruido o luz, irritabilidad, cambios emocionales y tolerancia a la frustración. Registrar condiciones de trabajo, ruido, carga y confinamiento para contextualizar. |
| Disrupción circadiana y trastornos del sueño | Dificultad para conciliar el sueño, despertares, sueño poco reparador, uso reportado de somníferos o estimulantes y somnolencia en el turno. Considerar los horarios y las condiciones de iluminación. |
| Niebla espacial y cambios cognitivos | Lentitud percibida, fallos de memoria de trabajo, dificultad de atención y errores operativos. Registrar fatiga y condiciones ambientales, como CO₂ si hay mediciones, para revisión de las posibles asociaciones. |
| Aislamiento, retraimiento y conflictos interpersonales | Evitación de actividades grupales, dificultades de comunicación, percepción de reparto injusto de tareas, irritación y soledad. Considerar también la privacidad y el contacto con familiares y con control de misión. |
| Fenómeno break-off (Clark y Graybiel) | Sensación de irrealidad, extrañamiento, vacío o desconexión emocional, incluida la experiencia al mirar la Tierra o comunicarse con casa. Registrar el contexto del autorreporte. |

## Diseño y puntuación

1. **Reducir el subregistro.** Preguntar por esfuerzo, energía y desempeño sin emplear etiquetas clínicas. Proponer ítems inversos para revisar consistencia cuando su redacción sea comprensible. Contrastar el autorreporte con medidas objetivas comparables, como tiempo de reacción o aciertos en memoria de trabajo, cuando estén disponibles.
2. **Separar los módulos por frecuencia.** El diario se plantea para menos de 90 segundos con VAS de 0 a 100 o Likert de 1 a 5 para sueño, energía, estrés y claridad mental. El semanal se plantea para 5 a 7 minutos con dominios de PHQ-9, GAD-7, POMS y cohesión, y considera la fase de misión. El módulo posterior a un evento crítico considera ansiedad de estado según STAI y recoge el contexto de la emergencia o EVA.
3. **Explicitar la lógica de cálculo.** Documentar la dirección de cada escala, cómo se obtiene la línea base, la fórmula de desviación, la incertidumbre, el procedimiento ante datos faltantes y los criterios de discrepancia. Los valores solicitados abajo son propuestas para revisión y requieren evidencia antes de usarse operacionalmente.

| Parámetro propuesto en la solicitud | Umbral y acción para revisar |
| --- | --- |
| Discrepancia de fatiga | Si el autorreporte indica ausencia de fatiga y hay una caída del rendimiento del 20 % frente a la línea base, marcar la discrepancia para revisión. Definir con precisión cómo se calcula la caída, incluida la dirección de la métrica. |
| Verde | 0 a 30 % de desviación. Continuar el cronograma habitual si el equipo responsable confirma que procede. |
| Amarillo | 31 a 60 % o discrepancia entre autorreporte y prueba. Considerar revisar la carga, el descanso, la higiene del sueño y medidas de autorregulación con el equipo. |
| Rojo | Más de 60 %, una caída grave de rendimiento o señales críticas de aislamiento o pánico. Elevar la situación al equipo para valoración confidencial. Cualquier reasignación de tareas corresponde al equipo responsable. |

Antes de implementar un semáforo, verificar los límites, el redondeo entre intervalos, la versión de cada instrumento y la regla de combinación. Si la evidencia no respalda un punto de corte, la propuesta debe señalar qué falta validar.

## Formato de cada propuesta

1. **Metadatos del test.** Nombre, frecuencia, tiempo estimado y fenómenos que evalúa.
2. **Reactivos.** Preguntas numeradas con texto, escala de respuesta, variable medida y fuente.
3. **Prueba objetiva complementaria.** Ejercicio breve de atención o memoria con condiciones de aplicación y métrica para comparar con el autorreporte.
4. **Lógica de cálculo y umbrales.** Fórmula y tabla de interpretación con las fuentes y el estado de validación de cada umbral.

MediSpace incluye el [módulo Diario](modulo-diario.md) y el [módulo Semanal](modulo-semanal.md). Post-Emergencia queda por desarrollar.

La sección **Pruebas cognitivas** del perfil incluye Praxis Motora. Mide en el navegador el tiempo de respuesta a cada uno de los 20 objetivos consecutivos. Las rondas completas se guardan en el historial de la cuenta y en `praxis_motora` dentro del expediente JSON.

Aprendizaje visual de objetos (VOLT) presenta diez figuras tridimensionales durante cinco segundos cada una. Los reconocimientos inmediato y diferido contienen veinte figuras cada uno. Tras el reconocimiento inmediato, el servidor conserva la sesión y habilita el diferido a partir de los quince minutos. El expediente guarda ambas puntuaciones, los tiempos y el intervalo real en `memoria_visual`. Las figuras de MediSpace son propias. [Descripción del reconocimiento diferido en Cognitive Atlas](https://cognitiveatlas.org/task/id/trm_56a2a98785453/)

Orientación de línea (LOT) presenta doce pares de segmentos para cotejar sus inclinaciones con un abanico de once líneas numeradas. MediSpace usa ángulos de 15° a 165° y genera sus propios pares. El expediente guarda los aciertos por par y por línea, los tiempos y las respuestas en `orientacion_linea`. [Formato de referencia del juicio de orientación de Benton](https://pmc.ncbi.nlm.nih.gov/articles/PMC3094715/)

## Chat de apoyo

El chat ofrece apoyo emocional por texto y orienta a la persona hacia el equipo de salud cuando corresponde. Para responder, el proveedor de IA recibe el mensaje y los turnos recientes. MediSpace guarda la conversación en la base de datos de la cuenta, fuera del expediente JSON descargable.
