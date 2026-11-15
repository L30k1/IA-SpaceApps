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

Abre [MediSpace](http://127.0.0.1:5000/). En **Crear cuenta**, escribe el nombre, el ID del astronauta y una contraseña de 8 a 128 caracteres. Adjunta el historial médico en formato JSON. El nombre y el ID deben coincidir con los del archivo. Para iniciar sesión escribe esos tres datos.

Si todavía no tienes un JSON, en **Crear cuenta → Crear un historial médico JSON** puedes llenar el formulario y descargar el archivo. Los campos obligatorios del JSON son `_id`, el identificador único, y `astronauta.nombre`. Las listas `misiones`, `alergias`, `antecedentes`, `medicamentos` y `chequeos` pueden quedar vacías si todavía no hay registros.

Cada chequeo completado aparece en la lista `chequeos` del expediente exportado. Con SQLite, el servidor también reescribe una copia al iniciar sesión y al terminar un chequeo. La copia queda en `medispace.sqlite3.expedientes`, junto a la base de datos. Si cambias `MEDISPACE_DATABASE`, la carpeta se crea junto al archivo de SQLite con el sufijo `.expedientes`.

En un navegador compatible, usa **Elegir historial JSON y permitir su actualización** al crear la cuenta y autoriza la escritura si deseas actualizar ese mismo archivo. En **Historial clínico** también puedes vincular el archivo original o descargar una copia.

Para habilitar los chequeos, ejecuta `$env:GEMINI_API_KEY = "<tu clave de IA>"` en PowerShell antes de iniciar el servidor. La IA recibe los mensajes y las mediciones ingresadas. Pulsa **Enviar** para seguir conversando o **Finalizar chequeo** cuando quieras ver el resultado. Las recomendaciones se basan en el cuestionario y las mediciones disponibles, y quedan para revisión del equipo médico. MediSpace guarda la conversación completa y resume los turnos anteriores cuando la conversación es larga. Si la IA falla, puedes reintentar sin perder los turnos guardados.

Al abrir un HTML directamente o usar un servidor estático como Live Server, verás un enlace para entrar a la aplicación de Python. El historial se guarda por cuenta en la base de datos configurada.

Puedes definir `MEDISPACE_SECRET_KEY` con un valor secreto estable para conservar las sesiones al reiniciar el servidor. Si se omite, se genera una clave nueva en cada inicio.

## Calendario de la misión

En el JSON del astronauta, incluye cada misión en `misiones` con su `id`, `fecha_inicio` y `fecha_fin`. Usa fechas en formato `AAAA-MM-DD` y prepara el expediente antes de crear la cuenta. El perfil muestra el calendario en modo de solo lectura. Ambos días cuentan para la duración. MediSpace muestra los plazos en UTC−6 y calcula el cumplimiento con las evaluaciones guardadas durante cada período. La evaluación cognitiva requiere una ronda completa de Praxis Motora, VOLT y LOT dentro del mismo período.

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
5. Configura MongoDB Atlas para que las cuentas y el historial se guarden fuera de Render. Si prefieres conservar SQLite, monta un disco persistente en `/var/data` y agrega `MEDISPACE_DATABASE=/var/data/medispace.sqlite3`.
6. Pulsa **Deploy** y comparte la dirección HTTPS que Render genera. Los visitantes pueden crear una cuenta con su propio expediente JSON.

## Empezar con MongoDB Atlas

1. Crea un clúster Free (M0) y un usuario de base de datos con permiso de lectura y escritura en `medispace`. [Crear el clúster](https://www.mongodb.com/docs/atlas/tutorial/deploy-free-tier-cluster/)
2. Copia los rangos de salida de tu servicio en **Render → Connect → Outbound** y agrégalos a **Network Access** en Atlas. [Direcciones de salida de Render](https://render.com/docs/outbound-ip-addresses)
3. En **Atlas → Connect → Drivers → Python**, copia la URI completa con las credenciales del usuario de base de datos. Guárdala como `MONGODB_URI` en **Render → Environment**. MediSpace utiliza la base `medispace`. Si eliges otro nombre, agrega `MONGODB_DB` y concede permisos sobre esa base. Conserva `MEDISPACE_SECRET_KEY` en la configuración de Render. [Conexión con PyMongo](https://www.mongodb.com/docs/atlas/driver-connection/) · [Variables de Render](https://render.com/docs/configure-environment-variables)
4. Despliega. MediSpace comprueba la conexión y crea sus índices al arrancar. Con `MONGODB_URI`, las cuentas, expedientes, monitoreos y chats se guardan en Atlas. Sin esa variable, el servidor usa SQLite.
5. Genera un expediente con datos ficticios desde **Crear cuenta → Crear un historial médico JSON**. En **Crear cuenta**, escribe el nombre y el ID del archivo, elige una contraseña y adjunta el JSON. Guarda un monitoreo y una prueba cognitiva. Reinicia el servicio e inicia sesión con los tres campos para verificar que sigan en el historial. En Atlas, las cuentas se guardan en `usuarios` y los monitoreos en `monitoreos`, vinculados por el ID interno de la cuenta.

La base Atlas empieza vacía. Los JSON siguen sirviendo para importar y exportar expedientes. Con Atlas, la exportación se genera cuando la solicitas y la app guarda el expediente en MongoDB.

Si falla el arranque, revisa **Render → Logs**. El código `MONGO_RED` apunta a conectividad o al estado del clúster, `MONGO_AUTENTICACION` a las credenciales y `MONGO_PERMISOS` al acceso del usuario a la base. Los mensajes de arranque omiten la URI y las credenciales. [Conectar Render a Atlas](https://render.com/docs/connect-to-mongodb-atlas)

## Voz en los chats

En el monitoreo médico y el chat de apoyo, mantén presionada la barra espaciadora fuera de un campo editable o mantén pulsado **Mantén pulsado para hablar**. Autoriza el micrófono cuando el navegador lo solicite. Suelta para dejar de escuchar y revisa el texto antes de pulsar **Enviar**.

El navegador lee en voz alta la respuesta nueva. Si bloquea la lectura automática, pulsa **Escuchar última respuesta**. El dictado requiere un navegador compatible y HTTPS o localhost. El navegador puede utilizar su propio servicio de transcripción. [API de voz del navegador](https://wicg.github.io/speech-api/)
