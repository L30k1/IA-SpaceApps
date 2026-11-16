import json
from hashlib import sha256

from medical_history_form import FORM_SECTIONS, build_medical_record


EDITABLE_GROUPS = ("alergias", "antecedentes", "medicamentos")
EDITABLE_FIELDS = (*EDITABLE_GROUPS, "estado_alergias", "referencias_monitoreo", "misiones")
EDIT_SECTIONS = tuple(section for section in FORM_SECTIONS if section[0] != "chequeos")
EXERCISE_TARGET_FIELD = "ejercicio_min_diarios"


class StaleEditError(ValueError):
    pass


def edit_version(medical_record):
    data = {field_name: medical_record.get(field_name) for field_name in EDITABLE_FIELDS}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def mission_rows(medical_record, targets=None):
    return [
        {"id": mission["id"], "fecha_inicio": mission.get("fecha_inicio") or "",
         "fecha_fin": mission.get("fecha_fin") or "",
         EXERCISE_TARGET_FIELD: targets[i] if targets is not None and i < len(targets) else mission.get(EXERCISE_TARGET_FIELD, "")}
        for i, mission in enumerate(medical_record["misiones"])
    ]


def edit_form(medical_record):
    form_data = {"estado_alergias": medical_record.get("estado_alergias", "")}
    for kind, reference_range in medical_record.get("referencias_monitoreo", {}).items():
        if reference_range:
            form_data.update({f"referencias.{kind}.{boundary}": value for boundary, value in reference_range.items()})
    rows = {"misiones": mission_rows(medical_record)}
    for group in EDITABLE_GROUPS:
        rows[group] = [
            {**row_data, "_fila_original": str(i)} for i, row_data in enumerate(medical_record.get(group, []))
        ] or [{}]
    return form_data, rows


def apply_record_edit(medical_record, version, form_data, rows, targets):
    if version != edit_version(medical_record):
        raise StaleEditError("The record changed while you were editing. Reopen the editor before saving.")
    if len(targets) != len(medical_record["misiones"]):
        raise ValueError("Check the daily minimum for each mission.")
    input_data = {
        **form_data, "nombre": medical_record["astronauta"]["nombre"], "astronauta_id": medical_record["_id"],
    }
    data = {"misiones": [
        {field_name: str(value) for field_name, value in row_data.items()} for row_data in mission_rows(medical_record, targets)
    ], "chequeos": []}
    used_items = {}
    for group in EDITABLE_GROUPS:
        used_items[group] = [row_data for row_data in rows[group] if any(k != "_fila_original" and v for k, v in row_data.items())]
        data[group] = [{k: v for k, v in row_data.items() if k != "_fila_original"} for row_data in used_items[group]]

    validated = build_medical_record(input_data, data)
    updated_record = {**medical_record, "estado_alergias": validated["estado_alergias"],
                   "referencias_monitoreo": validated.get("referencias_monitoreo", {})}
    for group, _, fields in EDIT_SECTIONS:
        if group not in EDITABLE_GROUPS:
            continue
        editable = {field_name for field_name, _, _ in fields}
        original_items = medical_record.get(group, [])
        updated_messages = []
        indices = set()
        for row_data, new_value in zip(used_items[group], validated[group]):
            index_score = row_data.get("_fila_original")
            if index_score is None:
                updated_messages.append(new_value)
                continue
            if not index_score.isascii() or not index_score.isdigit() or len(index_score) > 6:
                raise ValueError("A form row is invalid.")
            i = int(index_score)
            if i >= len(original_items) or i in indices:
                raise ValueError("A form row is invalid.")
            indices.add(i)
            extras = {field_name: value for field_name, value in original_items[i].items() if field_name not in editable}
            updated_messages.append({**extras, **new_value})
        updated_record[group] = updated_messages
    updated_record["misiones"] = [
        {**{k: v for k, v in original.items() if k != EXERCISE_TARGET_FIELD},
         **({EXERCISE_TARGET_FIELD: new_value[EXERCISE_TARGET_FIELD]} if EXERCISE_TARGET_FIELD in new_value else {})}
        for original, new_value in zip(medical_record["misiones"], validated["misiones"])
    ]
    return updated_record
