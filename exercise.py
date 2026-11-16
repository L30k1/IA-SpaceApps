EXERCISE_FIELD = "sesiones_ejercicio"
EXERCISE_TYPES = {
    "aerobico": "Aeróbico",
    "fuerza": "Fuerza",
    "movilidad": "Movilidad",
    "mixto": "Mixed (aerobic and strength)",
}
HEART_RATE_CONTEXTS = {
    "reposo": "En reposo",
    "durante_ejercicio": "Durante el ejercicio",
    "despues_ejercicio": "Después del ejercicio",
}
EXERCISE_HEART_RATE_CONTEXTS = {"durante_ejercicio", "despues_ejercicio"}


def validate_exercise_session(sesion):
    if not isinstance(sesion, dict):
        raise ValueError("The exercise session is invalid.")
    kind, duration, effort = (sesion.get(field_name) for field_name in ("tipo", "duracion_min", "esfuerzo"))
    equipment, recovery = (sesion.get(field_name, "") for field_name in ("equipo", "recuperacion"))
    mission = sesion.get("mision_id")
    if not isinstance(kind, str) or kind not in EXERCISE_TYPES:
        raise ValueError("Select an exercise type.")
    if type(duration) is not int or not 1 <= duration <= 1440:
        raise ValueError("Enter a valid duration in minutes.")
    if effort is not None and (type(effort) is not int or not 0 <= effort <= 10):
        raise ValueError("Perceived effort must be between 0 and 10.")
    if not isinstance(equipment, str) or not isinstance(recovery, str) or len(equipment) > 80 or len(recovery) > 500:
        raise ValueError("Equipment allows up to 80 characters and the recovery note up to 500.")
    if mission is not None and not isinstance(mission, str):
        raise ValueError("Select a mission from your record.")
    return {"tipo": kind, "duracion_min": duration, "esfuerzo": effort,
            "equipo": equipment.strip(), "recuperacion": recovery.strip(),
            **({"mision_id": mission.strip()} if mission and mission.strip() else {})}
