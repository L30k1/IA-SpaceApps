import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from math import ceil, isfinite
from operator import itemgetter
from pathlib import Path
from statistics import mean
from sys import float_info
from tempfile import NamedTemporaryFile
from unicodedata import normalize
from urllib.parse import urlencode
from uuid import uuid4

import httpx2
from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from google.genai.errors import APIError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import db
from medical_history_form import FORM_SECTIONS, adjust_form_rows, form_rows, build_medical_record
from language import short_date, current_language, requested_language, translate as t
from assistant_ai import assess_checkup, generate_question, prepare_conversation, reply_text, ai_turn
from mission_calendar import MISSION_TIMEZONE, build_mission_schedule, mission_dates, summarize_exercise, mission_exercise_routine
from database.medical_records import (
    PRAXIS_FIELD, PHASES, INPUT_LIMITS, PRAXIS_TARGETS, VITAL_SIGNS, utc_datetime, read_medical_record, lot_entry,
    exercise_entry, emotion_test_entry, f2b_entry, praxis_entry,
)
from exercise import EXERCISE_FIELD, HEART_RATE_CONTEXTS, EXERCISE_HEART_RATE_CONTEXTS, EXERCISE_TYPES
from edit_medical_record import (
    EDITABLE_GROUPS, EDIT_SECTIONS, StaleEditError, apply_record_edit, mission_rows, edit_form,
    edit_version,
)
from emotion_recognition import ERT_FIELD, EMOTIONS, ERT_EXPOSURE_MS, INTENSITIES, IMAGE_SHEETS, make_emotion_stimuli
from emergency import reply_to_emergency_chat
from f2b import F2B_FIELD, F2B_MATCHES, F2B_EXPOSURE_MS, F2B_STIMULUS_COUNT, f2b_sequence
from lot import LOT_ANGLES, LOT_FIELD, LOT_TRIAL_COUNT, LOT_OPTIONS, lot_pairs
from record_edit_key import EDIT_KEY_FIELD, extract_edit_key, create_edit_key, verify_credential
from psychological_support import (
    INTERVALS, MODULES, VERSION, read_pvt, read_answers, score, reply_to_support_chat, generate_psychological_followup,
    mission_quarter, validate_check_ins,
)
from volt import VOLT_FIELD, DELAY, EXPOSURE_SECONDS, SHAPE_COUNT, make_stimuli
from ai_voice import ElevenLabsError, ELEVENLABS_MESSAGES, elevenlabs_settings, synthesize_elevenlabs


ROOT = Path(__file__).resolve().parent
ACCESS_MODES = {"login", "register"}
JSON_TEST_ENDPOINTS = {"pruebas_cognitivas", "prueba_volt", "prueba_lot", "prueba_f2b", "prueba_emociones"}
RESULT_LABELS = {
    "ALERTA": "Priority review suggested",
    "ESTABLE": "No additional priority suggested",
    "INDETERMINADO": "More information needed",
}
GEMINI_ERRORS = (APIError, httpx2.HTTPError, ValueError)
GEMINI_ERROR_MESSAGE = "The AI did not return a valid reply. Try again."
MONITORING_MEASUREMENTS = {
    "hr": ("frecuencia_cardiaca", "frecuencia_cardiaca_lpm", int),
    "spo2": ("spo2", "spo2_pct", int),
    "temp": ("temperatura", "temperatura_c", float),
}
ADMIN_SECTIONS = {
    "expediente": "Medical record",
    "monitoreos": "Monitoreos",
    "psicologia": "Psychological forms",
    "cognicion": "Cognitive tests",
    "ejercicio": "Exercise",
    "chats": "Conversations",
}
ADMIN_GROUPS = {
    "psicologia": (("diario_psicologico", "Daily"), ("semanal_psicologico", "Weekly")),
    "cognicion": (
        (PRAXIS_FIELD, "Motor Praxis (MP)"), (VOLT_FIELD, "Visual Object Learning Test (VOLT)"),
        (LOT_FIELD, "Orientación de línea (LOT)"), (F2B_FIELD, "Fractal 2-Back (F2B)"),
        (ERT_FIELD, "Facial emotion recognition"),
    ),
    "ejercicio": ((EXERCISE_FIELD, "Exercise sessions"),),
}


def compare_reference_ranges(measured_values, reference_ranges):
    comparison = {}
    for lookup_key, (kind, _, _) in MONITORING_MEASUREMENTS.items():
        value, reference_range = measured_values.get(lookup_key), reference_ranges.get(kind)
        if value is None or not reference_range:
            continue
        lower_bound, upper_bound = reference_range["minimo"], reference_range["maximo"]
        position = "inferior" if value < lower_bound else "superior" if value > upper_bound else "dentro"
        comparison[kind] = {**reference_range, "valor": value, "unidad": VITAL_SIGNS[kind][1], "posicion": position}
    return comparison


def read_uploaded_record():
    uploaded_file = request.files.get("expediente")
    if not uploaded_file or not uploaded_file.filename.lower().endswith(".json"):
        raise ValueError("Select your medical record as a JSON file.")
    medical_record = read_medical_record(uploaded_file.read())
    for module in MODULES:
        validate_check_ins(medical_record, module)
    return medical_record


def normalized_name(full_name):
    return normalize("NFC", " ".join(full_name.split())).casefold()


def merge_checkup_history(medical_record, rows):
    checkup_entries = {entry["id"]: entry for entry in medical_record["chequeos"]}
    entries = []
    for row in rows:
        details = json.loads(row["details"] or "{}")
        record_id = details.get("expediente_chequeo_id")
        entry = checkup_entries.pop(record_id, None)
        if entry is None:
            record_id = record_id or f"chequeo-anterior-{row['id']}"
            while record_id in checkup_entries:
                record_id += "-local"
            entry = db.checkup_record(
                record_id, row["finished_at"], json.loads(row["messages"]),
                (row["hr"], row["spo2"], row["temp"]), details, row["status"],
            )
        entries.append((f"app-{row['id']}", entry))
    entries.extend((f"json-{record_id}", entry) for record_id, entry in checkup_entries.items())
    return sorted(entries, key=lambda item: utc_datetime(item[1]["fecha_hora"]), reverse=True)


def clinical_records(database, user_id, medical_record, storage=db):
    return [
        {**entry, "clave": lookup_key, "estado": entry.get("resultado") or entry.get("resultado_simulador"),
         "evaluacion_ia": entry.get("evaluacion_ia") if lookup_key.startswith("app-") else None}
        for lookup_key, entry in merge_checkup_history(medical_record, storage.history(database, user_id, medical_record["_id"]))
    ]


def statistics_series(label, unit, readings):
    if not readings:
        return None
    # History is ordered from newest to oldest.
    measurements_values = [value for _, value in readings]
    lower_bound, upper_bound = min(measurements_values), max(measurements_values)
    scale = 1 if isfinite(float(upper_bound) - float(lower_bound)) else 2
    difference = upper_bound / scale - lower_bound / scale
    dates = [utc_datetime(timestamp) for timestamp, _ in readings]
    start, end = dates[-1], dates[0]
    duration = (end - start).total_seconds()
    points = []
    for timestamp, value in reversed(list(zip(dates, measurements_values))):
        x = 12 + 536 * (timestamp - start).total_seconds() / duration if duration else 280
        y = 116 - 104 * ((value / scale - lower_bound / scale) / difference) if difference else 64
        points.append({"x": round(x, 2), "y": round(y, 2), "fecha": timestamp.isoformat(), "valor": value})
    return {
        "etiqueta": label, "unidad": unit, "cantidad": len(measurements_values), "ultimo": measurements_values[0],
        "promedio": mean(measurements_values), "minimo": lower_bound, "maximo": upper_bound, "puntos": points,
        "inicio": start.isoformat(), "fin": end.isoformat(),
    }


def monitoring_statistics(entries):
    measurements_values = {kind: [] for kind in VITAL_SIGNS}
    record_history = []
    for entry in entries:
        measurements = {}
        for measured_value in entry["mediciones"]:
            kind = measured_value["tipo"].strip().casefold()
            value = measured_value["valor"]
            if (kind in VITAL_SIGNS and measured_value["unidad"].strip().casefold() == VITAL_SIGNS[kind][1].casefold()
                    and type(value) in (int, float) and -float_info.max <= value <= float_info.max):
                measurements.setdefault(kind, []).append(value)
        if measurements:
            record_history.append({"fecha_hora": entry["fecha_hora"], "clave": entry["clave"], "mediciones": measurements})
        for kind, readings in measurements.items():
            measurements_values[kind].extend((entry["fecha_hora"], value) for value in reversed(readings))

    medical_summary = {kind: statistics_series(*VITAL_SIGNS[kind], readings) for kind, readings in measurements_values.items()}
    return medical_summary, record_history


def write_json_file(destination, content_blob):
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_file = None
    try:
        with NamedTemporaryFile(dir=destination.parent, delete=False) as uploaded_file:
            temporary_file = Path(uploaded_file.name)
            uploaded_file.write(content_blob)
        temporary_file.replace(destination)
    finally:
        if temporary_file is not None:
            temporary_file.unlink(missing_ok=True)


def emergency_json_requested():
    return (
        request.endpoint == "chat_psicologico"
        and request.args.get("modo") == "emergencia"
        and request.accept_mimetypes.best == "application/json"
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
        MAX_CONTENT_LENGTH=256 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    app.jinja_env.globals["t"] = t
    app.add_template_filter(short_date, "short_date")

    @app.template_filter("ai_reply")
    def display_ai_reply(value):
        try:
            return reply_text(value)
        except ValueError:
            return t("This earlier reply is unavailable in a readable format.")
    uri_mongo = os.getenv("MONGODB_URI", "").strip() if database is None else ""
    if uri_mongo:
        import db_mongo as storage

        database = storage.connect_database(uri_mongo, os.getenv("MONGODB_DB", "").strip() or "medispace")
        record_files = None
        account_conflict = storage.AccountConflict

        @app.errorhandler(storage.DatabaseError)
        def database_unavailable(_error):
            message = "The database could not confirm the operation. Check your history before trying again."
            if request.method == "POST" and (
                request.endpoint in JSON_TEST_ENDPOINTS or emergency_json_requested()
            ):
                return {"error": t(message)}, 503
            return t(message), 503
    else:
        storage = db
        database = database or os.getenv("MEDISPACE_DATABASE") or ROOT / "medispace.sqlite3"
        record_files = Path(f"{database}.expedientes")
        account_conflict = sqlite3.IntegrityError
        db.initialize(database)

    @app.template_filter("utc_time")
    def utc_time(timestamp):
        timestamp = utc_datetime(timestamp)
        return f"{short_date(timestamp)} {timestamp:%H:%M} UTC"

    def current_medical_record():
        return storage.medical_record_for_user(database, session.get("user_id"))

    def refresh_record_file(user_id):
        with storage.record_for_export(database, user_id) as (medical_record, rows):
            if medical_record is None:
                return None
            medical_record["chequeos"] = [entry for _, entry in merge_checkup_history(medical_record, rows)]
            identifier = secure_filename(medical_record["_id"])[:80]
            filename = f"expediente-{identifier}.json" if identifier else "expediente.json"
            content_blob = (json.dumps(medical_record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            if record_files is not None:
                try:
                    write_json_file(record_files / str(user_id) / filename, content_blob)
                except OSError as exc:
                    app.logger.warning("Could not update the record file for user %s: %s", user_id, exc)
            return filename, content_blob

    def sync_record_file(user_id):
        if record_files is None:
            return
        try:
            refresh_record_file(user_id)
        except sqlite3.OperationalError as exc:
            app.logger.warning("Deferred the medical record update for user %s: %s", user_id, exc)

    @app.after_request
    def protect_pages(response):
        if request.endpoint in {
            "index", "preparar_historial", "profile", "checkup", "summary", "registro_psicologico",
            "chat_psicologico", "historial_cognitivo",
            "download_expediente", "logout", "ejercicio", "editar_expediente", "audio_elevenlabs",
            "admin_cuentas", "admin_cuenta", "admin_eliminar_cuenta",
        } or request.endpoint in JSON_TEST_ENDPOINTS:
            response.cache_control.no_store = True
            response.headers["Content-Language"] = current_language()
            if requested_language():
                response.set_cookie("medispace_lang", requested_language(), max_age=31536000,
                                    httponly=True, secure=request.is_secure, samesite="Lax")
        if request.endpoint in {"admin_cuentas", "admin_cuenta", "admin_eliminar_cuenta"}:
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    def language_url(code):
        query = request.args.to_dict(flat=False)
        query["lang"] = [code]
        return f"{url_for(request.endpoint, **(request.view_args or {}))}?{urlencode(query, doseq=True)}"

    @app.context_processor
    def page_context():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return {
            "utc_clock": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "csrf": session["csrf"],
            "fases": {lookup_key: t(label) for lookup_key, label in PHASES.items()},
            "signos": VITAL_SIGNS,
            "contextos_fc": HEART_RATE_CONTEXTS,
            "limites_captura": INPUT_LIMITS,
            "etiquetas_resultado": {lookup_key: t(label) for lookup_key, label in RESULT_LABELS.items()},
            "language": current_language(),
            "elevenlabs_disponible": elevenlabs_settings() is not None,
            "language_url": language_url,
        }

    @app.before_request
    def validate_form():
        if request.method == "POST":
            if request.endpoint == "index" and request.args.get("mode") == "register":
                request.max_content_length = 8 * 1024 * 1024
            if request.endpoint == "editar_expediente":
                request.max_content_length = 8 * 1024 * 1024
                request.max_form_memory_size = request.max_content_length
            expected = session.get("csrf", "")
            token = request.form.get("csrf", "")
            if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
                if request.endpoint == "admin_eliminar_cuenta":
                    abort(403)
                if request.endpoint == "audio_elevenlabs":
                    return {"error": t("Reload the chat to renew the voice session.")}, 403
                if request.endpoint in JSON_TEST_ENDPOINTS:
                    return {"error": t("Your session changed or expired. Sign in again to save another round.")}, 403
                if request.endpoint == "chat_psicologico" and request.args.get("modo") == "emergencia":
                    if emergency_json_requested():
                        return {"error": t("Your session changed or expired. Reopen the chat.")}, 403
                    flash("The form expired. Complete this step again.")
                    return redirect(url_for("chat_psicologico", modo="emergencia"), 303)
                if request.endpoint == "preparar_historial" and request.accept_mimetypes.best == "application/json":
                    return {"error": t("The form expired. Complete this step again.")}, 403
                flash("The form expired. Complete this step again.")
                if request.endpoint == "preparar_historial":
                    return redirect(url_for("preparar_historial"), 303)
                if request.endpoint in {
                    "checkup", "registro_psicologico", "chat_psicologico", "ejercicio", "editar_expediente",
                } and current_medical_record():
                    return redirect(url_for(request.endpoint, **request.view_args), 303)
                mode = request.args.get("mode")
                return redirect(url_for("index", mode=mode if mode in ACCESS_MODES else None), 303)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/index.html", methods=["GET", "POST"])
    def index():
        mode = request.args.get("mode", "login")
        if mode == "login-json":
            return redirect(url_for("index"), 303)
        if mode not in ACCESS_MODES:
            abort(404)
        if current_medical_record():
            return redirect(url_for("profile"), 303)

        full_name = request.form.get("nombre", "").strip()
        identifier = request.form.get("astronauta_id", "").strip()
        error = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if not full_name or not identifier:
                error = "Enter your name and astronaut ID."
            elif mode == "register":
                try:
                    if not 8 <= len(password) <= 128:
                        raise ValueError("Enter a password between 8 and 128 characters long.")
                    medical_record = read_uploaded_record()
                    if medical_record["_id"] != identifier:
                        raise ValueError("The ID must match the _id field in your JSON record.")
                    if normalized_name(medical_record["astronauta"]["nombre"]) != normalized_name(full_name):
                        raise ValueError("The name must match the astronaut's name in your JSON record.")
                    key_hash = extract_edit_key(medical_record)
                    user_id = storage.create_user(database, generate_password_hash(password), medical_record, key_hash)
                except ValueError as exc:
                    error = str(exc)
                except account_conflict:
                    error = "This astronaut ID is already registered."
            else:
                user = storage.find_user_by_astronaut_id(database, identifier)
                if (user and 0 < len(password) <= 128 and check_password_hash(user["password_hash"], password)
                        and normalized_name(user["name"]) == normalized_name(full_name)):
                    user_id = user["id"]
                else:
                    error = "The name, ID, or password is incorrect."

            if not error:
                session.clear()
                session["user_id"] = user_id
                sync_record_file(user_id)
                return redirect(url_for("profile"), 303)
        return render_template("index.html", mode=mode, full_name=full_name, identifier=identifier, error=error)

    @app.route("/historial-medico/nuevo", methods=["GET", "POST"], endpoint="preparar_historial")
    def create_medical_history():
        form_data = request.form
        rows = form_rows(form_data)
        error = None
        if request.method == "GET":
            rows = {group: [{}] for group in rows}
        else:
            action = form_data.get("accion", "descargar")
            if action == "descargar":
                try:
                    medical_record = build_medical_record(form_data, rows)
                    medical_record[EDIT_KEY_FIELD] = create_edit_key(form_data)
                except ValueError as exc:
                    error = str(exc)
                    if request.accept_mimetypes.best == "application/json":
                        return {"error": t(error)}, 400
                else:
                    identifier = secure_filename(medical_record["_id"])[:80]
                    full_name = f"expediente-{identifier}.json" if identifier else "expediente.json"
                    content_blob = json.dumps(medical_record, ensure_ascii=False, indent=2) + "\n"
                    return Response(content_blob, mimetype="application/json", headers={
                        "Content-Disposition": f'attachment; filename="{full_name}"',
                        "Cache-Control": "no-store",
                    })
            elif not adjust_form_rows(rows, action):
                abort(400)
        return render_template("historial-formulario.html", form_data=form_data, rows=rows, sections=FORM_SECTIONS, error=error)

    @app.post("/salir")
    def logout():
        session.clear()
        return redirect(url_for("index"), 303)

    @app.get("/perfil.htm")
    def profile():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        records = clinical_records(database, session["user_id"], medical_record, storage)
        return render_template(
            "perfil.htm", medical_record=medical_record, latest=records[0] if records else None,
            schedules=build_mission_schedule(medical_record, records, datetime.now(timezone.utc)),
            es_admin=storage.is_administrator(database, session["user_id"]),
        )

    def require_admin():
        account_id = session.get("user_id")
        if account_id is None:
            return redirect(url_for("index"))
        if not storage.is_administrator(database, account_id):
            abort(403)
        return None

    @app.get("/admin", endpoint="admin_cuentas")
    def admin_accounts():
        access_check = require_admin()
        if access_check is not None:
            return access_check
        identifier = request.args.get("astronauta_id", "").strip()
        page_number = request.args.get("pagina", 1, type=int)
        if not 1 <= page_number <= 1000000:
            abort(404)
        limit_value = 25
        accounts = storage.list_admin_accounts(database, identifier, (page_number - 1) * limit_value, limit_value + 1)
        return render_template(
            "admin.html", accounts=accounts[:limit_value], has_next=len(accounts) > limit_value,
            page_number=page_number, identifier=identifier,
        )

    @app.get("/admin/cuentas/<user_id>", endpoint="admin_cuenta")
    def admin_account(user_id):
        access_check = require_admin()
        if access_check is not None:
            return access_check
        section = request.args.get("seccion", "expediente")
        if section not in ADMIN_SECTIONS:
            abort(404)
        account = storage.get_admin_account(database, user_id)
        if account is None:
            abort(404)

        account_id = account["id"]
        medical_record = account.get("expediente") or {}
        groups = []
        if section == "expediente" and medical_record:
            sections_to_exclude = {"chequeos", *(field_name for fields in ADMIN_GROUPS.values() for field_name, _ in fields)}
            groups = [("Historial médico", {k: v for k, v in medical_record.items() if k not in sections_to_exclude})]
        elif section == "monitoreos" and medical_record:
            rows = storage.history(database, account_id, medical_record["_id"])
            groups = [("Saved checkups", [entry for _, entry in merge_checkup_history(medical_record, rows)])]
            active_draft = storage.get_open_checkup(database, account_id, medical_record["_id"])
            if active_draft:
                detail_text = json.loads(active_draft["details"] or "{}")
                groups.append(("Checkup in progress", {**detail_text, "conversacion": json.loads(active_draft["messages"])}))
        elif section in ADMIN_GROUPS:
            groups = [(label, medical_record.get(field_name, [])) for field_name, label in ADMIN_GROUPS[section]]
            if section == "cognicion":
                active_draft = storage.volt_draft(database, account_id)
                if active_draft:
                    groups.append(("VOLT in progress", active_draft))
        elif section == "chats":
            groups = [
                ("Support chat (includes archived messages)", storage.psych_chat(database, account_id, include_archived=True)[1]),
                ("Emergency voice chat", storage.psych_chat(database, account_id, emergency=True)[1]),
            ]
        return render_template(
            "admin.html", account=account, section=section, sections=ADMIN_SECTIONS, groups=groups,
            can_delete=account_id != session["user_id"],
        )

    @app.post("/admin/cuentas/<user_id>/eliminar", endpoint="admin_eliminar_cuenta")
    def admin_delete_account(user_id):
        access_check = require_admin()
        if access_check is not None:
            return access_check
        if request.form.get("confirmar") != "1":
            abort(400)
        account = storage.get_admin_account(database, user_id)
        if account is None:
            flash("The account no longer exists.")
            return redirect(url_for("admin_cuentas"), 303)
        administrator, account_id = session["user_id"], account["id"]
        if administrator == account_id:
            abort(403)
        try:
            deleted = storage.delete_account(database, administrator, account_id)
        except (OSError, sqlite3.OperationalError):
            app.logger.exception("Could not delete the account in SQLite")
            flash("The account could not be deleted. Try again.")
            return redirect(url_for("admin_cuenta", user_id=user_id), 303)
        if not deleted:
            if not storage.is_administrator(database, administrator):
                abort(403)
            flash("The account no longer exists.")
        else:
            flash("The account and its records were deleted.")
        return redirect(url_for("admin_cuentas"), 303)

    @app.route("/ejercicio", methods=["GET", "POST"], endpoint="ejercicio")
    def exercise():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))

        current_time = datetime.now(MISSION_TIMEZONE)
        local_timestamp = current_time.strftime("%Y-%m-%dT%H:%M")
        missions = {m["id"]: dates for m in medical_record["misiones"] if (dates := mission_dates(m))}
        selected = request.args.get("mision", "")
        if not selected:
            active_entries = [lookup_key for lookup_key, (start, end) in missions.items() if start <= current_time.date() <= end]
            if len(active_entries) == 1:
                selected = active_entries[0]
        fields = ("fecha_hora", "tipo", "duracion_min", "equipo", "esfuerzo", "recuperacion", "mision_id")
        form_data = {"fecha_hora": local_timestamp, "mision_id": selected if selected in missions else ""}
        identifier = uuid4().hex
        error = None
        if request.method == "POST":
            form_data = {field_name: request.form.get(field_name, "").strip() for field_name in fields}
            identifier = request.form.get("registro_id", "")
            try:
                timestamp = datetime.strptime(form_data["fecha_hora"], "%Y-%m-%dT%H:%M")
                if timestamp > current_time.replace(tzinfo=None):
                    raise ValueError
            except ValueError:
                error = "Enter the local date and time of a completed session."
            mission_id = form_data["mision_id"]
            if error is None:
                candidate_missions = [lookup_key for lookup_key, (start, end) in missions.items() if start <= timestamp.date() <= end]
                if mission_id and mission_id not in candidate_missions:
                    error = "The session date must fall within the selected mission."
                elif not mission_id and len(candidate_missions) == 1:
                    mission_id = candidate_missions[0]
                elif not mission_id and len(candidate_missions) > 1:
                    error = "Select the mission to count this session toward its routine."
            if error is None:
                data = {**form_data, "mision_id": mission_id}
                for field_name in ("duracion_min", "esfuerzo"):
                    try:
                        data[field_name] = int(form_data[field_name]) if form_data[field_name] else None
                    except ValueError:
                        pass
                try:
                    entry = exercise_entry(identifier, timestamp.replace(tzinfo=MISSION_TIMEZONE).isoformat(), data)
                except ValueError as exc:
                    error = str(exc)
                else:
                    account_id = session["user_id"]
                    if storage.save_record_result(database, account_id, EXERCISE_FIELD, entry, *fields):
                        sync_record_file(account_id)
                        flash("Exercise session saved.")
                        return redirect(url_for("ejercicio", mision=mission_id or None, actualizar_archivo=1), 303)
                    error = "This session already exists with different details. Reopen the form."

        entries = sorted(medical_record.get(EXERCISE_FIELD, []), key=lambda r: r["fecha_hora"], reverse=True)
        mision_seleccionada = form_data["mision_id"]
        routine = None
        if mision_seleccionada in missions:
            mission = next(m for m in medical_record["misiones"] if m["id"] == mision_seleccionada)
            routine = mission_exercise_routine(mission, *missions[mision_seleccionada], current_time.date(),
                                   summarize_exercise(entries, missions, current_time))
        start = current_time.date() - timedelta(days=6)
        week = [r for r in entries if start <= utc_datetime(r["fecha_hora"]).astimezone(MISSION_TIMEZONE).date() <= current_time.date()]
        minutes_count = {}
        efforts = {}
        for entry in week:
            kind = entry["tipo"]
            minutes_count[kind] = minutes_count.get(kind, 0) + entry["duracion_min"]
            if entry["equipo"] and entry["esfuerzo"] is not None:
                lookup_key = kind, entry["equipo"].casefold()
                efforts.setdefault(lookup_key, []).append(entry)
        charts = [
            statistics_series(
                t(EXERCISE_TYPES[kind]) + " · " + group[0]["equipo"],
                "/ 10", [(r["fecha_hora"], r["esfuerzo"]) for r in group],
            )
            for (kind, _), group in efforts.items() if len(group) > 1
        ]
        return render_template(
            "ejercicio.html", medical_record=medical_record, error=error, form_data=form_data,
            kinds=EXERCISE_TYPES, missions=missions, latest_timestamp=local_timestamp, entry_id=identifier, entries=entries,
            sesiones_semana=len(week), minutes_count=minutes_count, charts=charts,
            routine=routine, mision_seleccionada=mision_seleccionada,
            update_file=request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion", methods=["GET", "POST"], endpoint="pruebas_cognitivas")
    def cognitive_tests():
        medical_record = current_medical_record()
        if medical_record is None:
            if request.method == "POST":
                return {"error": t("Sign in to save your results.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            try:
                response_times = json.loads(request.form.get("tiempos_ms", ""))
            except (ValueError, RecursionError):
                return {"error": t("The round times could not be read.")}, 400
            try:
                entry = praxis_entry(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), response_times)
            except ValueError as exc:
                return {"error": t(str(exc))}, 400
            account_id = session["user_id"]
            if not storage.save_record_result(database, account_id, PRAXIS_FIELD, entry, "tiempos_ms"):
                return {"error": t("A different result already exists for this round ID.")}, 409
            sync_record_file(account_id)
            return {"url": url_for("pruebas_cognitivas", registro=entry["id"], actualizar_archivo=1, _anchor="praxis-guardado")}
        entries = sorted(medical_record.get(PRAXIS_FIELD, []), key=lambda entry: entry["fecha_hora"], reverse=True)
        selected_id = request.args.get("registro")
        selected_entry = next((entry for entry in entries if entry["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        update_file = selected_entry is not None and request.args.get("actualizar_archivo") == "1"
        return render_template(
            "cognicion.html", medical_record=medical_record, targets_count=PRAXIS_TARGETS, entry_id=uuid4().hex,
            entries=entries, selected_entry=selected_entry, update_file=update_file,
        )

    @app.route("/cognicion/volt", methods=["GET", "POST"], endpoint="prueba_volt")
    def visual_object_test():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        account_id = session["user_id"]
        current_time = datetime.now(timezone.utc)
        if request.method == "POST":
            action = request.form.get("accion")
            ajax = action in {"inmediato", "diferido"}
            try:
                answers = json.loads(request.form.get("respuestas", "null")) if ajax else None
                completed_id = storage.update_volt(database, account_id, action, request.form.get("registro_id"), answers, current_time)
            except (ValueError, RecursionError) as exc:
                if ajax:
                    return {"error": t(str(exc))}, 400
                flash(str(exc))
                return redirect(url_for("prueba_volt"), 303)
            destination = url_for("prueba_volt")
            if completed_id:
                sync_record_file(account_id)
                destination = url_for("prueba_volt", registro=completed_id, actualizar_archivo=1, _anchor="volt-guardado")
            return {"url": destination} if ajax else redirect(destination, 303)

        active_draft = storage.volt_draft(database, account_id)
        phase = active_draft["fase"] if active_draft else None
        learning, recognition_round, wait_seconds = [], [], 0
        if phase in {"aprendizaje", "diferido"}:
            original_items, immediate, delayed = make_stimuli(active_draft["id"])
            learning = original_items if phase == "aprendizaje" else []
            recognition_round = [shape for shape, _ in (immediate if learning else delayed)]
        elif phase == "espera":
            available_at = utc_datetime(active_draft["fin_inmediato"]) + DELAY
            wait_seconds = max(0, ceil((available_at - current_time).total_seconds()))
        entries = sorted(medical_record.get(VOLT_FIELD, []), key=lambda entry: entry["fecha_hora"], reverse=True)
        selected_id = request.args.get("registro")
        selected_entry = next((entry for entry in entries if entry["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        return render_template(
            "volt.html", medical_record=medical_record, active_draft=active_draft, phase=phase, wait_seconds=wait_seconds,
            learning=learning, recognition_round=recognition_round, exposure=EXPOSURE_SECONDS,
            shapes=SHAPE_COUNT, entries=entries, selected_entry=selected_entry,
            update_file=selected_entry is not None and request.args.get("actualizar_archivo") == "1",
        )

    def save_test_round(field_name, make_entry, answer_field, anchor):
        try:
            answers = json.loads(request.form.get("respuestas", ""))
        except (ValueError, RecursionError):
            return {"error": t("The round responses could not be read.")}, 400
        try:
            entry = make_entry(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), answers)
        except ValueError as exc:
            return {"error": t(str(exc))}, 400
        account_id = session["user_id"]
        if not storage.save_record_result(database, account_id, field_name, entry, answer_field):
            return {"error": t("A different result already exists for this round ID.")}, 409
        sync_record_file(account_id)
        return {"url": url_for(request.endpoint, registro=entry["id"], actualizar_archivo=1, _anchor=anchor)}

    @app.route("/cognicion/lot", methods=["GET", "POST"], endpoint="prueba_lot")
    def line_orientation_test():
        medical_record = current_medical_record()
        if medical_record is None:
            if request.method == "POST":
                return {"error": t("Sign in to save your results.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return save_test_round(LOT_FIELD, lot_entry, "respuestas", "lot-guardado")

        entries = sorted(medical_record.get(LOT_FIELD, []), key=lambda entry: entry["fecha_hora"], reverse=True)
        selected_id = request.args.get("registro")
        selected_entry = next((entry for entry in entries if entry["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        identifier = uuid4().hex
        rounds = [[LOT_ANGLES[number - 1] for number in pair] for pair in lot_pairs(identifier)]
        return render_template(
            "lot.html", medical_record=medical_record, entry_id=identifier, rounds=rounds, angles=LOT_ANGLES,
            options=LOT_OPTIONS, trials=LOT_TRIAL_COUNT, entries=entries, selected_entry=selected_entry,
            update_file=selected_entry is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion/f2b", methods=["GET", "POST"], endpoint="prueba_f2b")
    def fractal_2_back_test():
        medical_record = current_medical_record()
        if medical_record is None:
            if request.method == "POST":
                return {"error": t("Sign in to save your results.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return save_test_round(F2B_FIELD, f2b_entry, "respuestas_ms", "f2b-guardado")

        selected_id = request.args.get("registro")
        selected_entry = next((r for r in medical_record.get(F2B_FIELD, []) if r["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        identifier = uuid4().hex
        return render_template(
            "f2b.html", medical_record=medical_record, entry_id=identifier, selected_entry=selected_entry,
            data={"secuencia": f2b_sequence(identifier), "exposicion_ms": F2B_EXPOSURE_MS},
            matches=F2B_MATCHES,
            update_file=selected_entry is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion/emociones", methods=["GET", "POST"], endpoint="prueba_emociones")
    def emotion_recognition_test():
        medical_record = current_medical_record()
        if medical_record is None:
            if request.method == "POST":
                return {"error": t("Sign in to save your results.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return save_test_round(ERT_FIELD, emotion_test_entry, "respuestas", "emociones-guardado")

        selected_id = request.args.get("registro")
        selected_entry = next((r for r in medical_record.get(ERT_FIELD, []) if r["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        identifier = uuid4().hex
        trials = make_emotion_stimuli(identifier)
        data = {
            "laminas": {sheet: url_for("lamina_emociones", full_name=sheet) for sheet in IMAGE_SHEETS},
            "ensayos": [{"lamina": e["lamina"], "casilla": e["casilla"]} for e in trials],
            "exposicion_ms": ERT_EXPOSURE_MS,
        }
        return render_template(
            "emociones.html", medical_record=medical_record, entry_id=identifier, data=data,
            emotion_recognition=EMOTIONS, intensities=INTENSITIES, selected_entry=selected_entry,
            update_file=selected_entry is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.get("/cognicion/historial", endpoint="historial_cognitivo")
    def cognitive_history():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        tests = (
            (PRAXIS_FIELD, "Motor Praxis", "pruebas_cognitivas", "praxis-guardado", (
                ("Average reaction time", "ms", itemgetter("promedio_ms")),
                ("Fastest response", "ms", itemgetter("mejor_ms")),
            )),
            (VOLT_FIELD, "Visual Object Learning Test (VOLT)", "prueba_volt", "volt-guardado", (
                ("Correct answers in immediate recognition", "aciertos", lambda r: r["inmediato"]["correctas"]),
                ("Correct answers in delayed recognition", "aciertos", lambda r: r["diferido"]["correctas"]),
                ("Average time in immediate recognition", "ms", lambda r: r["inmediato"]["promedio_ms"]),
                ("Average time in delayed recognition", "ms", lambda r: r["diferido"]["promedio_ms"]),
            )),
            (LOT_FIELD, "Orientación de línea (LOT)", "prueba_lot", "lot-guardado", (
                ("Pares correctos", "pares", itemgetter("pares_correctos")),
                ("Líneas correctas", "lines", itemgetter("lineas_correctas")),
                ("Average time per pair", "ms", itemgetter("promedio_ms")),
            )),
            (F2B_FIELD, "Fractal 2-Back (F2B)", "prueba_f2b", "f2b-guardado", (
                ("Matches detected", "aciertos", itemgetter("aciertos")),
                ("Falsas alarmas", "respuestas", itemgetter("falsas_alarmas")),
                ("Median reaction time for hits", "ms", itemgetter("mediana_aciertos_ms")),
            )),
            (ERT_FIELD, "Facial Emotion Recognition (ERT)", "prueba_emociones", "emociones-guardado", (
                ("Accuracy", "%", itemgetter("precision_pct")),
                ("Median reaction time for hits", "ms", itemgetter("mediana_aciertos_ms")),
            )),
        )
        record_history = []
        for field_name, full_name, destination, anchor, metrics in tests:
            entries = sorted(medical_record.get(field_name, []), key=lambda r: utc_datetime(r["fecha_hora"]), reverse=True)
            series = []
            for label, unit, value in metrics:
                readings = [(r["fecha_hora"], reading) for r in entries if (reading := value(r)) is not None]
                if readings:
                    series.append(statistics_series(label, unit, readings))
            record_history.append({"nombre": full_name, "destino": destination, "ancla": anchor, "registros": entries, "series": series})
        return render_template("historial-cognitivo.html", record_history=record_history)

    @app.get("/assets/marca/<full_name>", endpoint="imagen_marca")
    def brand_image(full_name):
        return send_from_directory(ROOT / "static" / "marca", full_name)

    @app.get("/assets/emociones/<full_name>", endpoint="lamina_emociones")
    def emotion_sheet(full_name):
        return send_from_directory(ROOT / "static" / "emociones", full_name)

    @app.get("/assets/reconocimiento-emociones.js", endpoint="emociones_script")
    def emotion_test_script():
        return send_from_directory(ROOT / "static", "reconocimiento-emociones.js")

    @app.get("/assets/orientacion-linea.js")
    def lot_script():
        return send_from_directory(ROOT / "static", "orientacion-linea.js")

    @app.get("/assets/fractal-2-back.js")
    def f2b_script():
        return send_from_directory(ROOT / "static", "fractal-2-back.js")

    @app.get("/assets/memoria-visual.js")
    def volt_script():
        return send_from_directory(ROOT / "static", "memoria-visual.js")

    @app.get("/assets/praxis-motora.js", endpoint="praxis_motora_script")
    def motor_praxis_script():
        return send_from_directory(ROOT / "static", "praxis-motora.js")

    @app.get("/assets/voz-chat.js", endpoint="voz_chat_script")
    def chat_voice_script():
        return send_from_directory(ROOT / "static", "voz-chat.js")

    @app.get("/assets/chat-ui.js")
    def chat_ui_script():
        return send_from_directory(ROOT / "static", "chat-ui.js")

    @app.get("/assets/audio-ia.js", endpoint="audio_ia_script")
    def ai_audio_script():
        return send_from_directory(ROOT / "static", "audio-ia.js")

    @app.post("/voz/elevenlabs")
    def audio_elevenlabs():
        medical_record = current_medical_record()
        if medical_record is None:
            return {"error": t("Sign in again to hear the reply.")}, 401
        settings = elevenlabs_settings()
        if settings is None:
            return {"error": t("ElevenLabs needs an API key and Voice ID in Render.")}, 503
        channel = request.form.get("canal")
        if request.form.get("usar_nube") != "1" or channel not in {"medico", "psicologico", "emergencia"}:
            return "", 400
        account_id = session["user_id"]
        if channel in {"psicologico", "emergencia"}:
            _, turns = storage.psych_chat(database, account_id, emergency=channel == "emergencia")
        else:
            active_draft = storage.get_open_checkup(database, account_id, medical_record["_id"])
            turns = json.loads(active_draft["messages"]) if active_draft else []
        last_item = next((turn["text"] for turn in reversed(turns) if turn["role"] == "ai"), None)
        try:
            message_text = reply_text(last_item).replace("\r\n", "\n").replace("\r", "\n")
        except ValueError:
            return "", 404
        if request.form.get("texto") != message_text:
            return {"error": t("The latest reply has changed. Reload the chat to hear it.")}, 409
        try:
            audio = synthesize_elevenlabs(message_text, settings)
        except ElevenLabsError as exc:
            app.logger.warning("ElevenLabs speech error %s, provider HTTP status: %s", exc.code, exc.http_status or "-")
            return {"error": t(ELEVENLABS_MESSAGES[exc.code]), "codigo": exc.code}, 502
        return Response(audio, mimetype="audio/mpeg")

    @app.get("/assets/idioma.js", endpoint="idioma_script")
    def language_script():
        return send_from_directory(ROOT / "static", "idioma.js")

    @app.get("/assets/voz-emergencia.js", endpoint="voz_emergencia_script")
    def emergency_voice_script():
        return send_from_directory(ROOT / "static", "voz-emergencia.js")

    @app.get("/assets/expediente-local.js", endpoint="expediente_local_script")
    def local_record_script():
        return send_from_directory(ROOT / "static", "expediente-local.js")

    @app.get("/assets/crear-historial.js", endpoint="crear_historial_script")
    def create_history_script():
        return send_from_directory(ROOT / "static", "crear-historial.js")

    @app.route("/psicologia/<module>", methods=["GET", "POST"], endpoint="registro_psicologico")
    def psychological_check_in(module):
        if module not in MODULES:
            abort(404)
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        try:
            validate_check_ins(medical_record, module)
        except ValueError as exc:
            abort(422, description=str(exc))
        account_id = session["user_id"]
        field_name, questions, scale = MODULES[module]
        interval = INTERVALS[module]
        current_time = datetime.now(timezone.utc)
        quarters = {
            mission["id"]: mission_quarter(mission, current_time.astimezone(MISSION_TIMEZONE).date()) for mission in medical_record["misiones"]
        } if module == "semanal" else {}
        active_missions = [mission_key for mission_key, quarter in quarters.items() if quarter is not None]
        selected_mission = request.form.get("mision_id", "") if request.method == "POST" else (
            active_missions[0] if len(active_missions) == 1 else ""
        )
        entries = sorted(
            medical_record.get(field_name, []),
            key=lambda entry: utc_datetime(entry["fecha_hora"]),
            reverse=True,
        )
        available_at = db.next_check_in(entries, interval)
        is_waiting = available_at is not None and current_time < available_at
        cooldown_rejected = False
        selected_id = request.args.get("registro")
        selected_entry = next((entry for entry in entries if entry["id"] == selected_id), None)
        if selected_id and selected_entry is None:
            abort(404)
        ai_available = bool(os.getenv("GEMINI_API_KEY", "").strip())
        entry_id = uuid4().hex
        error = None
        if request.method == "POST":
            action = request.form.get("accion", "guardar")
            if action == "seguimiento":
                if selected_entry is None:
                    abort(404)
                entry = selected_entry
            elif action in {"guardar", "guardar-ia"}:
                entry_id = request.form.get("registro_id", "")
                if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
                    abort(400)
                if any(entry["id"] == entry_id for entry in entries):
                    return redirect(url_for("registro_psicologico", module=module, registro=entry_id), 303)
                try:
                    if is_waiting:
                        raise db.EarlyCheckInError(available_at)
                    answers = read_answers(request.form, module)
                    pvt = read_pvt(request.form)
                    note = request.form.get("nota", "").strip()
                    if len(note) > 600:
                        raise ValueError("The note can be up to 600 characters.")
                    if module == "semanal" and selected_mission and selected_mission not in quarters:
                        raise ValueError("Select a mission from your record.")
                    entry = {
                        "id": entry_id, "version": VERSION,
                        "fecha_hora": current_time.isoformat(),
                        "respuestas": answers, "nota": note, "pvt": pvt,
                        "puntuacion": score(answers, module), "seguimiento_ia": None,
                    }
                    if module == "semanal":
                        entry["mision_id"] = selected_mission or None
                        entry["tramo_mision"] = quarters.get(selected_mission)
                    if not storage.save_psych_report(database, account_id, field_name, entry, interval):
                        return redirect(url_for("registro_psicologico", module=module, registro=entry_id), 303)
                except db.EarlyCheckInError as exc:
                    available_at = exc.available_at
                    is_waiting = cooldown_rejected = True
                    error = str(exc)
                except ValueError as exc:
                    error = str(exc)
            else:
                abort(400)
            if error is None:
                if action in {"seguimiento", "guardar-ia"} and not entry.get("seguimiento_ia"):
                    if ai_available:
                        try:
                            guidance = generate_psychological_followup(entry, module)
                        except GEMINI_ERRORS:
                            flash("The check-in was saved. You can request AI follow-up again.")
                        else:
                            storage.save_psych_followup(database, account_id, field_name, entry["id"], guidance)
                    else:
                        flash("The check-in was saved. AI setup is still pending.")
                sync_record_file(account_id)
                return redirect(url_for(
                    "registro_psicologico", module=module, registro=entry["id"], actualizar_archivo=1,
                ), 303)
        page_number = render_template(
            "diario.html", medical_record=medical_record, entries=entries, selected_entry=selected_entry,
            module=module, questions=questions, scale=scale, entry_id=entry_id, error=error,
            quarters=quarters, selected_mission=selected_mission,
            available_at=available_at if is_waiting else None,
            ai_available=ai_available, form_data=request.form,
            update_file=selected_entry is not None and request.args.get("actualizar_archivo") == "1",
        )
        if cooldown_rejected:
            seconds_count = max(1, ceil((available_at - datetime.now(timezone.utc)).total_seconds()))
            return page_number, 429, {"Retry-After": str(seconds_count)}
        return page_number

    @app.route("/psicologia/chat", methods=["GET", "POST"], endpoint="chat_psicologico")
    def support_chat():
        emergency = request.args.get("modo") == "emergencia"
        chat_mode = "emergencia" if emergency else None
        wants_json = emergency_json_requested()
        medical_record = current_medical_record()
        if medical_record is None:
            if wants_json:
                return {"error": t("Sign in again to talk with the AI.")}, 401
            return redirect(url_for("index"))
        account_id = session["user_id"]
        revision, turns = storage.psych_chat(database, account_id, emergency=emergency)
        ai_available = bool(os.getenv("GEMINI_API_KEY", "").strip())
        message_text = request.form.get("mensaje", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("accion") == "limpiar":
                if emergency:
                    abort(400)
                if request.form.get("revision") == str(revision) and turns and storage.clear_support_chat(database, account_id, revision):
                    flash("Chat cleared. The previous conversation was saved.")
                else:
                    flash("The conversation changed. Review the messages before clearing the chat.")
                return redirect(url_for("chat_psicologico"), 303)
            if request.form.get("revision") != str(revision):
                error = "The conversation was updated. Review the messages and send yours again."
                state = 409
            elif not 1 <= len(message_text) <= 2000:
                error = "Enter a message of up to 2,000 characters."
                state = 400
            elif not ai_available:
                error = "AI setup is pending on the server."
                state = 503
            else:
                updated_messages = [*turns, {"role": "user", "text": message_text}]
                try:
                    respond = reply_to_emergency_chat if emergency else reply_to_support_chat
                    reply = respond(updated_messages)
                except GEMINI_ERRORS:
                    error = "The AI could not reply. Your message is still in the text field so you can try again."
                    state = 503
                else:
                    new_turn = [updated_messages[-1], ai_turn(reply)]
                    if storage.save_psych_chat(database, account_id, revision, new_turn, emergency=emergency):
                        if wants_json:
                            return {"revision": revision + 1, "mensajes": new_turn}
                        if request.headers.get("X-MediSpace-Chat") != "1":
                            return redirect(url_for("chat_psicologico", modo=chat_mode, _anchor="ultimo-mensaje"), 303)
                        revision += 1
                        turns = [*turns, *new_turn]
                        message_text = ""
                    else:
                        revision, turns = storage.psych_chat(database, account_id, emergency=emergency)
                        error = "The conversation was updated in another tab. Review the messages before sending again."
                        state = 409
            if wants_json:
                if state == 409:
                    error = "The conversation changed in another tab. Copy your message and reopen the chat to send it."
                return {"error": t(error)}, state
        return render_template(
            "chat-psicologico.html", medical_record=medical_record, module="chat", turns=turns,
            revision=revision, message_text=message_text, error=error, ai_available=ai_available, emergency=emergency,
        )

    @app.route("/chequeo.html", methods=["GET", "POST"])
    def checkup():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        if not os.getenv("GEMINI_API_KEY", "").strip():
            return render_template("chequeo.html", medical_record=medical_record, blocked_message="AI setup is pending on the server.")

        account_id, astronaut_id = session["user_id"], medical_record["_id"]
        draft = storage.get_open_checkup(database, account_id, astronaut_id)
        if request.method == "POST" and request.form.get("iniciar") == "1":
            if draft is None:
                try:
                    question = generate_question({"mensajes": []})
                except GEMINI_ERRORS:
                    return render_template("chequeo.html", medical_record=medical_record, blocked_message=GEMINI_ERROR_MESSAGE), 503
                storage.open_checkup(database, account_id, astronaut_id, ai_turn(question))
            return redirect(url_for("checkup"), 303)
        if draft is None:
            return redirect(url_for("profile"), 303)

        messages = json.loads(draft["messages"])
        saved_details = json.loads(draft["details"] or "{}")
        vitals = {
            key: saved_details.get("telemetria", {}).get(key, draft[key] if draft["revision"] else None)
            for key in ("hr", "spo2", "temp")
        }
        details = saved_details
        if request.method == "GET" and draft["revision"] == 0 and not details:
            today = datetime.now(MISSION_TIMEZONE).date()
            active_missions = [mission["id"] for mission in medical_record["misiones"]
                        if (dates := mission_dates(mission)) and dates[0] <= today <= dates[1]]
            if len(active_missions) == 1:
                details = {"mision_id": active_missions[0], "fase": "vuelo"}
        answer = request.form.get("answer", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("turn") != f"{draft['id']}:{draft['revision']}":
                return redirect(url_for("checkup"), 303)
            action = request.form.get("accion", "enviar")
            if action not in {"enviar", "finalizar"}:
                abort(400)
            vitals = {key: request.form.get(key, "").strip() for key in vitals}
            details = {field_name: request.form.get(field_name, "").strip()
                       for field_name in ("mision_id", "fase", "motivo", "actividad", "contexto_fc")}
            missions = {mission["id"] for mission in medical_record["misiones"]}
            measured_values = {}
            try:
                for key, (kind, _, convert) in MONITORING_MEASUREMENTS.items():
                    lower_bound, upper_bound = INPUT_LIMITS[kind]
                    value = convert(vitals[key]) if vitals[key] else None
                    if value is not None and not lower_bound <= value <= upper_bound:
                        raise ValueError
                    measured_values[key] = value
            except ValueError:
                error = "Check the format and units of your measurements."
            if ((details["mision_id"] and details["mision_id"] not in missions)
                    or (details["fase"] and details["fase"] not in PHASES)):
                error = "Select a mission and phase from your record."
            if any(len(details[field_name]) > 200 for field_name in ("motivo", "actividad")):
                error = "The reason and activity fields each allow up to 200 characters."
            if details["contexto_fc"] and details["contexto_fc"] not in HEART_RATE_CONTEXTS:
                error = "Select a valid context for the heart rate reading."
            if len(answer) > 1000 or (action == "enviar" and not answer):
                error = "Enter a reply of up to 1,000 characters."
            if not error:
                updated = [*messages, {"role": "user", "text": answer}] if answer else messages
                status = None
                details["telemetria"] = measured_values
                context = {
                    "telemetria": {label: measured_values[key] for key, (_, label, _) in MONITORING_MEASUREMENTS.items()
                                   if measured_values[key] is not None},
                    "fase": details["fase"], "actividad": details["actividad"], "motivo": details["motivo"],
                }
                comparison = compare_reference_ranges(measured_values, medical_record.get("referencias_monitoreo", {}))
                if measured_values["hr"] is not None and details["contexto_fc"]:
                    context["contexto_fc"] = details["contexto_fc"]
                    if details["contexto_fc"] in EXERCISE_HEART_RATE_CONTEXTS:
                        comparison.pop("frecuencia_cardiaca", None)
                else:
                    details.pop("contexto_fc")
                if comparison:
                    context["comparacion_referencias"] = comparison
                try:
                    conversation, memory = prepare_conversation(updated, saved_details.get("memoria_ia"))
                    if action == "finalizar":
                        assessment = assess_checkup(conversation, context)
                        status = assessment["estado"]
                        details["evaluacion_ia"] = assessment
                        if comparison:
                            details["comparacion_referencias"] = comparison
                    else:
                        question = generate_question(conversation, context)
                        updated.append(ai_turn(question))
                        if memory:
                            details["memoria_ia"] = memory
                except GEMINI_ERRORS:
                    error = GEMINI_ERROR_MESSAGE
                if not error:
                    sql_values = tuple(measured_values[key] if measured_values[key] is not None else 0 for key in ("hr", "spo2", "temp"))
                    saved = storage.save_turn(database, draft, updated, sql_values, details, status)
                    if saved and status:
                        sync_record_file(account_id)
                        return redirect(url_for("summary", registro=f"app-{draft['id']}", actualizar_archivo=1), 303)
                    if not saved or request.headers.get("X-MediSpace-Chat") != "1":
                        return redirect(url_for("checkup"), 303)
                    draft = {**draft, "revision": draft["revision"] + 1}
                    messages, vitals, answer = updated, measured_values, ""
        return render_template(
            "chequeo.html", messages=messages, vitals=vitals, draft=draft, answer=answer, error=error,
            medical_record=medical_record, details=details,
        )

    @app.route("/expediente/editar", methods=["GET", "POST"], endpoint="editar_expediente")
    def edit_medical_record():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        account_id = session["user_id"]
        credentials = storage.edit_credentials(database, account_id)
        if credentials is None:
            return redirect(url_for("index"))
        stored_key = credentials["clave_edicion_hash"]
        action = request.form.get("accion")
        authorized = stored_key and session.get("editor_usuario") == account_id
        if authorized and action == "cerrar":
            session.pop("editor_usuario", None)
            return redirect(url_for("summary", vista="historial"), 303)
        if not authorized:
            error = None
            if action == "desbloquear":
                if verify_credential(stored_key, request.form.get("llave_edicion", "")):
                    session["editor_usuario"] = account_id
                    return redirect(url_for("editar_expediente"), 303)
                error = "The editing key is incorrect."
            elif action == "configurar" and not stored_key:
                if not verify_credential(credentials["password_hash"], request.form.get("password", "")):
                    error = "The account password is incorrect."
                else:
                    try:
                        key_hash = create_edit_key(request.form)
                    except ValueError as exc:
                        error = str(exc)
                    else:
                        if storage.configure_edit_key(database, account_id, key_hash):
                            session["editor_usuario"] = account_id
                        return redirect(url_for("editar_expediente"), 303)
            elif request.method == "POST":
                error = "Unlock the editor with your key before saving."
            return render_template("editar-expediente.html", configure=not stored_key, error=error), (
                403 if error else 200
            )

        error = None
        state = 200
        if request.method == "POST":
            form_data = request.form
            version = form_data.get("version", "")
            targets = form_data.getlist("misiones.ejercicio_min_diarios")
            rows = form_rows(form_data, editing=True)
            rows["misiones"] = mission_rows(medical_record, targets)
            if action == "guardar":
                try:
                    stored = storage.update_medical_record(
                        database, account_id, lambda selected_entry: apply_record_edit(selected_entry, version, form_data, rows, targets),
                    )
                except StaleEditError as exc:
                    error, state = str(exc), 409
                except ValueError as exc:
                    error, state = str(exc), 400
                else:
                    if not stored:
                        return redirect(url_for("index"))
                    session.pop("editor_usuario", None)
                    sync_record_file(account_id)
                    flash("Record changes saved.")
                    return redirect(url_for("summary", vista="historial", actualizar_archivo=1), 303)
            elif not adjust_form_rows({group: rows[group] for group in EDITABLE_GROUPS}, action or ""):
                abort(400)
        else:
            form_data, rows = edit_form(medical_record)
            version = edit_version(medical_record)
        return render_template(
            "historial-formulario.html", medical_record=medical_record, form_data=form_data, rows=rows,
            sections=EDIT_SECTIONS, editing=True, version=version, error=error,
        ), state

    @app.get("/expediente.json", endpoint="download_expediente")
    def download_medical_record():
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("index"))
        uploaded_file = refresh_record_file(user_id)
        if uploaded_file is None:
            return redirect(url_for("index"))
        filename, content_blob = uploaded_file
        return Response(
            content_blob,
            content_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/resumen.html")
    def summary():
        medical_record = current_medical_record()
        if medical_record is None:
            return redirect(url_for("index"))
        view = request.args.get("vista", "resultados")
        if view not in {"resultados", "alertas", "historial", "estadisticas"}:
            return redirect(url_for("summary"))
        records = clinical_records(database, session["user_id"], medical_record, storage)
        lookup_key = request.args.get("registro")
        latest = next((entry for entry in records if entry["clave"] == lookup_key), None) if lookup_key else (records[0] if records else None)
        if lookup_key and latest is None:
            abort(404)
        statistics_view, historical_measurements = monitoring_statistics(records) if view == "estadisticas" else ({}, [])
        return render_template(
            "resumen.html", view=view, latest=latest, records=records, medical_record=medical_record,
            statistics_view=statistics_view, historical_measurements=historical_measurements,
            update_file=view in {"resultados", "historial"} and request.args.get("actualizar_archivo") == "1",
        )

    return app


if __name__ == "__main__":
    create_app().run()
