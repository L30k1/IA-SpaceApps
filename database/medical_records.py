import json
import math
import re
from datetime import datetime, timezone

from exercise import EXERCISE_FIELD, validate_exercise_session
from emotion_recognition import ERT_FIELD, ERT_VERSION, score_emotion_test
from f2b import F2B_FIELD, F2B_VERSION, score_f2b
from language import translate as t
from lot import LOT_FIELD, LOT_VERSION, score_lot
from volt import VOLT_FIELD, DELAY, VOLT_VERSION, make_stimuli, score


RECORD_GROUPS = ("misiones", "alergias", "antecedentes", "medicamentos", "chequeos")
VITAL_SIGNS = {
    "frecuencia_cardiaca": ("FC", "lpm"),
    "spo2": ("SpO₂", "%"),
    "temperatura": ("Temperatura", "°C"),
}
# Application input limits. Clinical reference ranges are defined separately.
INPUT_LIMITS = {"frecuencia_cardiaca": (1, 999), "spo2": (0, 100), "temperatura": (0.1, 99.9)}
PHASES = {"preflight": "Prevuelo", "vuelo": "Vuelo", "posvuelo": "Posvuelo"}
PRAXIS_FIELD = "praxis_motora"
PRAXIS_TARGETS = 20


def validate_reference_ranges(reference_ranges):
    if not isinstance(reference_ranges, dict) or reference_ranges.keys() - VITAL_SIGNS.keys():
        raise ValueError("Monitoring references must match the vital signs in the medical record.")
    ranges = {}
    for kind, reference_range in reference_ranges.items():
        if reference_range is None:
            continue
        lower_bound, upper_bound = (reference_range.get("minimo"), reference_range.get("maximo")) if isinstance(reference_range, dict) else (None, None)
        below, above = INPUT_LIMITS[kind]
        if (type(lower_bound) not in (int, float) or type(upper_bound) not in (int, float)
                or not below <= lower_bound <= upper_bound <= above):
            raise ValueError(t("Check the minimum and maximum for {signo}. Enter both within the accepted input limits.",
                               signo=t(VITAL_SIGNS[kind][0])))
        ranges[kind] = {"minimo": lower_bound, "maximo": upper_bound}
    return ranges


def required_text(entry, field_name):
    value = entry.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(t("Fill in the {campo} field in the medical record.", campo=field_name))
    return value.strip()


def utc_datetime(timestamp):
    try:
        value = datetime.fromisoformat(timestamp)
        if value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError("Checkup timestamps need a time zone, for example 2026-11-14T21:30:00Z.")


def praxis_entry(identifier, timestamp, response_times):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("The Motor Praxis round ID is invalid.")
    if not isinstance(response_times, list) or len(response_times) != PRAXIS_TARGETS or any(
        type(duration_ms) not in (int, float) or not 0 <= duration_ms <= 2**53 - 1 for duration_ms in response_times
    ):
        raise ValueError(t("The round must contain {cantidad} valid times in milliseconds.", cantidad=PRAXIS_TARGETS))
    response_times = [round(duration_ms, 3) for duration_ms in response_times]
    return {
        "id": identifier,
        "fecha_hora": utc_datetime(timestamp).isoformat(),
        "tiempos_ms": response_times,
        "promedio_ms": round(sum(response_times) / len(response_times), 3),
        "mejor_ms": min(response_times),
    }


def lot_entry(identifier, timestamp, answers):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("The Line Orientation Test ID is invalid.")
    return {
        "id": identifier, "fecha_hora": utc_datetime(timestamp).isoformat(), "version": LOT_VERSION,
        **score_lot(identifier, answers),
    }


def validate_volt_entries(entries):
    if not isinstance(entries, list):
        raise ValueError("Visual object learning must contain a list of sessions.")
    normalized_values = []
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("version") != VOLT_VERSION:
            raise ValueError("The visual object learning record version is invalid.")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier) or identifier in ids:
            raise ValueError("Visual object learning session IDs must be valid and unique.")
        interval = entry.get("intervalo_segundos")
        if type(interval) not in (int, float) or not DELAY.total_seconds() <= interval <= 2**53 - 1:
            raise ValueError("The visual object learning interval is invalid.")
        normalized = {"id": identifier, "version": VOLT_VERSION, "intervalo_segundos": interval,
                       "fecha_hora": utc_datetime(entry.get("fecha_hora")).isoformat()}
        for phase, trials in zip(("inmediato", "diferido"), make_stimuli(identifier)[1:]):
            outcome = entry.get(phase)
            if not isinstance(outcome, dict):
                raise ValueError("The record must include both recognition phases.")
            normalized[phase] = score(outcome.get("respuestas"), trials)
        normalized_values.append(normalized)
        ids.add(identifier)
    return normalized_values


def f2b_entry(identifier, timestamp, answers):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("The Fractal 2-Back round ID is invalid.")
    return {
        "id": identifier, "fecha_hora": utc_datetime(timestamp).isoformat(), "version": F2B_VERSION,
        **score_f2b(identifier, answers),
    }


def emotion_test_entry(identifier, timestamp, answers):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("The facial emotion recognition round ID is invalid.")
    return {
        "id": identifier, "fecha_hora": utc_datetime(timestamp).isoformat(), "version": ERT_VERSION,
        **score_emotion_test(identifier, answers),
    }


def exercise_entry(identifier, timestamp, sesion):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("The exercise session ID is invalid.")
    return {"id": identifier, "fecha_hora": utc_datetime(timestamp).isoformat(), **validate_exercise_session(sesion)}


def read_medical_record(content_blob):
    try:
        medical_record = json.loads(content_blob)
    except (ValueError, RecursionError):
        raise ValueError("The file does not contain valid JSON.") from None
    if not isinstance(medical_record, dict) or not isinstance(medical_record.get("astronauta"), dict):
        raise ValueError("The JSON must include the astronaut's information.")

    medical_record["_id"] = required_text(medical_record, "_id")
    astronaut_id = medical_record["astronauta"]
    astronaut_id["nombre"] = required_text(astronaut_id, "nombre")
    astronaut_id["rol"] = "Astronauta"
    if "referencias_monitoreo" in medical_record:
        medical_record["referencias_monitoreo"] = validate_reference_ranges(medical_record["referencias_monitoreo"])
    for group in RECORD_GROUPS:
        entries = medical_record.setdefault(group, [])
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise ValueError(t("{campo} must be a list of records.", campo=group))
    for group, field_name in (("misiones", "id"), ("alergias", "sustancia"),
                         ("antecedentes", "condicion"), ("medicamentos", "nombre")):
        for entry in medical_record[group]:
            entry[field_name] = required_text(entry, field_name)

    missions = [mission["id"] for mission in medical_record["misiones"]]
    for mission in medical_record["misiones"]:
        if "ejercicio_min_diarios" in mission:
            lower_bound = mission["ejercicio_min_diarios"]
            if type(lower_bound) is not int or not 1 <= lower_bound <= 1440:
                raise ValueError("The daily exercise minimum must be a whole number from 1 to 1440 minutes.")
    identifiers = set()
    for checkup_entry in medical_record["chequeos"]:
        checkup_entry["id"] = required_text(checkup_entry, "id")
        if checkup_entry["id"] in identifiers:
            raise ValueError("Checkup IDs must be unique.")
        identifiers.add(checkup_entry["id"])
        checkup_entry["fecha_hora"] = utc_datetime(checkup_entry.get("fecha_hora")).isoformat()
        if checkup_entry.get("mision_id") is not None and checkup_entry["mision_id"] not in missions:
            raise ValueError("The mission for each checkup must be listed in the medical record.")
        if checkup_entry.get("fase") is not None and checkup_entry["fase"] not in list(PHASES):
            raise ValueError("The JSON phase must be preflight, vuelo, or posvuelo.")
        assessment = checkup_entry.get("evaluacion")
        if assessment is not None and not isinstance(assessment, dict):
            raise ValueError("The assessment must be a JSON object.")
        measurements = checkup_entry.setdefault("mediciones", [])
        if not isinstance(measurements, list) or not all(isinstance(m, dict) for m in measurements):
            raise ValueError("Measurements must be a list of records.")
        for measurement in measurements:
            required_text(measurement, "tipo")
            required_text(measurement, "unidad")
            value = measurement.get("valor")
            if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
                raise ValueError("Each measurement needs a numeric value.")
    if PRAXIS_FIELD in medical_record:
        entries = medical_record[PRAXIS_FIELD]
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise ValueError("Motor Praxis must contain a list of rounds.")
        entries = [praxis_entry(r.get("id"), r.get("fecha_hora"), r.get("tiempos_ms")) for r in entries]
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("Motor Praxis round IDs must be unique.")
        medical_record[PRAXIS_FIELD] = entries
    if VOLT_FIELD in medical_record:
        medical_record[VOLT_FIELD] = validate_volt_entries(medical_record[VOLT_FIELD])
    if LOT_FIELD in medical_record:
        entries = medical_record[LOT_FIELD]
        if not isinstance(entries, list) or not all(
            isinstance(r, dict) and r.get("version") == LOT_VERSION for r in entries
        ):
            raise ValueError("Line Orientation must contain a list of valid rounds.")
        entries = [lot_entry(r.get("id"), r.get("fecha_hora"), r.get("respuestas")) for r in entries]
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("Line Orientation round IDs must be unique.")
        medical_record[LOT_FIELD] = entries
    if F2B_FIELD in medical_record:
        entries = medical_record[F2B_FIELD]
        if not isinstance(entries, list) or not all(
            isinstance(r, dict) and r.get("version") == F2B_VERSION for r in entries
        ):
            raise ValueError("Fractal 2-Back must contain a list of valid rounds.")
        entries = [f2b_entry(r.get("id"), r.get("fecha_hora"), r.get("respuestas_ms")) for r in entries]
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("Fractal 2-Back round IDs must be unique.")
        medical_record[F2B_FIELD] = entries
    if ERT_FIELD in medical_record:
        entries = medical_record[ERT_FIELD]
        if not isinstance(entries, list) or not all(
            isinstance(r, dict) and r.get("version") == ERT_VERSION for r in entries
        ):
            raise ValueError("Facial Emotion Recognition must contain a list of valid rounds.")
        entries = [emotion_test_entry(r.get("id"), r.get("fecha_hora"), r.get("respuestas")) for r in entries]
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("Facial emotion recognition round IDs must be unique.")
        medical_record[ERT_FIELD] = entries
    if EXERCISE_FIELD in medical_record:
        sesiones = medical_record[EXERCISE_FIELD]
        if not isinstance(sesiones, list) or not all(isinstance(r, dict) for r in sesiones):
            raise ValueError("The medical record must contain exercise sessions as a list.")
        sesiones = [exercise_entry(r.get("id"), r.get("fecha_hora"), r) for r in sesiones]
        if any(s.get("mision_id") and s["mision_id"] not in missions for s in sesiones):
            raise ValueError("Select a mission from your record.")
        if len({r["id"] for r in sesiones}) != len(sesiones):
            raise ValueError("Exercise session IDs must be unique.")
        medical_record[EXERCISE_FIELD] = sesiones
    return medical_record
