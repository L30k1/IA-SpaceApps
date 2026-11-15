import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from math import ceil, isfinite
from operator import itemgetter
from pathlib import Path
from statistics import mean
from sys import float_info
from tempfile import NamedTemporaryFile
from unicodedata import normalize
from uuid import uuid4

import httpx2
from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from google.genai.errors import APIError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import db
from asistente import evaluar_chequeo, generar_pregunta, preparar_conversacion
from calendario_mision import calendario
from database.expedientes import (
    CAMPO_PRAXIS, FASES, OBJETIVOS_PRAXIS, SIGNOS, fecha_utc, leer_expediente, registro_lot, registro_praxis,
)
from lot import ANGULOS_LOT, CAMPO_LOT, ENSAYOS_LOT, OPCIONES_LOT, pares_lot
from psicologia import (
    INTERVALOS, MODULOS, VERSION, leer_pvt, leer_respuestas, puntuar, responder_chat_psicologico, seguimiento_psicologico,
    tramo_mision, validar_registros,
)
from volt import CAMPO_VOLT, ESPERA, EXPOSICION, FIGURAS, estimulos


ROOT = Path(__file__).resolve().parent
MODOS_ACCESO = {"login", "register"}
ETIQUETAS_RESULTADO = {
    "ALERTA": "Revisión prioritaria sugerida",
    "ESTABLE": "Sin prioridad adicional sugerida",
    "INDETERMINADO": "Información por aclarar",
}
ERRORES_GEMINI = (APIError, httpx2.HTTPError, ValueError)
MENSAJE_GEMINI = "La IA no devolvió una respuesta válida. Vuelve a intentarlo."


def leer_expediente_subido():
    archivo = request.files.get("expediente")
    if not archivo or not archivo.filename.lower().endswith(".json"):
        raise ValueError("Selecciona tu expediente en formato JSON.")
    expediente = leer_expediente(archivo.read())
    for modulo in MODULOS:
        validar_registros(expediente, modulo)
    return expediente


def nombre_normalizado(nombre):
    return normalize("NFC", " ".join(nombre.split())).casefold()


def historial_expediente(expediente, filas):
    chequeos = {registro["id"]: registro for registro in expediente["chequeos"]}
    registros = []
    for row in filas:
        details = json.loads(row["details"] or "{}")
        record_id = details.get("expediente_chequeo_id")
        registro = chequeos.pop(record_id, None)
        if registro is None:
            record_id = record_id or f"chequeo-anterior-{row['id']}"
            while record_id in chequeos:
                record_id += "-local"
            registro = db.checkup_record(
                record_id, row["finished_at"], json.loads(row["messages"]),
                (row["hr"], row["spo2"], row["temp"]), details, row["status"],
            )
        registros.append((f"app-{row['id']}", registro))
    registros.extend((f"json-{record_id}", registro) for record_id, registro in chequeos.items())
    return sorted(registros, key=lambda item: fecha_utc(item[1]["fecha_hora"]), reverse=True)


def registros_clinicos(database, user_id, expediente, almacen=db):
    return [
        {**registro, "clave": clave, "estado": registro.get("resultado") or registro.get("resultado_simulador"),
         "evaluacion_ia": registro.get("evaluacion_ia") if clave.startswith("app-") else None}
        for clave, registro in historial_expediente(expediente, almacen.history(database, user_id, expediente["_id"]))
    ]


def serie_estadistica(etiqueta, unidad, lecturas):
    if not lecturas:
        return None
    # El historial llega del más reciente al más antiguo.
    valores = [valor for _, valor in lecturas]
    minimo, maximo = min(valores), max(valores)
    escala = 1 if isfinite(float(maximo) - float(minimo)) else 2
    diferencia = maximo / escala - minimo / escala
    fechas = [fecha_utc(fecha) for fecha, _ in lecturas]
    inicio, fin = fechas[-1], fechas[0]
    duracion = (fin - inicio).total_seconds()
    puntos = []
    for fecha, valor in reversed(list(zip(fechas, valores))):
        x = 12 + 536 * (fecha - inicio).total_seconds() / duracion if duracion else 280
        y = 116 - 104 * ((valor / escala - minimo / escala) / diferencia) if diferencia else 64
        puntos.append({"x": round(x, 2), "y": round(y, 2), "fecha": fecha.isoformat(), "valor": valor})
    return {
        "etiqueta": etiqueta, "unidad": unidad, "cantidad": len(valores), "ultimo": valores[0],
        "promedio": mean(valores), "minimo": minimo, "maximo": maximo, "puntos": puntos,
        "inicio": inicio.isoformat(), "fin": fin.isoformat(),
    }


def estadisticas_monitoreo(registros):
    valores = {tipo: [] for tipo in SIGNOS}
    historial = []
    for registro in registros:
        mediciones = {}
        for medida in registro["mediciones"]:
            tipo = medida["tipo"].strip().casefold()
            valor = medida["valor"]
            if (tipo in SIGNOS and medida["unidad"].strip().casefold() == SIGNOS[tipo][1].casefold()
                    and type(valor) in (int, float) and -float_info.max <= valor <= float_info.max):
                mediciones.setdefault(tipo, []).append(valor)
        if mediciones:
            historial.append({"fecha_hora": registro["fecha_hora"], "clave": registro["clave"], "mediciones": mediciones})
        for tipo, lecturas in mediciones.items():
            valores[tipo].extend((registro["fecha_hora"], valor) for valor in reversed(lecturas))

    resumen = {tipo: serie_estadistica(*SIGNOS[tipo], lecturas) for tipo, lecturas in valores.items()}
    return resumen, historial


def escribir_archivo_json(destino, contenido):
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporal = None
    try:
        with NamedTemporaryFile(dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        temporal.replace(destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


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
    uri_mongo = os.getenv("MONGODB_URI", "").strip() if database is None else ""
    if uri_mongo:
        import db_mongo as almacen

        database = almacen.conectar(uri_mongo, os.getenv("MONGODB_DB", "").strip() or "medispace")
        archivos_expedientes = None
        conflicto_cuenta = almacen.ConflictoCuenta

        @app.errorhandler(almacen.ErrorBase)
        def base_no_disponible(_error):
            mensaje = "No se pudo confirmar la operación en la base de datos. Revisa tu historial antes de reintentar."
            if request.method == "POST" and request.endpoint in {"pruebas_cognitivas", "prueba_volt", "prueba_lot"}:
                return {"error": mensaje}, 503
            return mensaje, 503
    else:
        almacen = db
        database = database or os.getenv("MEDISPACE_DATABASE") or ROOT / "medispace.sqlite3"
        archivos_expedientes = Path(f"{database}.expedientes")
        conflicto_cuenta = sqlite3.IntegrityError
        db.initialize(database)

    @app.template_filter("hora_utc")
    def hora_utc(fecha):
        return fecha_utc(fecha).strftime("%d/%m/%Y %H:%M UTC")

    def expediente_actual():
        return almacen.expediente_for_user(database, session.get("user_id"))

    def actualizar_archivo_expediente(user_id):
        with almacen.expediente_para_archivo(database, user_id) as (expediente, filas):
            if expediente is None:
                return None
            expediente["chequeos"] = [registro for _, registro in historial_expediente(expediente, filas)]
            identificador = secure_filename(expediente["_id"])[:80]
            filename = f"expediente-{identificador}.json" if identificador else "expediente.json"
            contenido = (json.dumps(expediente, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            if archivos_expedientes is not None:
                try:
                    escribir_archivo_json(archivos_expedientes / str(user_id) / filename, contenido)
                except OSError as exc:
                    app.logger.warning("No se pudo actualizar el archivo del usuario %s: %s", user_id, exc)
            return filename, contenido

    def sincronizar_archivo_expediente(user_id):
        if archivos_expedientes is None:
            return
        try:
            actualizar_archivo_expediente(user_id)
        except sqlite3.OperationalError as exc:
            app.logger.warning("Se aplazó la actualización del expediente del usuario %s: %s", user_id, exc)

    @app.after_request
    def proteger_paginas(response):
        if request.endpoint in {
            "index", "profile", "checkup", "summary", "registro_psicologico",
            "chat_psicologico", "pruebas_cognitivas", "prueba_volt", "prueba_lot", "historial_cognitivo",
            "download_expediente", "logout",
        }:
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
            "etiquetas_resultado": ETIQUETAS_RESULTADO,
        }

    @app.before_request
    def validate_form():
        if request.method == "POST":
            if request.endpoint == "index" and request.args.get("mode") == "register":
                request.max_content_length = 8 * 1024 * 1024
            expected = session.get("csrf", "")
            token = request.form.get("csrf", "")
            if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
                if request.endpoint in {"pruebas_cognitivas", "prueba_volt", "prueba_lot"}:
                    return {"error": "La sesión cambió o caducó. Vuelve a iniciar sesión para guardar otra ronda."}, 403
                flash("El formulario caducó. Vuelve a completar el paso.")
                if request.endpoint in {"checkup", "registro_psicologico", "chat_psicologico"} and expediente_actual():
                    return redirect(url_for(request.endpoint, **request.view_args), 303)
                mode = request.args.get("mode")
                return redirect(url_for("index", mode=mode if mode in MODOS_ACCESO else None), 303)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/index.html", methods=["GET", "POST"])
    def index():
        mode = request.args.get("mode", "login")
        if mode == "login-json":
            return redirect(url_for("index"), 303)
        if mode not in MODOS_ACCESO:
            abort(404)
        if expediente_actual():
            return redirect(url_for("profile"), 303)

        nombre = request.form.get("nombre", "").strip()
        identificador = request.form.get("astronauta_id", "").strip()
        error = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if not nombre or not identificador:
                error = "Escribe tu nombre y el ID del astronauta."
            elif mode == "register":
                try:
                    if not 8 <= len(password) <= 128:
                        raise ValueError("Escribe una contraseña de 8 a 128 caracteres.")
                    expediente = leer_expediente_subido()
                    if expediente["_id"] != identificador:
                        raise ValueError("El ID debe coincidir con el campo _id de tu historial JSON.")
                    if nombre_normalizado(expediente["astronauta"]["nombre"]) != nombre_normalizado(nombre):
                        raise ValueError("El nombre debe coincidir con el del astronauta en tu historial JSON.")
                    user_id = almacen.create_user(database, generate_password_hash(password), expediente)
                except ValueError as exc:
                    error = str(exc)
                except conflicto_cuenta:
                    error = "El identificador del astronauta ya está registrado."
            else:
                user = almacen.find_user_by_astronauta(database, identificador)
                if (user and 0 < len(password) <= 128 and check_password_hash(user["password_hash"], password)
                        and nombre_normalizado(user["name"]) == nombre_normalizado(nombre)):
                    user_id = user["id"]
                else:
                    error = "El nombre, el ID o la contraseña son incorrectos."

            if not error:
                session.clear()
                session["user_id"] = user_id
                sincronizar_archivo_expediente(user_id)
                return redirect(url_for("profile"), 303)
        return render_template("index.html", mode=mode, nombre=nombre, identificador=identificador, error=error)

    @app.post("/salir")
    def logout():
        session.clear()
        return redirect(url_for("index"), 303)

    @app.get("/perfil.htm")
    def profile():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        records = registros_clinicos(database, session["user_id"], expediente, almacen)
        return render_template(
            "perfil.htm", expediente=expediente, latest=records[0] if records else None,
            planes=calendario(expediente, records, datetime.now(timezone.utc)),
        )

    @app.route("/cognicion", methods=["GET", "POST"])
    def pruebas_cognitivas():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": "Inicia sesión para guardar los resultados."}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            try:
                tiempos = json.loads(request.form.get("tiempos_ms", ""))
            except (ValueError, RecursionError):
                return {"error": "No se pudieron leer los tiempos de la ronda."}, 400
            try:
                registro = registro_praxis(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), tiempos)
            except ValueError as exc:
                return {"error": str(exc)}, 400
            usuario = session["user_id"]
            if not almacen.save_cognitive_report(database, usuario, CAMPO_PRAXIS, registro, "tiempos_ms"):
                return {"error": "Ya existe un resultado diferente con el identificador de esta ronda."}, 409
            sincronizar_archivo_expediente(usuario)
            return {"url": url_for("pruebas_cognitivas", registro=registro["id"], actualizar_archivo=1, _anchor="praxis-guardado")}
        registros = sorted(expediente.get(CAMPO_PRAXIS, []), key=lambda registro: registro["fecha_hora"], reverse=True)
        seleccionado = request.args.get("registro")
        actual = next((registro for registro in registros if registro["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        actualizar_archivo = actual is not None and request.args.get("actualizar_archivo") == "1"
        return render_template(
            "cognicion.html", expediente=expediente, objetivos=OBJETIVOS_PRAXIS, registro_id=uuid4().hex,
            registros=registros, actual=actual, actualizar_archivo=actualizar_archivo,
        )

    @app.route("/cognicion/volt", methods=["GET", "POST"])
    def prueba_volt():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        usuario = session["user_id"]
        ahora = datetime.now(timezone.utc)
        if request.method == "POST":
            accion = request.form.get("accion")
            ajax = accion in {"inmediato", "diferido"}
            try:
                respuestas = json.loads(request.form.get("respuestas", "null")) if ajax else None
                completado = almacen.actualizar_volt(database, usuario, accion, request.form.get("registro_id"), respuestas, ahora)
            except (ValueError, RecursionError) as exc:
                if ajax:
                    return {"error": str(exc)}, 400
                flash(str(exc))
                return redirect(url_for("prueba_volt"), 303)
            destino = url_for("prueba_volt")
            if completado:
                sincronizar_archivo_expediente(usuario)
                destino = url_for("prueba_volt", registro=completado, actualizar_archivo=1, _anchor="volt-guardado")
            return {"url": destino} if ajax else redirect(destino, 303)

        borrador = almacen.volt_draft(database, usuario)
        fase = borrador["fase"] if borrador else None
        aprendizaje, reconocimiento, espera = [], [], 0
        if fase in {"aprendizaje", "diferido"}:
            originales, inmediato, diferido = estimulos(borrador["id"])
            aprendizaje = originales if fase == "aprendizaje" else []
            reconocimiento = [forma for forma, _ in (inmediato if aprendizaje else diferido)]
        elif fase == "espera":
            disponible = fecha_utc(borrador["fin_inmediato"]) + ESPERA
            espera = max(0, ceil((disponible - ahora).total_seconds()))
        registros = sorted(expediente.get(CAMPO_VOLT, []), key=lambda registro: registro["fecha_hora"], reverse=True)
        seleccionado = request.args.get("registro")
        actual = next((registro for registro in registros if registro["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        return render_template(
            "volt.html", expediente=expediente, borrador=borrador, fase=fase, espera=espera,
            aprendizaje=aprendizaje, reconocimiento=reconocimiento, exposicion=EXPOSICION,
            figuras=FIGURAS, registros=registros, actual=actual,
            actualizar_archivo=actual is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion/lot", methods=["GET", "POST"])
    def prueba_lot():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": "Inicia sesión para guardar los resultados."}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            try:
                respuestas = json.loads(request.form.get("respuestas", ""))
            except (ValueError, RecursionError):
                return {"error": "No se pudieron leer las respuestas de la ronda."}, 400
            try:
                registro = registro_lot(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), respuestas)
            except ValueError as exc:
                return {"error": str(exc)}, 400
            usuario = session["user_id"]
            if not almacen.save_cognitive_report(database, usuario, CAMPO_LOT, registro, "respuestas"):
                return {"error": "Ya existe un resultado diferente con el identificador de esta ronda."}, 409
            sincronizar_archivo_expediente(usuario)
            destino = url_for("prueba_lot", registro=registro["id"], actualizar_archivo=1, _anchor="lot-guardado")
            return {"url": destino}

        registros = sorted(expediente.get(CAMPO_LOT, []), key=lambda registro: registro["fecha_hora"], reverse=True)
        seleccionado = request.args.get("registro")
        actual = next((registro for registro in registros if registro["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        identificador = uuid4().hex
        rondas = [[ANGULOS_LOT[numero - 1] for numero in par] for par in pares_lot(identificador)]
        return render_template(
            "lot.html", expediente=expediente, registro_id=identificador, rondas=rondas, angulos=ANGULOS_LOT,
            opciones=OPCIONES_LOT, ensayos=ENSAYOS_LOT, registros=registros, actual=actual,
            actualizar_archivo=actual is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.get("/cognicion/historial")
    def historial_cognitivo():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        pruebas = (
            (CAMPO_PRAXIS, "Praxis Motora", "pruebas_cognitivas", "praxis-guardado", (
                ("Tiempo medio de reacción", "ms", itemgetter("promedio_ms")),
                ("Respuesta más rápida", "ms", itemgetter("mejor_ms")),
            )),
            (CAMPO_VOLT, "Aprendizaje visual de objetos (VOLT)", "prueba_volt", "volt-guardado", (
                ("Aciertos en reconocimiento inmediato", "aciertos", lambda r: r["inmediato"]["correctas"]),
                ("Aciertos en reconocimiento diferido", "aciertos", lambda r: r["diferido"]["correctas"]),
                ("Tiempo medio en reconocimiento inmediato", "ms", lambda r: r["inmediato"]["promedio_ms"]),
                ("Tiempo medio en reconocimiento diferido", "ms", lambda r: r["diferido"]["promedio_ms"]),
            )),
            (CAMPO_LOT, "Orientación de línea (LOT)", "prueba_lot", "lot-guardado", (
                ("Pares correctos", "pares", itemgetter("pares_correctos")),
                ("Líneas correctas", "líneas", itemgetter("lineas_correctas")),
                ("Tiempo medio por par", "ms", itemgetter("promedio_ms")),
            )),
        )
        historial = []
        for campo, nombre, destino, ancla, metricas in pruebas:
            registros = sorted(expediente.get(campo, []), key=lambda r: fecha_utc(r["fecha_hora"]), reverse=True)
            series = [
                serie_estadistica(etiqueta, unidad, [(r["fecha_hora"], valor(r)) for r in registros])
                for etiqueta, unidad, valor in metricas
            ] if registros else []
            historial.append({"nombre": nombre, "destino": destino, "ancla": ancla, "registros": registros, "series": series})
        return render_template("historial-cognitivo.html", historial=historial)

    @app.get("/assets/orientacion-linea.js")
    def lot_script():
        return send_from_directory(ROOT / "static", "orientacion-linea.js")

    @app.get("/assets/memoria-visual.js")
    def volt_script():
        return send_from_directory(ROOT / "static", "memoria-visual.js")

    @app.get("/assets/praxis-motora.js")
    def praxis_motora_script():
        return send_from_directory(ROOT / "static", "praxis-motora.js")

    @app.get("/assets/voz-chat.js")
    def voz_chat_script():
        return send_from_directory(ROOT / "static", "voz-chat.js")

    @app.get("/assets/expediente-local.js")
    def expediente_local_script():
        return send_from_directory(ROOT / "static", "expediente-local.js")

    @app.route("/psicologia/<modulo>", methods=["GET", "POST"])
    def registro_psicologico(modulo):
        if modulo not in MODULOS:
            abort(404)
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        try:
            validar_registros(expediente, modulo)
        except ValueError as exc:
            abort(422, description=str(exc))
        usuario = session["user_id"]
        campo, reactivos, escala = MODULOS[modulo]
        intervalo = INTERVALOS[modulo]
        ahora = datetime.now(timezone.utc)
        tramos = {
            mision["id"]: tramo_mision(mision, ahora.date()) for mision in expediente["misiones"]
        } if modulo == "semanal" else {}
        en_curso = [id_mision for id_mision, tramo in tramos.items() if tramo is not None]
        mision_elegida = request.form.get("mision_id", "") if request.method == "POST" else (
            en_curso[0] if len(en_curso) == 1 else ""
        )
        registros = sorted(
            expediente.get(campo, []),
            key=lambda registro: fecha_utc(registro["fecha_hora"]),
            reverse=True,
        )
        disponible = db.proximo_registro(registros, intervalo)
        en_espera = disponible is not None and ahora < disponible
        espera_rechazada = False
        seleccionado = request.args.get("registro")
        actual = next((registro for registro in registros if registro["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        ia_disponible = bool(os.getenv("GEMINI_API_KEY", "").strip())
        registro_id = uuid4().hex
        error = None
        if request.method == "POST":
            accion = request.form.get("accion", "guardar")
            if accion == "seguimiento":
                if actual is None:
                    abort(404)
                registro = actual
            elif accion in {"guardar", "guardar-ia"}:
                registro_id = request.form.get("registro_id", "")
                if not re.fullmatch(r"[0-9a-f]{32}", registro_id):
                    abort(400)
                if any(registro["id"] == registro_id for registro in registros):
                    return redirect(url_for("registro_psicologico", modulo=modulo, registro=registro_id), 303)
                try:
                    if en_espera:
                        raise db.RegistroPrematuro(disponible)
                    respuestas = leer_respuestas(request.form, modulo)
                    pvt = leer_pvt(request.form)
                    nota = request.form.get("nota", "").strip()
                    if len(nota) > 600:
                        raise ValueError("La nota admite hasta 600 caracteres.")
                    if modulo == "semanal" and mision_elegida and mision_elegida not in tramos:
                        raise ValueError("Selecciona una misión de tu expediente.")
                    registro = {
                        "id": registro_id, "version": VERSION,
                        "fecha_hora": ahora.isoformat(),
                        "respuestas": respuestas, "nota": nota, "pvt": pvt,
                        "puntuacion": puntuar(respuestas, modulo), "seguimiento_ia": None,
                    }
                    if modulo == "semanal":
                        registro["mision_id"] = mision_elegida or None
                        registro["tramo_mision"] = tramos.get(mision_elegida)
                    if not almacen.save_psych_report(database, usuario, campo, registro, intervalo):
                        return redirect(url_for("registro_psicologico", modulo=modulo, registro=registro_id), 303)
                except db.RegistroPrematuro as exc:
                    disponible = exc.disponible
                    en_espera = espera_rechazada = True
                    error = str(exc)
                except ValueError as exc:
                    error = str(exc)
            else:
                abort(400)
            if error is None:
                if accion in {"seguimiento", "guardar-ia"} and not registro.get("seguimiento_ia"):
                    if ia_disponible:
                        try:
                            orientacion = seguimiento_psicologico(registro, modulo)
                        except ERRORES_GEMINI:
                            flash("El registro se guardó. Puedes volver a solicitar el seguimiento de IA.")
                        else:
                            almacen.save_psych_followup(database, usuario, campo, registro["id"], orientacion)
                    else:
                        flash("El registro se guardó. La IA aún no está configurada.")
                sincronizar_archivo_expediente(usuario)
                return redirect(url_for(
                    "registro_psicologico", modulo=modulo, registro=registro["id"], actualizar_archivo=1,
                ), 303)
        pagina = render_template(
            "diario.html", expediente=expediente, registros=registros, actual=actual,
            modulo=modulo, reactivos=reactivos, escala=escala, registro_id=registro_id, error=error,
            tramos=tramos, mision_elegida=mision_elegida,
            disponible=disponible if en_espera else None,
            ia_disponible=ia_disponible, formulario=request.form,
            actualizar_archivo=actual is not None and request.args.get("actualizar_archivo") == "1",
        )
        if espera_rechazada:
            segundos = max(1, ceil((disponible - datetime.now(timezone.utc)).total_seconds()))
            return pagina, 429, {"Retry-After": str(segundos)}
        return pagina

    @app.route("/psicologia/chat", methods=["GET", "POST"])
    def chat_psicologico():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        usuario = session["user_id"]
        revision, mensajes = almacen.psych_chat(database, usuario)
        ia_disponible = bool(os.getenv("GEMINI_API_KEY", "").strip())
        texto = request.form.get("mensaje", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("revision") != str(revision):
                error = "La conversación se actualizó. Revisa los mensajes y vuelve a enviarlo."
            elif not 1 <= len(texto) <= 2000:
                error = "Escribe un mensaje de hasta 2000 caracteres."
            elif not ia_disponible:
                error = "La IA aún no está configurada en el servidor."
            else:
                actualizados = [*mensajes, {"role": "user", "text": texto}]
                try:
                    respuesta = responder_chat_psicologico(actualizados)
                except ERRORES_GEMINI:
                    error = "La IA no pudo responder. Tu mensaje se conserva en el campo para reintentar."
                else:
                    actualizados.append({"role": "ai", "text": respuesta})
                    if almacen.save_psych_chat(database, usuario, revision, actualizados):
                        return redirect(url_for("chat_psicologico", _anchor="ultimo-mensaje"), 303)
                    revision, mensajes = almacen.psych_chat(database, usuario)
                    error = "La conversación se actualizó en otra pestaña. Revisa los mensajes antes de reenviar."
        return render_template(
            "chat-psicologico.html", expediente=expediente, modulo="chat", mensajes=mensajes,
            revision=revision, texto=texto, error=error, ia_disponible=ia_disponible,
        )

    @app.route("/chequeo.html", methods=["GET", "POST"])
    def checkup():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        if not os.getenv("GEMINI_API_KEY", "").strip():
            return render_template("chequeo.html", expediente=expediente, bloqueado="La IA aún no está configurada en el servidor.")

        usuario, astronauta = session["user_id"], expediente["_id"]
        draft = almacen.get_open_checkup(database, usuario, astronauta)
        if request.method == "POST" and request.form.get("iniciar") == "1":
            if draft is None:
                try:
                    pregunta = generar_pregunta({"mensajes": []})
                except ERRORES_GEMINI:
                    return render_template("chequeo.html", expediente=expediente, bloqueado=MENSAJE_GEMINI), 503
                almacen.open_checkup(database, usuario, astronauta, {"role": "ai", "text": pregunta})
            return redirect(url_for("checkup"), 303)
        if draft is None:
            return redirect(url_for("profile"), 303)

        messages = json.loads(draft["messages"])
        datos_guardados = json.loads(draft["details"] or "{}")
        vitals = {
            key: datos_guardados.get("telemetria", {}).get(key, draft[key] if draft["revision"] else None)
            for key in ("hr", "spo2", "temp")
        }
        details = datos_guardados
        answer = request.form.get("answer", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("turn") != f"{draft['id']}:{draft['revision']}":
                return redirect(url_for("checkup"), 303)
            accion = request.form.get("accion", "enviar")
            if accion not in {"enviar", "finalizar"}:
                abort(400)
            vitals = {key: request.form.get(key, "").strip() for key in vitals}
            details = {campo: request.form.get(campo, "").strip() for campo in ("mision_id", "fase", "motivo", "actividad")}
            misiones = {mision["id"] for mision in expediente["misiones"]}
            medidas = {}
            try:
                for key, convertir, minimo, maximo in (
                    ("hr", int, 1, 999), ("spo2", int, 0, 100), ("temp", float, 0.1, 99.9),
                ):
                    valor = convertir(vitals[key]) if vitals[key] else None
                    if valor is not None and not minimo <= valor <= maximo:
                        raise ValueError
                    medidas[key] = valor
            except ValueError:
                error = "Revisa el formato y las unidades de las mediciones ingresadas."
            if ((details["mision_id"] and details["mision_id"] not in misiones)
                    or (details["fase"] and details["fase"] not in FASES)):
                error = "Selecciona una misión y una fase del expediente."
            if any(len(details[campo]) > 200 for campo in ("motivo", "actividad")):
                error = "El motivo y la actividad admiten hasta 200 caracteres."
            if len(answer) > 1000 or (accion == "enviar" and not answer):
                error = "Escribe una respuesta de hasta 1000 caracteres."
            if not error:
                updated = [*messages, {"role": "user", "text": answer}] if answer else messages
                status = None
                details["telemetria"] = medidas
                contexto = {
                    "telemetria": {etiqueta: medidas[key] for key, etiqueta in (
                        ("hr", "frecuencia_cardiaca_lpm"), ("spo2", "spo2_pct"), ("temp", "temperatura_c"),
                    ) if medidas[key] is not None},
                    "fase": details["fase"], "actividad": details["actividad"], "motivo": details["motivo"],
                }
                try:
                    conversacion, memoria = preparar_conversacion(updated, datos_guardados.get("memoria_ia"))
                    if accion == "finalizar":
                        evaluacion = evaluar_chequeo(conversacion, contexto)
                        status = evaluacion["estado"]
                        details["evaluacion_ia"] = evaluacion
                    else:
                        pregunta = generar_pregunta(conversacion, contexto)
                        updated.append({"role": "ai", "text": pregunta})
                        if memoria:
                            details["memoria_ia"] = memoria
                except ERRORES_GEMINI:
                    error = MENSAJE_GEMINI
                if not error:
                    valores_sql = tuple(medidas[key] if medidas[key] is not None else 0 for key in ("hr", "spo2", "temp"))
                    saved = almacen.save_turn(database, draft, updated, valores_sql, details, status)
                    if saved and status:
                        sincronizar_archivo_expediente(usuario)
                        return redirect(url_for("summary", registro=f"app-{draft['id']}", actualizar_archivo=1), 303)
                    return redirect(url_for("checkup"), 303)
        return render_template(
            "chequeo.html", messages=messages, vitals=vitals, draft=draft, answer=answer, error=error,
            expediente=expediente, details=details,
        )

    @app.get("/expediente.json")
    def download_expediente():
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("index"))
        archivo = actualizar_archivo_expediente(user_id)
        if archivo is None:
            return redirect(url_for("index"))
        filename, contenido = archivo
        return Response(
            contenido,
            content_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/resumen.html")
    def summary():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        view = request.args.get("vista", "resultados")
        if view not in {"resultados", "alertas", "historial", "estadisticas"}:
            return redirect(url_for("summary"))
        records = registros_clinicos(database, session["user_id"], expediente, almacen)
        clave = request.args.get("registro")
        latest = next((registro for registro in records if registro["clave"] == clave), None) if clave else (records[0] if records else None)
        if clave and latest is None:
            abort(404)
        estadisticas, mediciones_historicas = estadisticas_monitoreo(records) if view == "estadisticas" else ({}, [])
        return render_template(
            "resumen.html", view=view, latest=latest, records=records, expediente=expediente,
            estadisticas=estadisticas, mediciones_historicas=mediciones_historicas,
            actualizar_archivo=view == "resultados" and request.args.get("actualizar_archivo") == "1",
        )

    return app


if __name__ == "__main__":
    create_app().run()
