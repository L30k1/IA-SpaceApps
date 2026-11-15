# IA-SpaceApps

MediSpace registra chequeos de astronautas y prepara información de seguimiento para su equipo médico. Python sirve la aplicación y SQLite guarda las cuentas y el historial.

## Abrir con doble clic en Windows

Abre `Abrir MediSpace.cmd` desde el Explorador de archivos. Si te pide la clave de IA, pégala en la ventana para habilitar los chequeos. Con el campo vacío puedes consultar el historial. La clave introducida dura lo que dure esa sesión.

MediSpace abre tu navegador y muestra una ventana de control que puedes minimizar. Usa **Detener MediSpace** cuando termines. Si MediSpace ya está abierto desde PowerShell, el acceso abre esa misma instancia. Detén esa instancia con **Ctrl+C** para que el acceso pueda iniciar su propio servidor.

## Ejecutar en PowerShell

```powershell
python -m pip install -r requirements.txt
python main.py
```

Abre [MediSpace](http://127.0.0.1:5000/) y crea una cuenta con tu expediente JSON. El registro toma el identificador y el nombre del archivo, y asigna el rol de astronauta. Las cuentas antiguas sin expediente pueden adjuntar su JSON desde **Crear cuenta** con su correo y contraseña actuales.

Los campos obligatorios del JSON son `_id`, con el identificador único, y `astronauta.nombre`. Las listas `misiones`, `alergias`, `antecedentes`, `medicamentos` y `chequeos` pueden quedar vacías. Las mediciones se pueden introducir en el chequeo cuando estén disponibles.

Cada chequeo completado se agrega a la lista `chequeos` del expediente JSON de su titular. El servidor reescribe su archivo al iniciar sesión y al terminar un chequeo. Los archivos se guardan en `medispace.sqlite3.expedientes`, junto a la base de datos. Si cambias `MEDISPACE_DATABASE`, la carpeta se crea junto al archivo de SQLite con el sufijo `.expedientes`. En Render, ambos quedan en el mismo disco.

En Chrome o Edge, usa **Elegir JSON y permitir su actualización** al iniciar sesión con JSON o al crear tu cuenta. Autoriza la escritura en el navegador. Al terminar un chequeo, MediSpace incorpora los registros al mismo archivo. Si se pierde el permiso, usa **Actualizar archivo original** en Resultados. En **Historial clínico** también puedes vincular el archivo original o descargar una copia.

Para habilitar los chequeos, ejecuta `$env:GEMINI_API_KEY = "<tu clave de IA>"` en PowerShell antes de iniciar el servidor. La IA recibe los mensajes y las mediciones ingresadas. Pulsa **Enviar** para seguir conversando o **Finalizar chequeo** cuando quieras ver el resultado. Las recomendaciones se basan en el cuestionario y las mediciones disponibles, y quedan para revisión del equipo médico. MediSpace guarda la conversación completa y resume los turnos anteriores cuando la conversación es larga. Si la IA falla, puedes reintentar sin perder los turnos guardados.

Al abrir un HTML directamente o usar un servidor estático como Live Server, verás un enlace para entrar a la aplicación de Python. El historial se guarda por cuenta y perfil en `medispace.sqlite3`.

Puedes definir `MEDISPACE_SECRET_KEY` con un valor secreto estable para conservar las sesiones al reiniciar el servidor. Si se omite, se genera una clave nueva en cada inicio.

## Calendario de la misión

En el JSON del astronauta, incluye cada misión en `misiones` con su `id`, `fecha_inicio` y `fecha_fin`. Usa fechas en formato `AAAA-MM-DD` y prepara el expediente antes de crear la cuenta. El perfil muestra el calendario en modo de solo lectura y el inicio de sesión con JSON consulta el expediente ya registrado. Ambos días cuentan para la duración. MediSpace muestra los plazos en UTC−6 y calcula el cumplimiento con las evaluaciones guardadas durante cada período. La evaluación cognitiva requiere una ronda completa de Praxis Motora, VOLT y LOT dentro del mismo período.

| Duración | Médica | Psicológica | Cognitiva |
|---|---|---|---|
| 1 a 7 días | Cada día | Diario | Una vez durante la misión |
| 8 a 30 días | Cada 3 días | Semanal | Cada 14 días |
| 31 días o más | Cada 7 días | Semanal | Cada 30 días |

Si la misión dura menos que un intervalo, la primera evaluación de ese tipo vence al finalizar la misión. Los días restantes al final de una misión no agregan otro plazo cuando no completan un intervalo. Esta periodicidad pertenece al calendario inicial de MediSpace y debe confirmarse con el equipo responsable. [Operaciones médicas y planificación de NASA](https://www.nasa.gov/reference/6-0-medical-operations/)

## Compartir un enlace público con Render

1. Sube los cambios del proyecto a GitHub. Guarda las claves en los ajustes del servicio y conserva la base de datos local fuera del repositorio.
2. En [Render](https://dashboard.render.com/), selecciona **New → Web Service** y conecta el repositorio. Elige **Python**.
3. Usa `pip install -r requirements.txt` como comando de compilación y `gunicorn --bind 0.0.0.0:$PORT 'main:create_app()'` como comando de inicio.
4. En **Environment**, agrega `MEDISPACE_SECRET_KEY` con un valor aleatorio propio. Agrega `GEMINI_API_KEY` con tu clave nueva para habilitar la IA.
5. Para conservar las cuentas y el historial en Render, usa un disco persistente montado en `/var/data` y agrega `MEDISPACE_DATABASE=/var/data/medispace.sqlite3`.
6. Pulsa **Deploy** y comparte la dirección HTTPS que Render genera. Los visitantes pueden crear una cuenta con su propio expediente JSON.

## Voz opcional con ElevenLabs

1. Crea una cuenta **Free** en ElevenLabs para pruebas no comerciales. El plan incluye 10 000 créditos al mes. [Planes de ElevenLabs](https://elevenlabs.io/pricing)
2. En **Developers → API Keys**, crea una clave restringida a **Text to Speech**. Puedes limitar los créditos de la clave. [Configuración de API Keys](https://elevenlabs.io/docs/help-center/technical/how-do-i-authorize-myself-using-an-api-key)
3. En **Voices → My Voices**, elige una voz propia y copia su ID desde los tres puntos. Si no tienes voz, puedes crear una en **Add a new voice → Voice Design** con una descripción de la voz en español. La API del plan gratuito excluye las voces de la biblioteca comunitaria. [Diseño de voz](https://elevenlabs.io/docs/eleven-creative/voices/voice-design/) · [Cómo copiar el ID](https://elevenlabs.io/docs/es/help-center/technical/how-do-i-find-the-voice-id-of-my-voices-via-the-website-and-api)
4. En **Render → tu servicio → Environment**, agrega `ELEVENLABS_API_KEY` con la clave y `ELEVENLABS_VOICE_ID` con el ID de voz. Guarda y despliega el código actualizado. [Variables en Render](https://render.com/docs/configure-environment-variables)
5. Abre un chequeo o el chat de apoyo, genera una respuesta de prueba y pulsa **Escuchar con ElevenLabs**. Puedes reproducir el mismo audio de nuevo desde el reproductor. El dictado y la voz del navegador siguen disponibles.

Para probar en PowerShell, define las variables en la terminal desde la que arrancas el servidor.

```powershell
$env:ELEVENLABS_API_KEY = '<tu clave>'
$env:ELEVENLABS_VOICE_ID = '<tu ID de voz>'
python main.py
```

Usa datos ficticios para las pruebas. Al generar audio, ElevenLabs recibe el texto de la última respuesta y su API aplica retención por defecto. El botón es opcional y se activa solo cuando el servidor tiene ambas variables. [Retención de datos de ElevenLabs](https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode)
