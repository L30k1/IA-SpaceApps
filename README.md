# IA-SpaceApps

MediSpace es una demostración de chequeos para una tripulación ficticia. Python sirve las cuatro pantallas y SQLite guarda las cuentas y el historial local.

## Abrir con doble clic en Windows

Abre `Abrir MediSpace.cmd` desde el Explorador de archivos. Si te pide la clave de Gemini, pégala en la ventana para habilitar los chequeos. Con el campo vacío puedes consultar el historial. La clave introducida dura lo que dure esa sesión.

MediSpace abre tu navegador y muestra una ventana de control que puedes minimizar. Usa **Detener MediSpace** cuando termines. Si MediSpace ya está abierto desde PowerShell, el acceso abre esa misma instancia. Detén esa instancia con **Ctrl+C** para que el acceso pueda iniciar su propio servidor.

## Ejecutar en PowerShell

```powershell
python -m pip install -r requirements.txt
python main.py
```

Abre [MediSpace](http://127.0.0.1:5000/) y crea una cuenta con tu expediente JSON. El registro toma el identificador y el nombre del archivo, y asigna el rol de astronauta. Las cuentas antiguas sin expediente pueden adjuntar su JSON desde **Crear cuenta** con su correo y contraseña actuales.

Los campos principales son `_id` y `astronauta.nombre`. Usa la estructura de [expediente-ejemplo.json](database/expediente-ejemplo.json) como referencia y asigna un identificador propio. Las listas de misiones, alergias, antecedentes, medicamentos y chequeos pueden quedar vacías. Los valores de telemetría se introducen en el chequeo. La aplicación usa SQLite para guardar las cuentas, expedientes y chequeos.

Cada chequeo completado se agrega a la lista `chequeos` del expediente JSON de su titular. El servidor reescribe su archivo al iniciar sesión y al terminar un chequeo. Los archivos se guardan en `medispace.sqlite3.expedientes`, junto a la base de datos. Si cambias `MEDISPACE_DATABASE`, la carpeta se crea junto al archivo de SQLite con el sufijo `.expedientes`. En Render, ambos quedan en el mismo disco.

En Chrome o Edge, usa **Elegir JSON y permitir su actualización** al iniciar sesión con JSON o al crear tu cuenta. Autoriza la escritura en el navegador. Al terminar un chequeo, MediSpace incorpora los registros al mismo archivo. Si se pierde el permiso, usa **Actualizar archivo original** en Resultados. En **Historial clínico** también puedes vincular el archivo original o descargar una copia.

Para habilitar los chequeos ficticios, ejecuta `$env:GEMINI_API_KEY = "<tu clave de Gemini>"` en PowerShell antes de iniciar el servidor. Gemini genera las preguntas, analiza las respuestas y la telemetría y guarda su evaluación simulada. Para alertas o resultados indeterminados también propone acciones de seguimiento. Si Gemini falla, puedes reenviar la respuesta sin perder los turnos guardados. Los informes importados y el historial de chequeos previos siguen disponibles.

## Cuenta de demostración

El expediente de ejemplo está reservado para `rivera@example.test`. Para crear esa cuenta en una instalación, ejecuta `python -m flask --app main:create_app crear-usuario-demo` y elige una contraseña al recibir la solicitud. El comando usa la misma base de datos que la aplicación. Para Render, ejecútalo en el entorno del servicio con acceso a su base de datos.

Para habilitar ambos expedientes en Render, agrega estas variables en **Environment**. Escribe una contraseña distinta de 12 a 128 caracteres en el campo **Value** de cada una.

| Archivo | Correo asignado | Variable |
| --- | --- | --- |
| `expediente-ejemplo.json` | `rivera@example.test` | `MEDISPACE_RIVERA_PASSWORD` |
| `expediente-astronauta.json` | `mariana@example.test` | `MEDISPACE_MARIANA_PASSWORD` |

Despliega la versión actualizada. Al arrancar, MediSpace crea las cuentas o actualiza la contraseña si el correo y el identificador corresponden a la cuenta configurada. Si el expediente ya está vinculado a otro correo, conserva su cuenta y contraseña. En **Iniciar sesión con JSON**, sube el archivo correspondiente y escribe la contraseña de esa cuenta.

Los formularios y enlaces funcionan en la dirección de MediSpace indicada arriba. Al abrir un HTML directamente o usar un servidor estático como Live Server, verás un enlace para entrar a la aplicación de Python. El estado ESTABLE o ALERTA lo calculan las reglas de demostración en `main.py`. El historial se guarda por cuenta y perfil en `medispace.sqlite3`.

Puedes definir `MEDISPACE_SECRET_KEY` con un valor secreto estable para conservar las sesiones al reiniciar el servidor. Si se omite, se genera una clave nueva en cada inicio.

## Compartir un enlace público con Render

1. Sube los cambios del proyecto a GitHub. Guarda las claves en los ajustes del servicio y conserva la base de datos local fuera del repositorio.
2. En [Render](https://dashboard.render.com/), selecciona **New → Web Service** y conecta el repositorio. Elige **Python**.
3. Usa `pip install -r requirements.txt` como comando de compilación y `gunicorn --bind 0.0.0.0:$PORT 'main:create_app()'` como comando de inicio.
4. En **Environment**, agrega `MEDISPACE_SECRET_KEY` con un valor aleatorio propio. Agrega `GEMINI_API_KEY` con tu clave nueva si quieres habilitar Gemini.
5. Para conservar las cuentas y el historial, usa un plan de pago con un disco montado en `/var/data` y agrega `MEDISPACE_DATABASE=/var/data/medispace.sqlite3`. El plan gratuito sirve para una demostración temporal porque su base de datos local puede perderse al reiniciar o desplegar.
6. Pulsa **Deploy** y comparte la dirección HTTPS que Render genera. Los visitantes pueden crear una cuenta con su propio expediente JSON.
