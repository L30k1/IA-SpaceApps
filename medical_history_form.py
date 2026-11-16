import json
from datetime import datetime
from itertools import zip_longest
from math import isfinite
from uuid import uuid4

from mission_calendar import MISSION_TIMEZONE
from database.medical_records import INPUT_LIMITS, VITAL_SIGNS, read_medical_record
from exercise import EXERCISE_FIELD
from emotion_recognition import ERT_FIELD
from f2b import F2B_FIELD


FORM_SECTIONS = (
    ("misiones", "Misiones", (
        ("id", "ID de misión", "text"), ("fecha_inicio", "Start", "date"), ("fecha_fin", "End", "date"),
        ("ejercicio_min_diarios", "Daily exercise minimum (min, optional)", "number"),
    )),
    ("alergias", "Alergias", (
        ("sustancia", "Sustancia", "text"), ("reaccion", "Reacción", "text"), ("gravedad", "Gravedad", "text"),
        ("fecha", "Date", "date"), ("confirmacion", "Confirmación", "text"),
        ("reportado_por", "Reported by", "text"), ("verificado_por", "Verified by", "text"),
    )),
    ("antecedentes", "Antecedentes", (
        ("condicion", "Condición", "text"), ("fecha_inicio", "Start", "date"), ("estado", "Estado", "text"),
        ("observaciones", "Notes", "textarea"), ("reportado_por", "Reported by", "text"),
        ("verificado_por", "Verified by", "text"),
    )),
    ("medicamentos", "Medicamentos", (
        ("nombre", "Medication", "text"), ("dosis", "Dosis", "number"), ("unidad", "Dose unit", "text"),
        ("via", "Route", "text"), ("frecuencia", "Frecuencia", "text"), ("motivo", "Motivo", "text"),
        ("fecha_inicio", "Start", "date"), ("fecha_fin", "End", "date"), ("estado", "Estado", "text"),
        ("reportado_por", "Reported by", "text"), ("verificado_por", "Verified by", "text"),
    )),
    ("chequeos", "Previous checkups", (
        ("fecha_hora", "Date and time (Mexico City)", "datetime-local"), ("mision_id", "ID de misión", "text"),
        ("fase", "Fase de misión", "fase"), ("motivo", "Motivo", "text"), ("actividad", "Actividad", "text"),
        ("frecuencia_cardiaca", "Frecuencia cardíaca (lpm)", "number"), ("spo2", "SpO₂ (%)", "number"),
        ("temperatura", "Temperatura (°C)", "number"), ("estado_revision", "Review status", "text"),
        ("accion_acordada", "Agreed action", "text"), ("fecha_seguimiento", "Follow-up date", "date"),
    )),
)


def form_rows(form_data, *, editing=False):
    rows = {}
    for group, _, fields in FORM_SECTIONS:
        names = [field_name for field_name, _, _ in fields]
        if editing and group in {"alergias", "antecedentes", "medicamentos"}:
            names.append("_fila_original")
        columns = [form_data.getlist(f"{group}.{field_name}") for field_name in names]
        rows[group] = [
            {field_name: value for field_name, value in zip(names, measurements_values) if value.strip()}
            for measurements_values in zip_longest(*columns, fillvalue="")
        ]
    return rows


def adjust_form_rows(rows, action):
    operation, _, destination = action.partition(":")
    group, _, index_score = destination.partition(":")
    if group not in rows:
        return False
    if operation == "agregar" and not index_score:
        rows[group].append({})
    elif (operation == "quitar" and index_score.isascii() and index_score.isdigit()
          and len(index_score) <= 6 and int(index_score) < len(rows[group])):
        rows[group].pop(int(index_score))
    else:
        return False
    return True


def build_medical_record(form_data, rows):
    medical_record = {
        "_id": form_data.get("astronauta_id", ""), "astronauta": {"nombre": form_data.get("nombre", "")},
        "estado_alergias": form_data.get("estado_alergias", "").strip(),
        "diario_psicologico": [], "semanal_psicologico": [], "praxis_motora": [],
        "memoria_visual": [], "orientacion_linea": [], F2B_FIELD: [], ERT_FIELD: [], EXERCISE_FIELD: [],
    }
    reference_ranges = {}
    for kind in INPUT_LIMITS:
        measurements_values = {limit_value: form_data.get(f"referencias.{kind}.{limit_value}", "").strip()
                   for limit_value in ("minimo", "maximo")}
        if any(measurements_values.values()):
            try:
                reference_ranges[kind] = {limit_value: float(value) for limit_value, value in measurements_values.items()}
            except ValueError:
                raise ValueError("Enter both limits as numbers or leave both blank.") from None
    if reference_ranges:
        medical_record["referencias_monitoreo"] = reference_ranges
    for group, _, _ in FORM_SECTIONS:
        medical_record[group] = [
            {field_name: value.strip() for field_name, value in row_data.items() if value.strip()}
            for row_data in rows[group] if any(value.strip() for value in row_data.values())
        ]
    for medication in medical_record["medicamentos"]:
        if "dosis" in medication:
            try:
                medication["dosis"] = float(medication["dosis"])
                if not isfinite(medication["dosis"]):
                    raise ValueError
            except ValueError:
                raise ValueError("Enter a numeric dose and put its unit in the separate field.") from None
    for mission in medical_record["misiones"]:
        if "ejercicio_min_diarios" in mission:
            try:
                mission["ejercicio_min_diarios"] = int(mission["ejercicio_min_diarios"])
            except ValueError:
                raise ValueError("The daily exercise minimum must be a whole number from 1 to 1440 minutes.") from None
    for checkup_entry in medical_record["chequeos"]:
        try:
            timestamp = datetime.fromisoformat(checkup_entry.get("fecha_hora", ""))
        except ValueError:
            raise ValueError("Each previous checkup needs a date and time.") from None
        checkup_entry["id"] = f"chequeo-{uuid4().hex}"
        checkup_entry["fecha_hora"] = (timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=MISSION_TIMEZONE)).isoformat()
        try:
            checkup_entry["mediciones"] = [
                {"tipo": kind, "unidad": unit, "valor": float(checkup_entry.pop(kind))}
                for kind, (_, unit) in VITAL_SIGNS.items() if kind in checkup_entry
            ]
        except ValueError:
            raise ValueError("Enter the vital signs as numbers.") from None
        assessment = {field_name: checkup_entry.pop(field_name) for field_name in (
            "estado_revision", "accion_acordada", "fecha_seguimiento",
        ) if field_name in checkup_entry}
        if assessment:
            checkup_entry["evaluacion"] = assessment
    return read_medical_record(json.dumps(medical_record, ensure_ascii=False))
