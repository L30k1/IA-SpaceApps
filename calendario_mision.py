from datetime import date, timedelta, timezone

from database.expedientes import CAMPO_PRAXIS, fecha_utc
from ejercicio import CAMPO_EJERCICIO, TIPOS_EJERCICIO
from lot import CAMPO_LOT
from volt import CAMPO_VOLT


ZONA_MISION = timezone(timedelta(hours=-6), "UTC−6")
PRUEBAS_COGNITIVAS = (CAMPO_PRAXIS, CAMPO_VOLT, CAMPO_LOT)
FRECUENCIAS = (
    (7, 1, "diario", 7),
    (30, 3, "semanal", 14),
    (date.max.toordinal(), 7, "semanal", 30),
)
METAS_REGISTRO_EJERCICIO = (
    (7, ("general",)),
    (30, ("aerobico", "fuerza")),
    (date.max.toordinal(), ("aerobico", "fuerza", "movilidad")),
)
EJEMPLOS_EJERCICIO = {
    "general": "Registra una sesión de aeróbico, fuerza o movilidad del plan de la misión.",
    "aerobico": "Bicicleta estática o cinta, según el equipo disponible.",
    "fuerza": "Ejercicios de resistencia con el equipo previsto para la misión.",
    "movilidad": "Movilidad y recuperación según el plan de la misión.",
}


def fechas_mision(mision):
    try:
        inicio = date.fromisoformat(mision.get("fecha_inicio"))
        fin = date.fromisoformat(mision.get("fecha_fin"))
    except (TypeError, ValueError):
        return None
    return (inicio, fin) if inicio <= fin else None


def fechas_registros(registros, misiones, ahora):
    por_mision = {identificador: [] for identificador in misiones}
    prevuelo = {identificador: [] for identificador in misiones}
    for registro in registros:
        fase = registro.get("fase")
        if fase == "posvuelo":
            continue
        instante = fecha_utc(registro["fecha_hora"])
        if instante > ahora:
            continue
        dia = instante.astimezone(ZONA_MISION).date()
        identificador = registro.get("mision_id")
        candidatas = [clave for clave, (inicio, fin) in misiones.items() if inicio <= dia <= fin]
        if not identificador:
            if len(candidatas) == 1:
                identificador = candidatas[0]
            elif not candidatas:
                futuras = [clave for clave, (inicio, _) in misiones.items() if dia < inicio]
                if len(futuras) == 1:
                    identificador = futuras[0]
        if identificador not in misiones:
            continue
        inicio, fin = misiones[identificador]
        if dia < inicio or (fase == "preflight" and dia <= fin):
            prevuelo[identificador].append(dia)
        elif fase != "preflight" and inicio <= dia <= fin:
            por_mision[identificador].append(dia)
    return por_mision, prevuelo


def cumplimiento(inicio, fin, hoy, intervalo, componentes, previos):
    duracion = (fin - inicio).days + 1
    total = max(1, duracion // intervalo)
    dias_pasados = (hoy - inicio).days
    i = min(total - 1, max(0, dias_pasados // intervalo))
    plazo = min(duracion, (i + 1) * intervalo)
    limite = inicio + timedelta(days=plazo - 1)
    ciclos = []
    a_tiempo = []
    for dias in componentes:
        transcurridos = [(dia - inicio).days for dia in dias]
        ciclos.append({min(total - 1, dia // intervalo) for dia in transcurridos})
        a_tiempo.append({dia // intervalo for dia in transcurridos if dia < total * intervalo})
    completos = set.intersection(*ciclos)
    puntuales = set.intersection(*a_tiempo)
    vencidas = i - sum(ciclo < i for ciclo in puntuales)
    restantes = sum(i not in parte for parte in ciclos)
    previo = max((dia for dias in previos for dia in dias), default=None)
    if hoy < inicio:
        restantes = sum(not dias for dias in previos)
        estado = "Prevuelo registrado" if previo else "Programada"
    elif i in completos:
        estado = "Completada" if i in puntuales else "Completada fuera de plazo"
    elif hoy > limite:
        estado = "Vencida"
    else:
        estado = "Pendiente"
    if i in completos and i + 1 < total:
        proxima = inicio + timedelta(days=plazo + intervalo - 1)
    else:
        proxima = None
    return {"intervalo": intervalo, "total": total, "estado": estado, "limite": limite, "vencidas": vencidas,
            "restantes": restantes, "proxima": proxima, "previo": previo}


def rutina_mision(identificador, inicio, fin, hoy, sesiones_por_tipo):
    duracion = (fin - inicio).days + 1
    _, tipos = next(regla for regla in METAS_REGISTRO_EJERCICIO if duracion <= regla[0])
    intervalo = min(duracion, 7)
    dia = min(fin, max(inicio, hoy))
    inicio_periodo = inicio + timedelta(days=((dia - inicio).days // intervalo) * intervalo)
    fin_periodo = inicio_periodo + timedelta(days=min(intervalo - 1, (fin - inicio_periodo).days))
    if (fin_periodo - inicio_periodo).days == 0:
        tipos = ("general",)
    metas = []
    for tipo in tipos:
        dias = sesiones_por_tipo[tipo][identificador]
        metas.append({"tipo": TIPOS_EJERCICIO.get(tipo, "Actividad registrada"), "ejemplo": EJEMPLOS_EJERCICIO[tipo],
                      "completada": any(inicio_periodo <= fecha <= fin_periodo for fecha in dias)})
    return {"inicio": inicio_periodo, "fin": fin_periodo, "metas": metas,
            "completadas": sum(meta["completada"] for meta in metas)}


def calendario(expediente, medicos, ahora):
    hoy = ahora.astimezone(ZONA_MISION).date()
    misiones = {m["id"]: fechas for m in expediente["misiones"] if (fechas := fechas_mision(m))}
    campos = {campo: fechas_registros(expediente.get(campo, []), misiones, ahora) for campo in (
        "diario_psicologico", "semanal_psicologico", *PRUEBAS_COGNITIVAS,
    )}
    chequeos, previos_medicos = fechas_registros(medicos, misiones, ahora)
    sesiones = expediente.get(CAMPO_EJERCICIO, [])
    sesiones_por_tipo = {"general": fechas_registros(sesiones, misiones, ahora)[0]}
    for tipo in ("aerobico", "fuerza", "movilidad"):
        sesiones_por_tipo[tipo] = fechas_registros((s for s in sesiones if s["tipo"] == tipo), misiones, ahora)[0]
    planes = []
    for mision in expediente["misiones"]:
        identificador = mision["id"]
        plan = {"mision": mision}
        if identificador in misiones:
            inicio, fin = misiones[identificador]
            duracion = (fin - inicio).days + 1
            _, medicina, psicologia, cognicion = next(regla for regla in FRECUENCIAS if duracion <= regla[0])
            intervalo_psicologico = 1 if psicologia == "diario" else 7
            psicologicos, previos_psicologicos = campos[f"{psicologia}_psicologico"]
            otro_modulo = "diario" if psicologia == "semanal" else "semanal"
            otros, otros_previos = campos[f"{otro_modulo}_psicologico"]
            plan.update(
                duracion=duracion, inicio=inicio,
                estado="Programada" if hoy < inicio else "En curso" if hoy <= fin else "Finalizada",
                psicologia=psicologia,
                otro_cuestionario=otro_modulo,
                ultimo_otro=max(otros[identificador] + otros_previos[identificador], default=None),
                medica=cumplimiento(inicio, fin, hoy, medicina, [chequeos[identificador]],
                                    [previos_medicos[identificador]]),
                psicologica=cumplimiento(inicio, fin, hoy, intervalo_psicologico,
                                         [psicologicos[identificador]], [previos_psicologicos[identificador]]),
                cognitiva=cumplimiento(inicio, fin, hoy, cognicion,
                                       [campos[c][0][identificador] for c in PRUEBAS_COGNITIVAS],
                                       [campos[c][1][identificador] for c in PRUEBAS_COGNITIVAS]),
                rutina=rutina_mision(identificador, inicio, fin, hoy, sesiones_por_tipo),
            )
        planes.append(plan)
    return planes
