import json
import math
import re
from datetime import datetime, timezone

from f2b import CAMPO_F2B, VERSION_F2B, puntuar_f2b
from idioma import traducir as t
from lot import CAMPO_LOT, VERSION_LOT, puntuar_lot
from volt import CAMPO_VOLT, ESPERA, VERSION_VOLT, estimulos, puntuar


GRUPOS = ("misiones", "alergias", "antecedentes", "medicamentos", "chequeos")
SIGNOS = {
    "frecuencia_cardiaca": ("FC", "lpm"),
    "spo2": ("SpO₂", "%"),
    "temperatura": ("Temperatura", "°C"),
}
# Límites de captura de la aplicación, no rangos clínicos.
LIMITES_CAPTURA = {"frecuencia_cardiaca": (1, 999), "spo2": (0, 100), "temperatura": (0.1, 99.9)}
FASES = {"preflight": "Prevuelo", "vuelo": "Vuelo", "posvuelo": "Posvuelo"}
CAMPO_PRAXIS = "praxis_motora"
OBJETIVOS_PRAXIS = 20


def validar_referencias_monitoreo(referencias):
    if not isinstance(referencias, dict) or referencias.keys() - SIGNOS.keys():
        raise ValueError("Las referencias del monitoreo deben corresponder a los signos vitales del expediente.")
    rangos = {}
    for tipo, rango in referencias.items():
        if rango is None:
            continue
        minimo, maximo = (rango.get("minimo"), rango.get("maximo")) if isinstance(rango, dict) else (None, None)
        inferior, superior = LIMITES_CAPTURA[tipo]
        if (type(minimo) not in (int, float) or type(maximo) not in (int, float)
                or not inferior <= minimo <= maximo <= superior):
            raise ValueError(t("Revisa el mínimo y el máximo de {signo}. Completa ambos dentro de los límites de captura.",
                               signo=t(SIGNOS[tipo][0])))
        rangos[tipo] = {"minimo": minimo, "maximo": maximo}
    return rangos


def texto_requerido(registro, campo):
    valor = registro.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(t("Completa el campo {campo} en el expediente.", campo=campo))
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
        raise ValueError(t("La ronda debe contener {cantidad} tiempos válidos en milisegundos.", cantidad=OBJETIVOS_PRAXIS))
    tiempos = [round(tiempo, 3) for tiempo in tiempos]
    return {
        "id": identificador,
        "fecha_hora": fecha_utc(fecha).isoformat(),
        "tiempos_ms": tiempos,
        "promedio_ms": round(sum(tiempos) / len(tiempos), 3),
        "mejor_ms": min(tiempos),
    }


def registro_lot(identificador, fecha, respuestas):
    if not isinstance(identificador, str) or not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("El identificador de la prueba de orientación no es válido.")
    return {
        "id": identificador, "fecha_hora": fecha_utc(fecha).isoformat(), "version": VERSION_LOT,
        **puntuar_lot(identificador, respuestas),
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


def registro_f2b(identificador, fecha, respuestas):
    if not isinstance(identificador, str) or not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("El identificador de Fractal 2-Back no es válido.")
    return {
        "id": identificador, "fecha_hora": fecha_utc(fecha).isoformat(), "version": VERSION_F2B,
        **puntuar_f2b(identificador, respuestas),
    }


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
    if "referencias_monitoreo" in expediente:
        expediente["referencias_monitoreo"] = validar_referencias_monitoreo(expediente["referencias_monitoreo"])
    for grupo in GRUPOS:
        registros = expediente.setdefault(grupo, [])
        if not isinstance(registros, list) or not all(isinstance(registro, dict) for registro in registros):
            raise ValueError(t("{campo} debe ser una lista de registros.", campo=grupo))
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
    if CAMPO_LOT in expediente:
        registros = expediente[CAMPO_LOT]
        if not isinstance(registros, list) or not all(
            isinstance(r, dict) and r.get("version") == VERSION_LOT for r in registros
        ):
            raise ValueError("Orientación de línea debe contener una lista de rondas válidas.")
        registros = [registro_lot(r.get("id"), r.get("fecha_hora"), r.get("respuestas")) for r in registros]
        if len({registro["id"] for registro in registros}) != len(registros):
            raise ValueError("Los identificadores de orientación de línea deben ser únicos.")
        expediente[CAMPO_LOT] = registros
    if CAMPO_F2B in expediente:
        registros = expediente[CAMPO_F2B]
        if not isinstance(registros, list) or not all(
            isinstance(r, dict) and r.get("version") == VERSION_F2B for r in registros
        ):
            raise ValueError("Fractal 2-Back debe contener una lista de rondas válidas.")
        registros = [registro_f2b(r.get("id"), r.get("fecha_hora"), r.get("respuestas_ms")) for r in registros]
        if len({registro["id"] for registro in registros}) != len(registros):
            raise ValueError("Los identificadores de Fractal 2-Back deben ser únicos.")
        expediente[CAMPO_F2B] = registros
    return expediente
