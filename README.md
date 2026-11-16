# MediSpace

**[Abrir MediSpace en Render](https://ia-spaceapps.onrender.com/index.html)**

MediSpace es una aplicación web para registrar y consultar el seguimiento de salud de astronautas. Reúne el expediente médico, las evaluaciones de la misión y el historial de resultados de cada cuenta.

## Qué incluye

- **Monitoreo médico.** Registra frecuencia cardíaca, saturación de oxígeno y temperatura. Gemini genera preguntas y recomendaciones de seguimiento a partir de la conversación, las mediciones y los rangos personales del expediente.
- **Atención psicológica.** Incluye formularios diarios y semanales, un chat de apoyo y un chat de emergencia por voz. El chat de emergencia orienta al usuario a contactar al equipo responsable.
- **Pruebas cognitivas.** Incluye Praxis Motora (PM), Aprendizaje visual de objetos (VOLT), Orientación de línea (LOT), Fractal 2-Back (F2B) y Reconocimiento facial (ERT). Los resultados se guardan en el historial.
- **Misiones y ejercicio.** El perfil muestra el calendario de evaluaciones y el mínimo diario de ejercicio según la misión. Las fechas se toman del expediente.
- **Administración.** El panel `/admin` permite a las cuentas autorizadas consultar expedientes y registros o eliminar una cuenta con sus datos de MediSpace.

## Empezar en Render

1. Abre la [versión en línea](https://ia-spaceapps.onrender.com/index.html).
2. En **Crear cuenta**, escribe tu nombre, ID de astronauta y una contraseña de 8 a 128 caracteres. Adjunta un historial médico JSON con el mismo nombre e ID.
3. Si necesitas generar el expediente, selecciona **Crear un historial médico JSON** y completa el formulario. Al descargarlo, MediSpace te lleva de vuelta a **Crear cuenta**.
4. Para volver a entrar, usa el nombre, el ID y la contraseña de la cuenta.

## Uso de IA

La [declaración de uso de SI](docs/uso-de-ia.md) describe cómo se utilizó IA en imágenes, audio, código y datos. El [inventario de procedencia](docs/procedencia-ia.json) reúne los metadatos. Las pruebas cognitivas se desarrollaron con asistencia de IA y se califican mediante reglas programadas.
