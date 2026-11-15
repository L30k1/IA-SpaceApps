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
from historial_formulario import SECCIONES, ajustar_filas, filas_formulario, generar_historial
from idioma import fecha_corta, idioma_actual, idioma_elegido, traducir as t
from asistente import evaluar_chequeo, generar_pregunta, preparar_conversacion, texto_respuesta
from calendario_mision import ZONA_MISION, calendario, fechas_mision, resumir_ejercicio, rutina_mision
from database.expedientes import (
    CAMPO_PRAXIS, FASES, LIMITES_CAPTURA, OBJETIVOS_PRAXIS, SIGNOS, fecha_utc, leer_expediente, registro_lot,
    registro_ejercicio, registro_emociones, registro_f2b, registro_praxis,
)
from ejercicio import CAMPO_EJERCICIO, CONTEXTOS_FC, CONTEXTOS_FC_EJERCICIO, TIPOS_EJERCICIO
from editar_expediente import (
    GRUPOS_EDITABLES, SECCIONES_EDICION, EdicionDesactualizada, aplicar_edicion, filas_mision, formulario_edicion,
    version_edicion,
)
from emociones import CAMPO_EMOCIONES, EMOCIONES, EXPOSICION_EMOCIONES_MS, INTENSIDADES, LAMINAS, estimulos_emociones
from emergencia import responder_emergencia
from f2b import CAMPO_F2B, COINCIDENCIAS_F2B, EXPOSICION_F2B_MS, ESTIMULOS_F2B, secuencia_f2b
from lot import ANGULOS_LOT, CAMPO_LOT, ENSAYOS_LOT, OPCIONES_LOT, pares_lot
from llave_edicion import CAMPO_LLAVE, llave_del_expediente, preparar_llave, verificar_credencial
from psicologia import (
    INTERVALOS, MODULOS, VERSION, leer_pvt, leer_respuestas, puntuar, responder_chat_psicologico, seguimiento_psicologico,
    tramo_mision, validar_registros,
)
from volt import CAMPO_VOLT, ESPERA, EXPOSICION, FIGURAS, estimulos
from voz_ia import ErrorElevenLabs, MENSAJES_ELEVENLABS, configuracion_elevenlabs, sintetizar_elevenlabs


ROOT = Path(__file__).resolve().parent
MODOS_ACCESO = {"login", "register"}
PRUEBAS_JSON = {"pruebas_cognitivas", "prueba_volt", "prueba_lot", "prueba_f2b", "prueba_emociones"}
ETIQUETAS_RESULTADO = {
    "ALERTA": "Revisión prioritaria sugerida",
    "ESTABLE": "Sin prioridad adicional sugerida",
    "INDETERMINADO": "Información por aclarar",
}
ERRORES_GEMINI = (APIError, httpx2.HTTPError, ValueError)
MENSAJE_GEMINI = "La IA no devolvió una respuesta válida. Vuelve a intentarlo."
MEDICIONES_MONITOREO = {
    "hr": ("frecuencia_cardiaca", "frecuencia_cardiaca_lpm", int),
    "spo2": ("spo2", "spo2_pct", int),
    "temp": ("temperatura", "temperatura_c", float),
}
SECCIONES_ADMIN = {
    "expediente": "Expediente",
    "monitoreos": "Monitoreos",
    "psicologia": "Formularios psicológicos",
    "cognicion": "Pruebas cognitivas",
    "ejercicio": "Ejercicio",
    "chats": "Conversaciones",
}
GRUPOS_ADMIN = {
    "psicologia": (("diario_psicologico", "Diario"), ("semanal_psicologico", "Semanal")),
    "cognicion": (
        (CAMPO_PRAXIS, "Praxis Motora (PM)"), (CAMPO_VOLT, "Aprendizaje visual de objetos (VOLT)"),
        (CAMPO_LOT, "Orientación de línea (LOT)"), (CAMPO_F2B, "Fractal 2-Back (F2B)"),
        (CAMPO_EMOCIONES, "Reconocimiento facial de emociones"),
    ),
    "ejercicio": ((CAMPO_EJERCICIO, "Sesiones de ejercicio"),),
}


def comparar_referencias(medidas, referencias):
    comparacion = {}
    for clave, (tipo, _, _) in MEDICIONES_MONITOREO.items():
        valor, rango = medidas.get(clave), referencias.get(tipo)
        if valor is None or not rango:
            continue
        minimo, maximo = rango["minimo"], rango["maximo"]
        posicion = "inferior" if valor < minimo else "superior" if valor > maximo else "dentro"
        comparacion[tipo] = {**rango, "valor": valor, "unidad": SIGNOS[tipo][1], "posicion": posicion}
    return comparacion


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


def solicitud_json_emergencia():
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
    app.add_template_filter(fecha_corta, "fecha_corta")

    @app.template_filter("respuesta_ia")
    def mostrar_respuesta_ia(valor):
        try:
            return texto_respuesta(valor)
        except ValueError:
            return t("Esta respuesta anterior no está disponible en un formato legible.")
    uri_mongo = os.getenv("MONGODB_URI", "").strip() if database is None else ""
    if uri_mongo:
        import db_mongo as almacen

        database = almacen.conectar(uri_mongo, os.getenv("MONGODB_DB", "").strip() or "medispace")
        archivos_expedientes = None
        conflicto_cuenta = almacen.ConflictoCuenta

        @app.errorhandler(almacen.ErrorBase)
        def base_no_disponible(_error):
            mensaje = "No se pudo confirmar la operación en la base de datos. Revisa tu historial antes de reintentar."
            if request.method == "POST" and (
                request.endpoint in PRUEBAS_JSON or solicitud_json_emergencia()
            ):
                return {"error": t(mensaje)}, 503
            return t(mensaje), 503
    else:
        almacen = db
        database = database or os.getenv("MEDISPACE_DATABASE") or ROOT / "medispace.sqlite3"
        archivos_expedientes = Path(f"{database}.expedientes")
        conflicto_cuenta = sqlite3.IntegrityError
        db.initialize(database)

    @app.template_filter("hora_utc")
    def hora_utc(fecha):
        fecha = fecha_utc(fecha)
        return f"{fecha_corta(fecha)} {fecha:%H:%M} UTC"

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
            "index", "preparar_historial", "profile", "checkup", "summary", "registro_psicologico",
            "chat_psicologico", "historial_cognitivo",
            "download_expediente", "logout", "ejercicio", "editar_expediente", "audio_elevenlabs",
            "admin_cuentas", "admin_cuenta",
        } or request.endpoint in PRUEBAS_JSON:
            response.cache_control.no_store = True
            response.headers["Content-Language"] = idioma_actual()
            if idioma_elegido():
                response.set_cookie("medispace_lang", idioma_elegido(), max_age=31536000,
                                    httponly=True, secure=request.is_secure, samesite="Lax")
        if request.endpoint in {"admin_cuentas", "admin_cuenta"}:
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    def url_idioma(codigo):
        query = request.args.to_dict(flat=False)
        query["lang"] = [codigo]
        return f"{url_for(request.endpoint, **(request.view_args or {}))}?{urlencode(query, doseq=True)}"

    @app.context_processor
    def page_context():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return {
            "utc_clock": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "csrf": session["csrf"],
            "fases": {clave: t(etiqueta) for clave, etiqueta in FASES.items()},
            "signos": SIGNOS,
            "contextos_fc": CONTEXTOS_FC,
            "limites_captura": LIMITES_CAPTURA,
            "etiquetas_resultado": {clave: t(etiqueta) for clave, etiqueta in ETIQUETAS_RESULTADO.items()},
            "idioma": idioma_actual(),
            "elevenlabs_disponible": configuracion_elevenlabs() is not None,
            "url_idioma": url_idioma,
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
                if request.endpoint == "audio_elevenlabs":
                    return {"error": t("Recarga el chat para renovar la sesión de voz.")}, 403
                if request.endpoint in PRUEBAS_JSON:
                    return {"error": t("La sesión cambió o caducó. Vuelve a iniciar sesión para guardar otra ronda.")}, 403
                if request.endpoint == "chat_psicologico" and request.args.get("modo") == "emergencia":
                    if solicitud_json_emergencia():
                        return {"error": t("La sesión cambió o caducó. Vuelve a abrir el chat.")}, 403
                    flash("El formulario caducó. Vuelve a completar el paso.")
                    return redirect(url_for("chat_psicologico", modo="emergencia"), 303)
                if request.endpoint == "preparar_historial" and request.accept_mimetypes.best == "application/json":
                    return {"error": t("El formulario caducó. Vuelve a completar el paso.")}, 403
                flash("El formulario caducó. Vuelve a completar el paso.")
                if request.endpoint == "preparar_historial":
                    return redirect(url_for("preparar_historial"), 303)
                if request.endpoint in {
                    "checkup", "registro_psicologico", "chat_psicologico", "ejercicio", "editar_expediente",
                } and expediente_actual():
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
                    clave_hash = llave_del_expediente(expediente)
                    user_id = almacen.create_user(database, generate_password_hash(password), expediente, clave_hash)
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

    @app.route("/historial-medico/nuevo", methods=["GET", "POST"])
    def preparar_historial():
        formulario = request.form
        filas = filas_formulario(formulario)
        error = None
        if request.method == "GET":
            filas = {grupo: [{}] for grupo in filas}
        else:
            accion = formulario.get("accion", "descargar")
            if accion == "descargar":
                try:
                    expediente = generar_historial(formulario, filas)
                    expediente[CAMPO_LLAVE] = preparar_llave(formulario)
                except ValueError as exc:
                    error = str(exc)
                    if request.accept_mimetypes.best == "application/json":
                        return {"error": t(error)}, 400
                else:
                    identificador = secure_filename(expediente["_id"])[:80]
                    nombre = f"expediente-{identificador}.json" if identificador else "expediente.json"
                    contenido = json.dumps(expediente, ensure_ascii=False, indent=2) + "\n"
                    return Response(contenido, mimetype="application/json", headers={
                        "Content-Disposition": f'attachment; filename="{nombre}"',
                        "Cache-Control": "no-store",
                    })
            elif not ajustar_filas(filas, accion):
                abort(400)
        return render_template("historial-formulario.html", formulario=formulario, filas=filas, secciones=SECCIONES, error=error)

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
            es_admin=almacen.es_administrador(database, session["user_id"]),
        )

    def comprobar_acceso_admin():
        usuario = session.get("user_id")
        if usuario is None:
            return redirect(url_for("index"))
        if not almacen.es_administrador(database, usuario):
            abort(403)
        return None

    @app.get("/admin")
    def admin_cuentas():
        acceso = comprobar_acceso_admin()
        if acceso is not None:
            return acceso
        identificador = request.args.get("astronauta_id", "").strip()
        pagina = request.args.get("pagina", 1, type=int)
        if not 1 <= pagina <= 1000000:
            abort(404)
        limite = 25
        cuentas = almacen.cuentas_administracion(database, identificador, (pagina - 1) * limite, limite + 1)
        return render_template(
            "admin.html", cuentas=cuentas[:limite], siguiente=len(cuentas) > limite,
            pagina=pagina, identificador=identificador,
        )

    @app.get("/admin/cuentas/<user_id>")
    def admin_cuenta(user_id):
        acceso = comprobar_acceso_admin()
        if acceso is not None:
            return acceso
        seccion = request.args.get("seccion", "expediente")
        if seccion not in SECCIONES_ADMIN:
            abort(404)
        cuenta = almacen.cuenta_administracion(database, user_id)
        if cuenta is None:
            abort(404)

        usuario = cuenta["id"]
        expediente = cuenta.get("expediente") or {}
        grupos = []
        if seccion == "expediente" and expediente:
            apartados = {"chequeos", *(campo for campos in GRUPOS_ADMIN.values() for campo, _ in campos)}
            grupos = [("Historial médico", {k: v for k, v in expediente.items() if k not in apartados})]
        elif seccion == "monitoreos" and expediente:
            filas = almacen.history(database, usuario, expediente["_id"])
            grupos = [("Monitoreos guardados", [registro for _, registro in historial_expediente(expediente, filas)])]
            borrador = almacen.get_open_checkup(database, usuario, expediente["_id"])
            if borrador:
                detalle = json.loads(borrador["details"] or "{}")
                grupos.append(("Monitoreo en curso", {**detalle, "conversacion": json.loads(borrador["messages"])}))
        elif seccion in GRUPOS_ADMIN:
            grupos = [(etiqueta, expediente.get(campo, [])) for campo, etiqueta in GRUPOS_ADMIN[seccion]]
            if seccion == "cognicion":
                borrador = almacen.volt_draft(database, usuario)
                if borrador:
                    grupos.append(("VOLT en curso", borrador))
        elif seccion == "chats":
            grupos = [
                ("Chat de apoyo (incluye el archivo)", almacen.psych_chat(database, usuario, incluir_archivo=True)[1]),
                ("Emergencia por voz", almacen.psych_chat(database, usuario, emergencia=True)[1]),
            ]
        return render_template(
            "admin.html", cuenta=cuenta, seccion=seccion, secciones=SECCIONES_ADMIN, grupos=grupos,
        )

    @app.route("/ejercicio", methods=["GET", "POST"])
    def ejercicio():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))

        ahora = datetime.now(ZONA_MISION)
        fecha_local = ahora.strftime("%Y-%m-%dT%H:%M")
        misiones = {m["id"]: fechas for m in expediente["misiones"] if (fechas := fechas_mision(m))}
        seleccionada = request.args.get("mision", "")
        if not seleccionada:
            vigentes = [clave for clave, (inicio, fin) in misiones.items() if inicio <= ahora.date() <= fin]
            if len(vigentes) == 1:
                seleccionada = vigentes[0]
        campos = ("fecha_hora", "tipo", "duracion_min", "equipo", "esfuerzo", "recuperacion", "mision_id")
        formulario = {"fecha_hora": fecha_local, "mision_id": seleccionada if seleccionada in misiones else ""}
        identificador = uuid4().hex
        error = None
        if request.method == "POST":
            formulario = {campo: request.form.get(campo, "").strip() for campo in campos}
            identificador = request.form.get("registro_id", "")
            try:
                fecha = datetime.strptime(formulario["fecha_hora"], "%Y-%m-%dT%H:%M")
                if fecha > ahora.replace(tzinfo=None):
                    raise ValueError
            except ValueError:
                error = "Ingresa la fecha y hora local de una sesión realizada."
            mision_id = formulario["mision_id"]
            if error is None:
                candidatas = [clave for clave, (inicio, fin) in misiones.items() if inicio <= fecha.date() <= fin]
                if mision_id and mision_id not in candidatas:
                    error = "La fecha de la sesión debe estar dentro de la misión seleccionada."
                elif not mision_id and len(candidatas) == 1:
                    mision_id = candidatas[0]
                elif not mision_id and len(candidatas) > 1:
                    error = "Selecciona la misión para que esta sesión cuente en su rutina."
            if error is None:
                datos = {**formulario, "mision_id": mision_id}
                for campo in ("duracion_min", "esfuerzo"):
                    try:
                        datos[campo] = int(formulario[campo]) if formulario[campo] else None
                    except ValueError:
                        pass
                try:
                    registro = registro_ejercicio(identificador, fecha.replace(tzinfo=ZONA_MISION).isoformat(), datos)
                except ValueError as exc:
                    error = str(exc)
                else:
                    usuario = session["user_id"]
                    if almacen.save_expediente_report(database, usuario, CAMPO_EJERCICIO, registro, *campos):
                        sincronizar_archivo_expediente(usuario)
                        flash("Sesión de ejercicio guardada.")
                        return redirect(url_for("ejercicio", mision=mision_id or None, actualizar_archivo=1), 303)
                    error = "Esta sesión ya existe con otros datos. Vuelve a abrir el registro."

        registros = sorted(expediente.get(CAMPO_EJERCICIO, []), key=lambda r: r["fecha_hora"], reverse=True)
        mision_seleccionada = formulario["mision_id"]
        rutina = None
        if mision_seleccionada in misiones:
            mision = next(m for m in expediente["misiones"] if m["id"] == mision_seleccionada)
            rutina = rutina_mision(mision, *misiones[mision_seleccionada], ahora.date(),
                                   resumir_ejercicio(registros, misiones, ahora))
        inicio = ahora.date() - timedelta(days=6)
        semana = [r for r in registros if inicio <= fecha_utc(r["fecha_hora"]).astimezone(ZONA_MISION).date() <= ahora.date()]
        minutos = {}
        esfuerzos = {}
        for registro in semana:
            tipo = registro["tipo"]
            minutos[tipo] = minutos.get(tipo, 0) + registro["duracion_min"]
            if registro["equipo"] and registro["esfuerzo"] is not None:
                clave = tipo, registro["equipo"].casefold()
                esfuerzos.setdefault(clave, []).append(registro)
        graficas = [
            serie_estadistica(
                t(TIPOS_EJERCICIO[tipo]) + " · " + grupo[0]["equipo"],
                "/ 10", [(r["fecha_hora"], r["esfuerzo"]) for r in grupo],
            )
            for (tipo, _), grupo in esfuerzos.items() if len(grupo) > 1
        ]
        return render_template(
            "ejercicio.html", expediente=expediente, error=error, formulario=formulario,
            tipos=TIPOS_EJERCICIO, misiones=misiones, fecha_maxima=fecha_local, registro_id=identificador, registros=registros,
            sesiones_semana=len(semana), minutos=minutos, graficas=graficas,
            rutina=rutina, mision_seleccionada=mision_seleccionada,
            actualizar_archivo=request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion", methods=["GET", "POST"])
    def pruebas_cognitivas():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": t("Inicia sesión para guardar los resultados.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            try:
                tiempos = json.loads(request.form.get("tiempos_ms", ""))
            except (ValueError, RecursionError):
                return {"error": t("No se pudieron leer los tiempos de la ronda.")}, 400
            try:
                registro = registro_praxis(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), tiempos)
            except ValueError as exc:
                return {"error": t(str(exc))}, 400
            usuario = session["user_id"]
            if not almacen.save_expediente_report(database, usuario, CAMPO_PRAXIS, registro, "tiempos_ms"):
                return {"error": t("Ya existe un resultado diferente con el identificador de esta ronda.")}, 409
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
                    return {"error": t(str(exc))}, 400
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

    def guardar_ronda(campo, crear_registro, campo_respuestas, ancla):
        try:
            respuestas = json.loads(request.form.get("respuestas", ""))
        except (ValueError, RecursionError):
            return {"error": t("No se pudieron leer las respuestas de la ronda.")}, 400
        try:
            registro = crear_registro(request.form.get("registro_id"), datetime.now(timezone.utc).isoformat(), respuestas)
        except ValueError as exc:
            return {"error": t(str(exc))}, 400
        usuario = session["user_id"]
        if not almacen.save_expediente_report(database, usuario, campo, registro, campo_respuestas):
            return {"error": t("Ya existe un resultado diferente con el identificador de esta ronda.")}, 409
        sincronizar_archivo_expediente(usuario)
        return {"url": url_for(request.endpoint, registro=registro["id"], actualizar_archivo=1, _anchor=ancla)}

    @app.route("/cognicion/lot", methods=["GET", "POST"])
    def prueba_lot():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": t("Inicia sesión para guardar los resultados.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return guardar_ronda(CAMPO_LOT, registro_lot, "respuestas", "lot-guardado")

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

    @app.route("/cognicion/f2b", methods=["GET", "POST"])
    def prueba_f2b():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": t("Inicia sesión para guardar los resultados.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return guardar_ronda(CAMPO_F2B, registro_f2b, "respuestas_ms", "f2b-guardado")

        seleccionado = request.args.get("registro")
        actual = next((r for r in expediente.get(CAMPO_F2B, []) if r["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        identificador = uuid4().hex
        return render_template(
            "f2b.html", expediente=expediente, registro_id=identificador, actual=actual,
            datos={"secuencia": secuencia_f2b(identificador), "exposicion_ms": EXPOSICION_F2B_MS},
            coincidencias=COINCIDENCIAS_F2B,
            actualizar_archivo=actual is not None and request.args.get("actualizar_archivo") == "1",
        )

    @app.route("/cognicion/emociones", methods=["GET", "POST"])
    def prueba_emociones():
        expediente = expediente_actual()
        if expediente is None:
            if request.method == "POST":
                return {"error": t("Inicia sesión para guardar los resultados.")}, 401
            return redirect(url_for("index"))
        if request.method == "POST":
            return guardar_ronda(CAMPO_EMOCIONES, registro_emociones, "respuestas", "emociones-guardado")

        seleccionado = request.args.get("registro")
        actual = next((r for r in expediente.get(CAMPO_EMOCIONES, []) if r["id"] == seleccionado), None)
        if seleccionado and actual is None:
            abort(404)
        identificador = uuid4().hex
        ensayos = estimulos_emociones(identificador)
        datos = {
            "laminas": {lamina: url_for("lamina_emociones", nombre=lamina) for lamina in LAMINAS},
            "ensayos": [{"lamina": e["lamina"], "casilla": e["casilla"]} for e in ensayos],
            "exposicion_ms": EXPOSICION_EMOCIONES_MS,
        }
        return render_template(
            "emociones.html", expediente=expediente, registro_id=identificador, datos=datos,
            emociones=EMOCIONES, intensidades=INTENSIDADES, actual=actual,
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
            (CAMPO_F2B, "Fractal 2-Back (F2B)", "prueba_f2b", "f2b-guardado", (
                ("Coincidencias detectadas", "aciertos", itemgetter("aciertos")),
                ("Falsas alarmas", "respuestas", itemgetter("falsas_alarmas")),
                ("Mediana de reacción en aciertos", "ms", itemgetter("mediana_aciertos_ms")),
            )),
            (CAMPO_EMOCIONES, "Reconocimiento facial (ERT)", "prueba_emociones", "emociones-guardado", (
                ("Precisión", "%", itemgetter("precision_pct")),
                ("Mediana de reacción en aciertos", "ms", itemgetter("mediana_aciertos_ms")),
            )),
        )
        historial = []
        for campo, nombre, destino, ancla, metricas in pruebas:
            registros = sorted(expediente.get(campo, []), key=lambda r: fecha_utc(r["fecha_hora"]), reverse=True)
            series = []
            for etiqueta, unidad, valor in metricas:
                lecturas = [(r["fecha_hora"], dato) for r in registros if (dato := valor(r)) is not None]
                if lecturas:
                    series.append(serie_estadistica(etiqueta, unidad, lecturas))
            historial.append({"nombre": nombre, "destino": destino, "ancla": ancla, "registros": registros, "series": series})
        return render_template("historial-cognitivo.html", historial=historial)

    @app.get("/assets/marca/<nombre>")
    def imagen_marca(nombre):
        return send_from_directory(ROOT / "static" / "marca", nombre)

    @app.get("/assets/emociones/<nombre>")
    def lamina_emociones(nombre):
        return send_from_directory(ROOT / "static" / "emociones", nombre)

    @app.get("/assets/reconocimiento-emociones.js")
    def emociones_script():
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

    @app.get("/assets/praxis-motora.js")
    def praxis_motora_script():
        return send_from_directory(ROOT / "static", "praxis-motora.js")

    @app.get("/assets/voz-chat.js")
    def voz_chat_script():
        return send_from_directory(ROOT / "static", "voz-chat.js")

    @app.get("/assets/chat-ui.js")
    def chat_ui_script():
        return send_from_directory(ROOT / "static", "chat-ui.js")

    @app.get("/assets/audio-ia.js")
    def audio_ia_script():
        return send_from_directory(ROOT / "static", "audio-ia.js")

    @app.post("/voz/elevenlabs")
    def audio_elevenlabs():
        expediente = expediente_actual()
        if expediente is None:
            return {"error": t("Vuelve a iniciar sesión para escuchar la respuesta.")}, 401
        configuracion = configuracion_elevenlabs()
        if configuracion is None:
            return {"error": t("ElevenLabs necesita una clave y un Voice ID en Render.")}, 503
        canal = request.form.get("canal")
        if request.form.get("usar_nube") != "1" or canal not in {"medico", "psicologico", "emergencia"}:
            return "", 400
        usuario = session["user_id"]
        if canal in {"psicologico", "emergencia"}:
            _, mensajes = almacen.psych_chat(database, usuario, emergencia=canal == "emergencia")
        else:
            borrador = almacen.get_open_checkup(database, usuario, expediente["_id"])
            mensajes = json.loads(borrador["messages"]) if borrador else []
        ultimo = next((turno["text"] for turno in reversed(mensajes) if turno["role"] == "ai"), None)
        try:
            texto = texto_respuesta(ultimo).replace("\r\n", "\n").replace("\r", "\n")
        except ValueError:
            return "", 404
        if request.form.get("texto") != texto:
            return {"error": t("La respuesta más reciente cambió. Recarga el chat para escucharla.")}, 409
        try:
            audio = sintetizar_elevenlabs(texto, configuracion)
        except ErrorElevenLabs as exc:
            app.logger.warning("Voz ElevenLabs %s, HTTP del proveedor: %s", exc.codigo, exc.estado_http or "-")
            return {"error": t(MENSAJES_ELEVENLABS[exc.codigo]), "codigo": exc.codigo}, 502
        return Response(audio, mimetype="audio/mpeg")

    @app.get("/assets/idioma.js")
    def idioma_script():
        return send_from_directory(ROOT / "static", "idioma.js")

    @app.get("/assets/voz-emergencia.js")
    def voz_emergencia_script():
        return send_from_directory(ROOT / "static", "voz-emergencia.js")

    @app.get("/assets/expediente-local.js")
    def expediente_local_script():
        return send_from_directory(ROOT / "static", "expediente-local.js")

    @app.get("/assets/crear-historial.js")
    def crear_historial_script():
        return send_from_directory(ROOT / "static", "crear-historial.js")

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
            mision["id"]: tramo_mision(mision, ahora.astimezone(ZONA_MISION).date()) for mision in expediente["misiones"]
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
        emergencia = request.args.get("modo") == "emergencia"
        modo = "emergencia" if emergencia else None
        quiere_json = solicitud_json_emergencia()
        expediente = expediente_actual()
        if expediente is None:
            if quiere_json:
                return {"error": t("Vuelve a iniciar sesión para conversar con la IA.")}, 401
            return redirect(url_for("index"))
        usuario = session["user_id"]
        revision, mensajes = almacen.psych_chat(database, usuario, emergencia=emergencia)
        ia_disponible = bool(os.getenv("GEMINI_API_KEY", "").strip())
        texto = request.form.get("mensaje", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("accion") == "limpiar":
                if emergencia:
                    abort(400)
                if request.form.get("revision") == str(revision) and mensajes and almacen.limpiar_psych_chat(database, usuario, revision):
                    flash("Conversación limpiada. El historial quedó guardado.")
                else:
                    flash("La conversación cambió. Revisa los mensajes antes de limpiar el chat.")
                return redirect(url_for("chat_psicologico"), 303)
            if request.form.get("revision") != str(revision):
                error = "La conversación se actualizó. Revisa los mensajes y vuelve a enviarlo."
                estado = 409
            elif not 1 <= len(texto) <= 2000:
                error = "Escribe un mensaje de hasta 2000 caracteres."
                estado = 400
            elif not ia_disponible:
                error = "La IA aún no está configurada en el servidor."
                estado = 503
            else:
                actualizados = [*mensajes, {"role": "user", "text": texto}]
                try:
                    responder = responder_emergencia if emergencia else responder_chat_psicologico
                    respuesta = responder(actualizados)
                except ERRORES_GEMINI:
                    error = "La IA no pudo responder. Tu mensaje se conserva en el campo para reintentar."
                    estado = 503
                else:
                    nuevo_turno = [actualizados[-1], {"role": "ai", "text": respuesta}]
                    if almacen.save_psych_chat(database, usuario, revision, nuevo_turno, emergencia=emergencia):
                        if quiere_json:
                            return {"revision": revision + 1, "mensajes": nuevo_turno}
                        if request.headers.get("X-MediSpace-Chat") != "1":
                            return redirect(url_for("chat_psicologico", modo=modo, _anchor="ultimo-mensaje"), 303)
                        revision += 1
                        mensajes = [*mensajes, *nuevo_turno]
                        texto = ""
                    else:
                        revision, mensajes = almacen.psych_chat(database, usuario, emergencia=emergencia)
                        error = "La conversación se actualizó en otra pestaña. Revisa los mensajes antes de reenviar."
                        estado = 409
            if quiere_json:
                if estado == 409:
                    error = "La conversación cambió en otra pestaña. Copia tu mensaje y vuelve a abrir el chat para enviarlo."
                return {"error": t(error)}, estado
        return render_template(
            "chat-psicologico.html", expediente=expediente, modulo="chat", mensajes=mensajes,
            revision=revision, texto=texto, error=error, ia_disponible=ia_disponible, emergencia=emergencia,
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
        if request.method == "GET" and draft["revision"] == 0 and not details:
            hoy = datetime.now(ZONA_MISION).date()
            en_curso = [mision["id"] for mision in expediente["misiones"]
                        if (fechas := fechas_mision(mision)) and fechas[0] <= hoy <= fechas[1]]
            if len(en_curso) == 1:
                details = {"mision_id": en_curso[0], "fase": "vuelo"}
        answer = request.form.get("answer", "").strip()
        error = None
        if request.method == "POST":
            if request.form.get("turn") != f"{draft['id']}:{draft['revision']}":
                return redirect(url_for("checkup"), 303)
            accion = request.form.get("accion", "enviar")
            if accion not in {"enviar", "finalizar"}:
                abort(400)
            vitals = {key: request.form.get(key, "").strip() for key in vitals}
            details = {campo: request.form.get(campo, "").strip()
                       for campo in ("mision_id", "fase", "motivo", "actividad", "contexto_fc")}
            misiones = {mision["id"] for mision in expediente["misiones"]}
            medidas = {}
            try:
                for key, (tipo, _, convertir) in MEDICIONES_MONITOREO.items():
                    minimo, maximo = LIMITES_CAPTURA[tipo]
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
            if details["contexto_fc"] and details["contexto_fc"] not in CONTEXTOS_FC:
                error = "Selecciona un contexto válido para la frecuencia cardíaca."
            if len(answer) > 1000 or (accion == "enviar" and not answer):
                error = "Escribe una respuesta de hasta 1000 caracteres."
            if not error:
                updated = [*messages, {"role": "user", "text": answer}] if answer else messages
                status = None
                details["telemetria"] = medidas
                contexto = {
                    "telemetria": {etiqueta: medidas[key] for key, (_, etiqueta, _) in MEDICIONES_MONITOREO.items()
                                   if medidas[key] is not None},
                    "fase": details["fase"], "actividad": details["actividad"], "motivo": details["motivo"],
                }
                comparacion = comparar_referencias(medidas, expediente.get("referencias_monitoreo", {}))
                if medidas["hr"] is not None and details["contexto_fc"]:
                    contexto["contexto_fc"] = details["contexto_fc"]
                    if details["contexto_fc"] in CONTEXTOS_FC_EJERCICIO:
                        comparacion.pop("frecuencia_cardiaca", None)
                else:
                    details.pop("contexto_fc")
                if comparacion:
                    contexto["comparacion_referencias"] = comparacion
                try:
                    conversacion, memoria = preparar_conversacion(updated, datos_guardados.get("memoria_ia"))
                    if accion == "finalizar":
                        evaluacion = evaluar_chequeo(conversacion, contexto)
                        status = evaluacion["estado"]
                        details["evaluacion_ia"] = evaluacion
                        if comparacion:
                            details["comparacion_referencias"] = comparacion
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
                    if not saved or request.headers.get("X-MediSpace-Chat") != "1":
                        return redirect(url_for("checkup"), 303)
                    draft = {**draft, "revision": draft["revision"] + 1}
                    messages, vitals, answer = updated, medidas, ""
        return render_template(
            "chequeo.html", messages=messages, vitals=vitals, draft=draft, answer=answer, error=error,
            expediente=expediente, details=details,
        )

    @app.route("/expediente/editar", methods=["GET", "POST"])
    def editar_expediente():
        expediente = expediente_actual()
        if expediente is None:
            return redirect(url_for("index"))
        usuario = session["user_id"]
        credenciales = almacen.credenciales_edicion(database, usuario)
        if credenciales is None:
            return redirect(url_for("index"))
        clave_guardada = credenciales["clave_edicion_hash"]
        accion = request.form.get("accion")
        autorizado = clave_guardada and session.get("editor_usuario") == usuario
        if autorizado and accion == "cerrar":
            session.pop("editor_usuario", None)
            return redirect(url_for("summary", vista="historial"), 303)
        if not autorizado:
            error = None
            if accion == "desbloquear":
                if verificar_credencial(clave_guardada, request.form.get("llave_edicion", "")):
                    session["editor_usuario"] = usuario
                    return redirect(url_for("editar_expediente"), 303)
                error = "La llave de edición es incorrecta."
            elif accion == "configurar" and not clave_guardada:
                if not verificar_credencial(credenciales["password_hash"], request.form.get("password", "")):
                    error = "La contraseña de la cuenta es incorrecta."
                else:
                    try:
                        clave_hash = preparar_llave(request.form)
                    except ValueError as exc:
                        error = str(exc)
                    else:
                        if almacen.configurar_llave_edicion(database, usuario, clave_hash):
                            session["editor_usuario"] = usuario
                        return redirect(url_for("editar_expediente"), 303)
            elif request.method == "POST":
                error = "Abre el editor con tu llave antes de guardar."
            return render_template("editar-expediente.html", configurar=not clave_guardada, error=error), (
                403 if error else 200
            )

        error = None
        estado = 200
        if request.method == "POST":
            formulario = request.form
            version = formulario.get("version", "")
            metas = formulario.getlist("misiones.ejercicio_min_diarios")
            filas = filas_formulario(formulario, editar=True)
            filas["misiones"] = filas_mision(expediente, metas)
            if accion == "guardar":
                try:
                    guardado = almacen.actualizar_datos_expediente(
                        database, usuario, lambda actual: aplicar_edicion(actual, version, formulario, filas, metas),
                    )
                except EdicionDesactualizada as exc:
                    error, estado = str(exc), 409
                except ValueError as exc:
                    error, estado = str(exc), 400
                else:
                    if not guardado:
                        return redirect(url_for("index"))
                    session.pop("editor_usuario", None)
                    sincronizar_archivo_expediente(usuario)
                    flash("Cambios del expediente guardados.")
                    return redirect(url_for("summary", vista="historial", actualizar_archivo=1), 303)
            elif not ajustar_filas({grupo: filas[grupo] for grupo in GRUPOS_EDITABLES}, accion or ""):
                abort(400)
        else:
            formulario, filas = formulario_edicion(expediente)
            version = version_edicion(expediente)
        return render_template(
            "historial-formulario.html", expediente=expediente, formulario=formulario, filas=filas,
            secciones=SECCIONES_EDICION, editar=True, version=version, error=error,
        ), estado

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
            actualizar_archivo=view in {"resultados", "historial"} and request.args.get("actualizar_archivo") == "1",
        )

    return app


if __name__ == "__main__":
    create_app().run()
