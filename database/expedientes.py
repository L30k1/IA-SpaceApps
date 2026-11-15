import json
import math
import re
from datetime import datetime, timezone

from volt import CAMPO_VOLT, ESPERA, VERSION_VOLT, estimulos, puntuar


GRUPOS = ("misiones", "alergias", "antecedentes", "medicamentos", "chequeos")
SIGNOS = {
    "frecuencia_cardiaca": ("FC", "lpm"),
    "spo2": ("SpO₂", "%"),
    "temperatura": ("Temperatura", "°C"),
}
FASES = {"preflight": "Prevuelo", "vuelo": "Vuelo", "posvuelo": "Posvuelo"}
CAMPO_PRAXIS = "praxis_motora"
OBJETIVOS_PRAXIS = 20


def texto_requerido(registro, campo):
    valor = registro.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"Completa el campo {campo} en el expediente.")
    return valor.strip()


def fecha_utc(fecha):
    try:
        valor = datetime.fromisoformat(fecha)
        if valor.utcoffset() is not None:
            return valor.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError("La fecha del chequeo debe incluir la zona horaria, por ejemplo 2026-11-14T21:30:00Z.")


def registro_praxis(identificador, fecha, tiempos):
    if not isinstance(identificador, str) or not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("El identificador de la ronda de Praxis Motora no es válido.")
    if not isinstance(tiempos, list) or len(tiempos) != OBJETIVOS_PRAXIS or any(
        type(tiempo) not in (int, float) or not 0 <= tiempo <= 2**53 - 1 for tiempo in tiempos
    ):
        raise ValueError(f"La ronda debe contener {OBJETIVOS_PRAXIS} tiempos válidos en milisegundos.")
    tiempos = [round(tiempo, 3) for tiempo in tiempos]
    return {
        "id": identificador,
        "fecha_hora": fecha_utc(fecha).isoformat(),
        "tiempos_ms": tiempos,
        "promedio_ms": round(sum(tiempos) / len(tiempos), 3),
        "mejor_ms": min(tiempos),
    }


def registros_volt(registros):
    if not isinstance(registros, list):
        raise ValueError("Memoria visual debe contener una lista de sesiones.")
    normalizados = []
    ids = set()
    for registro in registros:
        if not isinstance(registro, dict) or registro.get("version") != VERSION_VOLT:
            raise ValueError("La versión del registro de memoria visual no es válida.")
        identificador = registro.get("id")
        if not isinstance(identificador, str) or not re.fullmatch(r"[0-9a-f]{32}", identificador) or identificador in ids:
            raise ValueError("Los identificadores de memoria visual deben ser válidos y únicos.")
        intervalo = registro.get("intervalo_segundos")
        if type(intervalo) not in (int, float) or not ESPERA.total_seconds() <= intervalo <= 2**53 - 1:
            raise ValueError("El intervalo de memoria visual no es válido.")
        normalizado = {"id": identificador, "version": VERSION_VOLT, "intervalo_segundos": intervalo,
                       "fecha_hora": fecha_utc(registro.get("fecha_hora")).isoformat()}
        for fase, ensayos in zip(("inmediato", "diferido"), estimulos(identificador)[1:]):
            resultado = registro.get(fase)
            if not isinstance(resultado, dict):
                raise ValueError("El registro debe incluir ambas fases de reconocimiento.")
            normalizado[fase] = puntuar(resultado.get("respuestas"), ensayos)
        normalizados.append(normalizado)
        ids.add(identificador)
    return normalizados


def leer_expediente(contenido):
    try:
        expediente = json.loads(contenido)
    except (ValueError, RecursionError):
        raise ValueError("El archivo no contiene un JSON válido.") from None
    if not isinstance(expediente, dict) or not isinstance(expediente.get("astronauta"), dict):
        raise ValueError("El JSON debe contener los datos del astronauta.")

    expediente["_id"] = texto_requerido(expediente, "_id")
    astronauta = expediente["astronauta"]
    astronauta["nombre"] = texto_requerido(astronauta, "nombre")
    astronauta["rol"] = "Astronauta"
    for grupo in GRUPOS:
        registros = expediente.setdefault(grupo, [])
        if not isinstance(registros, list) or not all(isinstance(registro, dict) for registro in registros):
            raise ValueError(f"{grupo} debe ser una lista de registros.")
    for grupo, campo in (("misiones", "id"), ("alergias", "sustancia"),
                         ("antecedentes", "condicion"), ("medicamentos", "nombre")):
        for registro in expediente[grupo]:
            registro[campo] = texto_requerido(registro, campo)

    misiones = [mision["id"] for mision in expediente["misiones"]]
    identificadores = set()
    for chequeo in expediente["chequeos"]:
        chequeo["id"] = texto_requerido(chequeo, "id")
        if chequeo["id"] in identificadores:
            raise ValueError("Los identificadores de los chequeos deben ser únicos.")
        identificadores.add(chequeo["id"])
        chequeo["fecha_hora"] = fecha_utc(chequeo.get("fecha_hora")).isoformat()
        if chequeo.get("mision_id") is not None and chequeo["mision_id"] not in misiones:
            raise ValueError("La misión de cada chequeo debe figurar en el expediente.")
        if chequeo.get("fase") is not None and chequeo["fase"] not in list(FASES):
            raise ValueError("La fase debe ser preflight, vuelo o posvuelo.")
        evaluacion = chequeo.get("evaluacion")
        if evaluacion is not None and not isinstance(evaluacion, dict):
            raise ValueError("La evaluación debe ser un objeto JSON.")
        mediciones = chequeo.setdefault("mediciones", [])
        if not isinstance(mediciones, list) or not all(isinstance(m, dict) for m in mediciones):
            raise ValueError("Las mediciones deben ser una lista de registros.")
        for medicion in mediciones:
            texto_requerido(medicion, "tipo")
            texto_requerido(medicion, "unidad")
            valor = medicion.get("valor")
            if type(valor) not in (int, float) or (isinstance(valor, float) and not math.isfinite(valor)):
                raise ValueError("Cada medición debe tener un valor numérico.")
    if CAMPO_PRAXIS in expediente:
        registros = expediente[CAMPO_PRAXIS]
        if not isinstance(registros, list) or not all(isinstance(registro, dict) for registro in registros):
            raise ValueError("Praxis Motora debe contener una lista de rondas.")
        registros = [registro_praxis(r.get("id"), r.get("fecha_hora"), r.get("tiempos_ms")) for r in registros]
        if len({registro["id"] for registro in registros}) != len(registros):
            raise ValueError("Los identificadores de Praxis Motora deben ser únicos.")
        expediente[CAMPO_PRAXIS] = registros
    if CAMPO_VOLT in expediente:
        expediente[CAMPO_VOLT] = registros_volt(expediente[CAMPO_VOLT])
    return expediente
