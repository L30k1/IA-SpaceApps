import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx2
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from google.genai.errors import APIError
from werkzeug.security import check_password_hash, generate_password_hash

import db
from asistente import evaluar_chequeo, generar_pregunta
from database.expedientes import DEMO_ID, FASES, SIGNOS, fecha_utc, leer_expediente


ROOT = Path(__file__).resolve().parent
MODOS_ACCESO = {"login", "login-json", "register"}
ACCESOS_JSON = (
    ("expediente-ejemplo.json", "rivera@example.test", DEMO_ID, "MEDISPACE_RIVERA_PASSWORD"),
    ("expediente-astronauta.json", "mariana@example.test", "AS-MVEGA-8C42", "MEDISPACE_MARIANA_PASSWORD"),
)
ERRORES_GEMINI = (APIError, httpx2.HTTPError, ValueError)
MENSAJE_GEMINI = "Gemini no devolvió una respuesta válida. Vuelve a intentarlo."


def leer_expediente_subido(*, permitir_demo=False):
    archivo = request.files.get("expediente")
    if not archivo or not archivo.filename.lower().endswith(".json"):
        raise ValueError("Selecciona tu expediente en formato JSON.")
    return leer_expediente(archivo.read(), permitir_demo=permitir_demo)


def configurar_acceso_json(database, archivo, correo, astronauta_id, password, *, actualizar=False):
    if not 12 <= len(password) <= 128:
        raise ValueError("La contraseña debe tener entre 12 y 128 caracteres.")
    expediente = leer_expediente((ROOT / "database" / archivo).read_bytes(), permitir_demo=True)
    if expediente["_id"] != astronauta_id:
        raise ValueError("El expediente no coincide con el identificador de la cuenta.")

    if not db.find_user(database, correo):
        try:
            db.create_user(database, correo, expediente["astronauta"]["nombre"],
                           generate_password_hash(password), expediente)
            return
        except sqlite3.IntegrityError as exc:
            if not actualizar:
                raise ValueError("La cuenta o el expediente ya existe.") from exc
    if not actualizar:
        raise ValueError("La cuenta ya existe.")

    usuario = db.find_user(database, correo)
    titular = db.find_user_by_astronauta(database, astronauta_id)
    if not usuario or not titular or usuario["id"] != titular["id"]:
        raise ValueError("El correo o el expediente está vinculado a otra cuenta.")
    if not check_password_hash(usuario["password_hash"], password):
        db.update_password(database, usuario["id"], generate_password_hash(password))


def registros_clinicos(database, user_id, expediente):
    registros = [
        {**registro, "clave": f"json-{registro['id']}", "estado": registro.get("resultado_simulador"),
         "evaluacion_ia": None}
        for registro in expediente["chequeos"]
    ]
    for row in db.history(database, user_id, expediente["_id"]):
        details = json.loads(row["details"] or "{}")
        messages = json.loads(row["messages"])
        registros.append({
            **details,
            "clave": f"app-{row['id']}",
            "fecha_hora": row["finished_at"],
            "estado": row["status"],
            "mediciones": [
                {"tipo": tipo, "valor": row[columna], "unidad": SIGNOS[tipo][1]}
                for tipo, columna in zip(SIGNOS, ("hr", "spo2", "temp"))
            ],
            "conversacion": messages,
        })
    return sorted(registros, key=lambda r: fecha_utc(r["fecha_hora"]), reverse=True)


def create_app(database=None):
    app = Flask(
        __name__,
        template_folder=str(ROOT),
        static_folder=str(ROOT / "css"),
        static_url_path="/css",
    )
    app.config.update(
        SECRET_KEY=os.getenv("MEDISPACE_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=256 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    database = database or os.getenv("MEDISPACE_DATABASE") or ROOT / "medispace.sqlite3"
    db.initialize(database)
    for archivo, correo, astronauta_id, variable in ACCESOS_JSON:
        password = os.getenv(variable)
        if password:
            try:
                configurar_acceso_json(database, archivo, correo, astronauta_id, password, actualizar=True)
            except (OSError, ValueError) as exc:
                app.logger.error("No se pudo configurar %s: %s", variable, exc)

    @app.cli.command("crear-usuario-demo")
    @click.password_option(confirmation_prompt=True)
    def crear_usuario_demo(password):
        """Crea una cuenta para el expediente de ejemplo."""
        archivo, correo, astronauta_id, _ = ACCESOS_JSON[0]
        try:
            configurar_acceso_json(database, archivo, correo, astronauta_id, password)
        except (OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Cuenta creada: {correo}")

    @app.template_filter("hora_utc")
    def hora_utc(fecha):
        return fecha_utc(fecha).strftime("%d/%m/%Y %H:%M UTC")

    def expediente_actual():
        return db.expediente_for_user(database, session.get("user_id"))

    @app.after_request
    def proteger_paginas(response):
        if request.endpoint in {"index", "profile", "checkup", "summary", "logout"}:
            response.cache_control.no_store = True
        return response

    @app.context_processor
    def page_context():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return {
            "utc_clock": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "csrf": session["csrf"],
            "fases": FASES,
            "signos": SIGNOS,
        }

    @app.before_request
    def validate_form():
        if request.method == "POST":
            expected = session.get("csrf", "")
            token = request.form.get("csrf", "")
            if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
                flash("El formulario caducó. Vuelve a completar el paso.")
                if request.endpoint == "checkup" and expediente_actual():
                    return redirect(url_for("checkup"), 303)
                mode = request.args.get("mode")
                return redirect(url_for("index", mode=mode if mode in MODOS_ACCESO else None), 303)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/index.html", methods=["GET", "POST"])
    def index():
        mode = request.args.get("mode", "login")
        if mode not in MODOS_ACCESO:
            abort(404)
        if expediente_actual():
            return redirect(url_for("profile"), 303)

        email = request.form.get("email", "").strip().lower()
        error = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if mode == "login-json":
                try:
                    expediente = leer_expediente_subido(permitir_demo=True)
                except ValueError as exc:
                    error = str(exc)
                else:
                    user = db.find_user_by_astronauta(database, expediente["_id"])
                    if user and len(password) <= 128 and check_password_hash(user["password_hash"], password):
                        user_id = user["id"]
                    else:
                        error = "El expediente o la contraseña son incorrectos."
            elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
                error = "Escribe un correo electrónico válido."
            else:
                user = db.find_user(database, email)
                valid_password = bool(user and len(password) <= 128 and check_password_hash(user["password_hash"], password))
                if mode == "register":
                    try:
                        if not 8 <= len(password) <= 128:
                            raise ValueError("Escribe una contraseña de 8 a 128 caracteres.")
                        if user and (not valid_password or db.expediente_for_user(database, user["id"])):
                            raise ValueError("No se puede registrar esa cuenta.")
                        expediente = leer_expediente_subido()
                        user_id = db.create_user(
                            database, email, expediente["astronauta"]["nombre"], generate_password_hash(password),
                            expediente, existing_user=user["id"] if user else None,
                        )
                    except ValueError as exc:
                        error = str(exc)
                    except sqlite3.IntegrityError:
                        error = "La cuenta o el identificador del astronauta ya está registrado."
                elif not valid_password:
                    error = "El correo o la contraseña son incorrectos."
                elif not db.expediente_for_user(database, user["id"]):
                    flash("Agrega tu expediente JSON con el mismo correo y contraseña para habilitar tu cuenta.")
                    return redirect(url_for("index", mode="register"), 303)
                else:
                    user_id = user["id"]

            if not error:
                session.clear()
                session["user_id"] = user_id
                return redirect(url_for("profile"), 303)
        return render_template("index.html", mode=mode, email=email, error=error)

    @app.post("/salir")
    def logout():
        session.clear()
        return redirect(url_for("index"), 303)

    @app.get("/perfil.htm")
    def profile():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        records = registros_clinicos(database, session["user_id"], expediente)
        return render_template("perfil.htm", expediente=expediente, latest=records[0] if records else None)

    @app.route("/chequeo.html", methods=["GET", "POST"])
    def checkup():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        if not expediente.get("simulado"):
            return render_template("chequeo.html", expediente=expediente, bloqueado="El chequeo con Gemini está disponible para expedientes ficticios.")
        if not os.getenv("GEMINI_API_KEY", "").strip():
            return render_template("chequeo.html", expediente=expediente, bloqueado="Gemini aún no está configurado en el servidor.")

        usuario, astronauta = session["user_id"], expediente["_id"]
        draft = db.get_open_checkup(database, usuario, astronauta)
        if request.method == "POST" and request.form.get("iniciar") == "1":
            if draft is None:
                try:
                    pregunta = generar_pregunta([])
                except ERRORES_GEMINI:
                    return render_template("chequeo.html", expediente=expediente, error=MENSAJE_GEMINI), 503
                db.open_checkup(database, usuario, astronauta, {"role": "ai", "text": pregunta})
            return redirect(url_for("checkup"), 303)
        if draft is None:
            return render_template("chequeo.html", expediente=expediente)

        messages = json.loads(draft["messages"])
        vitals = {key: draft[key] if draft["revision"] else "" for key in ("hr", "spo2", "temp")}
        details = json.loads(draft["details"] or "{}")
        misiones = {mision["id"] for mision in expediente["misiones"]}
        answer = request.form.get("answer", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("turn") != f"{draft['id']}:{draft['revision']}":
                return redirect(url_for("checkup"), 303)
            vitals = {key: request.form.get(key, "") for key in vitals}
            details = {campo: request.form.get(campo, "").strip() for campo in ("mision_id", "fase", "motivo", "actividad")}
            try:
                hr, spo2, temp = int(vitals["hr"]), int(vitals["spo2"]), float(vitals["temp"])
                if not (1 <= hr <= 999 and 0 <= spo2 <= 100 and 0.1 <= temp <= 99.9):
                    raise ValueError
            except ValueError:
                error = "Ingresa los tres valores de telemetría y revisa sus unidades."
            if ((details["mision_id"] and details["mision_id"] not in misiones)
                    or (details["fase"] and details["fase"] not in FASES)):
                error = "Selecciona una misión y una fase del expediente."
            if any(len(details[campo]) > 200 for campo in ("motivo", "actividad")):
                error = "El motivo y la actividad admiten hasta 200 caracteres."
            if not error and not 1 <= len(answer) <= 1000:
                error = "Escribe una respuesta de hasta 1000 caracteres."
            if not error:
                updated = [*messages, {"role": "user", "text": answer}]
                status = None
                contexto = {
                    "telemetria": {"frecuencia_cardiaca_lpm": hr, "spo2_pct": spo2, "temperatura_c": temp},
                    "fase": details["fase"], "actividad": details["actividad"], "motivo": details["motivo"],
                }
                try:
                    if draft["revision"] < 2:
                        pregunta = generar_pregunta(updated, contexto)
                        updated.append({"role": "ai", "text": pregunta})
                    else:
                        evaluacion = evaluar_chequeo(updated, contexto)
                        status = evaluacion["estado"]
                        details["evaluacion_ia"] = evaluacion
                except ERRORES_GEMINI:
                    error = MENSAJE_GEMINI
                if not error:
                    saved = db.save_turn(database, draft, updated, (hr, spo2, temp), details, status)
                    if saved and status:
                        return redirect(url_for("summary", registro=f"app-{draft['id']}"), 303)
                    return redirect(url_for("checkup"), 303)
        return render_template(
            "chequeo.html", messages=messages, vitals=vitals, draft=draft, answer=answer, error=error,
            expediente=expediente, details=details,
        )

    @app.get("/resumen.html")
    def summary():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        view = request.args.get("vista", "resultados")
        if view not in {"resultados", "alertas", "historial"}:
            return redirect(url_for("summary"))
        records = registros_clinicos(database, session["user_id"], expediente)
        clave = request.args.get("registro")
        latest = next((registro for registro in records if registro["clave"] == clave), None) if clave else (records[0] if records else None)
        if clave and latest is None:
            abort(404)
        return render_template(
            "resumen.html", view=view, latest=latest, records=records, expediente=expediente,
        )

    return app


if __name__ == "__main__":
    create_app().run()
