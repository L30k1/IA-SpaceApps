# IA-SpaceApps

MediSpace es una demostración de chequeos para una tripulación ficticia. Python sirve las cuatro pantallas y SQLite guarda las cuentas y el historial local.

## Abrir con doble clic en Windows

Abre `Abrir MediSpace.pyw` desde el Explorador de archivos. Si te pide la clave de Gemini, pégala en la ventana o deja el campo vacío para usar la demostración. La clave introducida dura lo que dure esa sesión.

MediSpace abre tu navegador y muestra una ventana de control que puedes minimizar. Usa **Detener MediSpace** cuando termines. Si MediSpace ya está abierto desde PowerShell, el acceso abre esa misma instancia. Detén esa instancia con **Ctrl+C** para que el acceso pueda iniciar su propio servidor.

## Ejecutar en PowerShell

```powershell
python -m pip install -r requirements.txt
python main.py
```

Abre [MediSpace](http://127.0.0.1:5000/), crea una cuenta, elige un perfil y entra al chequeo. Usa datos ficticios. Por defecto el chequeo usa preguntas predefinidas. Para usar Gemini, ejecuta `$env:GEMINI_API_KEY = "<tu clave de Gemini>"` en PowerShell antes de iniciar el servidor. Gemini recibe el texto de la conversación y genera dos preguntas de seguimiento. Python guarda las respuestas y la telemetría simulada y muestra el resultado del simulador.

Los formularios y enlaces funcionan en la dirección de MediSpace indicada arriba. Al abrir un HTML directamente o usar un servidor estático como Live Server, verás un enlace para entrar a la aplicación de Python. El estado ESTABLE o ALERTA lo calculan las reglas de demostración en `main.py`. El historial se guarda por cuenta y perfil en `medispace.sqlite3`.

Puedes definir `MEDISPACE_SECRET_KEY` con un valor secreto estable para conservar las sesiones al reiniciar el servidor. Si se omite, se genera una clave nueva en cada inicio.

## Compartir un enlace público con Render

1. Sube los cambios del proyecto a GitHub. Guarda las claves en los ajustes del servicio y conserva la base de datos local fuera del repositorio.
2. En [Render](https://dashboard.render.com/), selecciona **New → Web Service** y conecta el repositorio. Elige **Python**.
3. Usa `pip install -r requirements.txt` como comando de compilación y `gunicorn --bind 0.0.0.0:$PORT 'main:create_app()'` como comando de inicio.
4. En **Environment**, agrega `MEDISPACE_SECRET_KEY` con un valor aleatorio propio. Agrega `GEMINI_API_KEY` con tu clave nueva si quieres habilitar Gemini.
5. Para conservar las cuentas y el historial, usa un plan de pago con un disco montado en `/var/data` y agrega `MEDISPACE_DATABASE=/var/data/medispace.sqlite3`. El plan gratuito sirve para una demostración temporal porque su base de datos local puede perderse al reiniciar o desplegar.
6. Pulsa **Deploy** y comparte la dirección HTTPS que Render genera. Los visitantes pueden crear su propia cuenta y probar el chequeo con datos ficticios.
