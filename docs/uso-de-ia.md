# Declaración de uso de sistemas de IA (SI)

MediSpace utilizó ChatGPT y OpenAI Codex durante el desarrollo para proponer, generar y revisar fragmentos del backend de Python, las plantillas HTML, los estilos CSS, la lógica de JavaScript y la documentación. Esta declaración describe la asistencia al proyecto. No se registró qué herramienta intervino en cada línea de código. El [inventario de procedencia](procedencia-ia.json) contiene los metadatos en formato JSON.

| Material | Dónde se usó el SI | Cómo se identifica |
|---|---|---|
| Imágenes de rostros | Las láminas `static/emociones/rostros-a.png` y `rostros-b.png` son los estímulos del ejercicio de reconocimiento facial (ERT). El nombre del generador específico no quedó documentado. | Cada rostro lleva la marca visible «Imagen generada por IA» al mostrarse durante la prueba, en una franja debajo del estímulo. Las láminas fuente se conservan como insumos. |
| Logotipos | El emblema y el logotipo de `static/marca/` fueron creados con ChatGPT y aportados por el equipo. | La marca visible «Imágenes generadas por IA · ChatGPT» aparece debajo de ambas imágenes en el encabezado y en el acceso. Los JPEG fuente se conservan como insumos. |
| Video | El repositorio no incluye videos generados por SI. | Para cualquier video generado que se agregue a la entrega, incluir una marca visible en el propio video. |
| Audio | ElevenLabs convierte en voz los mensajes del monitoreo médico, el chat de apoyo y el chat de emergencia cuando se activa. La alternativa reproduce el texto mediante síntesis de voz del navegador, sin crear un MP3 descargable en MediSpace. | Los controles de voz identifican la síntesis. El audio de ElevenLabs contiene una etiqueta ID3v1.1 con el título «Audio generado por IA» y el comentario «Generado por IA - ElevenLabs». [Formato de metadatos ID3](https://id3.org/ID3v1) |
| Datos de ejemplo | `database/expediente-astronauta-completo.json` contiene un expediente ficticio preparado con asistencia de IA para probar el formato de importación. | El propio JSON declara `tipo_datos` y `procedencia`. |
| Datos generados en ejecución | Google Gemini redacta preguntas y evaluaciones de monitoreo, orientaciones de seguimiento psicológico y respuestas de los chats de apoyo y emergencia. | Las nuevas salidas guardadas incluyen `procedencia` con el proveedor y el modelo. En los chats, los mensajes siguen identificados como IA. |

Las mediciones y las respuestas que la persona ingresa conservan su procedencia. Las puntuaciones de los cuestionarios y las pruebas cognitivas se calculan con la lógica de la aplicación.
