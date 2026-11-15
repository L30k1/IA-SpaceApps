CAMPO_EJERCICIO = "sesiones_ejercicio"
TIPOS_EJERCICIO = {
    "aerobico": "Aeróbico",
    "fuerza": "Fuerza",
    "movilidad": "Movilidad",
    "mixto": "Mixto",
}
CONTEXTOS_FC = {
    "reposo": "En reposo",
    "durante_ejercicio": "Durante el ejercicio",
    "despues_ejercicio": "Después del ejercicio",
}
CONTEXTOS_FC_EJERCICIO = {"durante_ejercicio", "despues_ejercicio"}


def validar_sesion(sesion):
    if not isinstance(sesion, dict):
        raise ValueError("La sesión de ejercicio no es válida.")
    tipo, duracion, esfuerzo = (sesion.get(campo) for campo in ("tipo", "duracion_min", "esfuerzo"))
    equipo, recuperacion = (sesion.get(campo, "") for campo in ("equipo", "recuperacion"))
    mision = sesion.get("mision_id")
    if not isinstance(tipo, str) or tipo not in TIPOS_EJERCICIO:
        raise ValueError("Selecciona un tipo de ejercicio.")
    if type(duracion) is not int or not 1 <= duracion <= 1440:
        raise ValueError("Ingresa una duración válida en minutos.")
    if esfuerzo is not None and (type(esfuerzo) is not int or not 0 <= esfuerzo <= 10):
        raise ValueError("El esfuerzo percibido debe estar entre 0 y 10.")
    if not isinstance(equipo, str) or not isinstance(recuperacion, str) or len(equipo) > 80 or len(recuperacion) > 500:
        raise ValueError("El equipo admite hasta 80 caracteres y la nota de recuperación hasta 500.")
    if mision is not None and not isinstance(mision, str):
        raise ValueError("Selecciona una misión de tu expediente.")
    return {"tipo": tipo, "duracion_min": duracion, "esfuerzo": esfuerzo,
            "equipo": equipo.strip(), "recuperacion": recuperacion.strip(),
            **({"mision_id": mision.strip()} if mision and mision.strip() else {})}
