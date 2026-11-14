import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx2
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from google.genai.errors import APIError
from werkzeug.security import check_password_hash, generate_password_hash

import db
from asistente import generar_pregunta


ROOT = Path(__file__).resolve().parent
PROFILES = {
    "AS-2743": {"name": "A. Rivera", "role": "Astronauta"},
    "SC-1092": {"name": "Dra. E. Vance", "role": "Investigadora"},
    "EN-4410": {"name": "Ing. M. Sato", "role": "Ingeniero"},
}
MEDICAL_TABS = {
    "historial": ("Historial médico", [
        "Sin condiciones crónicas registradas",
        "Última revisión integral: 01/09/2026",
        "Vacunación orbital completa al día",
        "Densidad ósea estable (-0.4% variación)",
    ]),
    "parametros": ("Parámetros fisiológicos de ejemplo", [
        "Presión arterial media: 118/76 mmHg",
        "Frecuencia respiratoria: 14 rpm",
        "Horas de sueño promedio: 7.2 h por ciclo",
        "Hidratación programada: 2.5 L",
    ]),
    "alergias": ("Alergias y contraindicaciones", [
        "Alergias medicamentosas: ninguna conocida",
        "Alergias alimentarias: ninguna",
        "Sensibilidad ambiental leve a polvo lunar simulado",
    ]),
}
DEMO_QUESTIONS = (
    "¿Has notado algún malestar físico o algún cambio en tu estado de ánimo?",
    "¿Qué actividades hiciste hoy y cómo te sentiste al realizarlas?",
)


def create_app(database=None):
    app = Flask(
        __name__,
        template_folder=str(ROOT),
        static_folder=str(ROOT / "css"),
        static_url_path="/css",
    )
    app.config.update(
        SECRET_KEY=os.getenv("MEDISPACE_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=16 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    database = database or os.getenv("MEDISPACE_DATABASE") or ROOT / "medispace.sqlite3"
    db.initialize(database)

    @app.context_processor
    def page_context():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return {
            "utc_clock": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "csrf": session["csrf"],
        }

    @app.before_request
    def validate_form():
        if request.method == "POST":
            expected = session.get("csrf", "")
            token = request.form.get("csrf", "")
            if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
                flash("El formulario caducó. Vuelve a completar el paso.")
                if request.endpoint == "checkup" and selected_profile():
                    return redirect(url_for("checkup"), 303)
                mode = request.args.get("mode")
                return redirect(url_for("index", mode="register" if mode == "register" else None), 303)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/index.html", methods=["GET", "POST"])
    def index():
        mode = request.args.get("mode", "login")
        if mode not in {"login", "register"}:
            abort(404)
        if "user_id" in session:
            if request.method == "POST":
                profile = request.form.get("profile")
                if profile not in PROFILES:
                    flash("Elige un perfil para continuar.")
                    return redirect(url_for("index"), 303)
                session["profile"] = profile
                return redirect(url_for("profile"), 303)
            return render_template("index.html", selecting=True)

        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        error = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
                error = "Escribe un correo electrónico válido."
            elif mode == "register":
                if not 1 <= len(name) <= 80 or not 8 <= len(password) <= 128:
                    error = "Escribe un nombre y una contraseña de 8 a 128 caracteres."
                else:
                    try:
                        user_id = db.create_user(database, email, name, generate_password_hash(password))
                    except sqlite3.IntegrityError:
                        error = "Ya existe una cuenta con ese correo."
            else:
                user = db.find_user(database, email)
                if not user or len(password) > 128 or not check_password_hash(user["password_hash"], password):
                    error = "El correo o la contraseña son incorrectos."
                else:
                    user_id, name = user["id"], user["name"]
            if not error:
                session.clear()
                session.update(user_id=user_id, name=name)
                return redirect(url_for("index"), 303)
        return render_template("index.html", mode=mode, email=email, name=name, error=error)

    @app.post("/salir")
    def logout():
        session.clear()
        return redirect(url_for("index"), 303)

    def selected_profile():
        profile_id = session.get("profile")
        if "user_id" not in session or profile_id not in PROFILES:
            return None
        return {**PROFILES[profile_id], "id": profile_id, "name": session["name"]}

    @app.get("/perfil.htm")
    def profile():
        crew = selected_profile()
        if crew is None:
            return redirect(url_for("index"))
        tab = request.args.get("tab")
        if tab is not None and tab not in MEDICAL_TABS:
            return redirect(url_for("profile"))
        records = db.history(database, session["user_id"], crew["id"])
        return render_template(
            "perfil.htm", crew=crew, tab=tab, medical=MEDICAL_TABS.get(tab),
            latest=records[0] if records else None,
        )

    @app.route("/chequeo.html", methods=["GET", "POST"])
    def checkup():
        crew = selected_profile()
        if crew is None:
            return redirect(url_for("index"))
        greeting = {"role": "ai", "text": f"¿Cómo te sientes hoy, {crew['name']}?"}
        draft = db.open_checkup(database, session["user_id"], crew["id"], greeting)
        messages = json.loads(draft["messages"])
        vitals = {key: draft[key] for key in ("hr", "spo2", "temp")}
        answer = request.form.get("quick_reply") or request.form.get("answer", "").strip()
        use_gemini = bool(os.getenv("GEMINI_API_KEY"))
        error = None
        if request.method == "POST":
            if request.form.get("turn") != f"{draft['id']}:{draft['revision']}":
                return redirect(url_for("checkup"), 303)
            vitals = {key: request.form.get(key, "") for key in vitals}
            try:
                hr, spo2, temp = int(vitals["hr"]), int(vitals["spo2"]), float(vitals["temp"])
                if not (40 <= hr <= 180 and 80 <= spo2 <= 100 and 30 <= temp <= 45):
                    raise ValueError
            except ValueError:
                error = "Revisa los tres valores de telemetría simulada."
            if not error and not 1 <= len(answer) <= 1000:
                error = "Escribe una respuesta de hasta 1000 caracteres."
            if not error:
                updated = [*messages, {"role": "user", "text": answer}]
                status = None
                if draft["revision"] < 2:
                    question = DEMO_QUESTIONS[draft["revision"]]
                    if use_gemini:
                        conversation = "\n".join(
                            f"{'Tripulante' if turn['role'] == 'user' else 'Asistente'}: {turn['text']}"
                            for turn in updated[1:]
                        )
                        try:
                            question = generar_pregunta(conversation)
                        except (APIError, httpx2.HTTPError):
                            error = "Gemini no respondió. Puedes volver a enviar tu respuesta."
                    if not error:
                        updated.append({"role": "ai", "text": question})
                else:
                    # Reglas del simulador de la interfaz original.
                    responses = " ".join(turn["text"].lower() for turn in updated if turn["role"] == "user")
                    symptoms = re.search(r"\b(dolor|ansiedad|mareo|malestar|estrés|fatiga|mal)\b", responses)
                    status = "ALERTA" if symptoms or not 50 <= hr <= 95 or spo2 < 95 else "ESTABLE"
                if not error:
                    saved = db.save_turn(database, draft, updated, (hr, spo2, temp), status)
                    return redirect(url_for("summary" if saved and status else "checkup"), 303)
        return render_template(
            "chequeo.html", messages=messages, vitals=vitals, draft=draft, answer=answer, error=error,
            use_gemini=use_gemini,
        )

    @app.get("/resumen.html")
    def summary():
        crew = selected_profile()
        if crew is None:
            return redirect(url_for("index"))
        view = request.args.get("vista", "resultados")
        if view not in {"resultados", "alertas", "historial"}:
            return redirect(url_for("summary"))
        records = db.history(database, session["user_id"], crew["id"])
        latest = records[0] if records else None
        messages = json.loads(latest["messages"]) if latest else []
        return render_template("resumen.html", view=view, latest=latest, records=records, messages=messages)

    return app


if __name__ == "__main__":
    create_app().run()
