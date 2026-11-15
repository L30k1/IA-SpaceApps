from datetime import date, timedelta, timezone

from database.expedientes import fecha_utc
from lot import CAMPO_LOT
from volt import CAMPO_VOLT


ZONA_MISION = timezone(timedelta(hours=-6), "UTC−6")
FRECUENCIAS = (
    (7, 1, "diario", 7),
    (30, 3, "semanal", 14),
    (date.max.toordinal(), 7, "semanal", 30),
)


def fechas_mision(mision):
    try:
        inicio = date.fromisoformat(mision.get("fecha_inicio"))
        fin = date.fromisoformat(mision.get("fecha_fin"))
    except (TypeError, ValueError):
        return None
    return (inicio, fin) if inicio <= fin else None


def fechas_registros(registros, misiones, ahora):
    por_mision = {identificador: [] for identificador in misiones}
    for registro in registros:
        if registro.get("fase") in {"preflight", "posvuelo"}:
            continue
        instante = fecha_utc(registro["fecha_hora"])
        if instante > ahora:
            continue
        dia = instante.astimezone(ZONA_MISION).date()
        identificador = registro.get("mision_id")
        candidatas = [clave for clave, (inicio, fin) in misiones.items() if inicio <= dia <= fin]
        if identificador in candidatas:
            por_mision[identificador].append(dia)
        elif not identificador and len(candidatas) == 1:
            por_mision[candidatas[0]].append(dia)
    return por_mision


def cumplimiento(inicio, fin, hoy, intervalo, componentes):
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
    if hoy < inicio:
        estado = "Programada"
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
            "restantes": restantes, "proxima": proxima}


def calendario(expediente, medicos, ahora):
    hoy = ahora.astimezone(ZONA_MISION).date()
    misiones = {m["id"]: fechas for m in expediente["misiones"] if (fechas := fechas_mision(m))}
    campos = {campo: fechas_registros(expediente.get(campo, []), misiones, ahora) for campo in (
        "diario_psicologico", "semanal_psicologico", "praxis_motora", CAMPO_VOLT, CAMPO_LOT,
    )}
    chequeos = fechas_registros(medicos, misiones, ahora)
    planes = []
    for mision in expediente["misiones"]:
        identificador = mision["id"]
        plan = {"mision": mision}
        if identificador in misiones:
            inicio, fin = misiones[identificador]
            duracion = (fin - inicio).days + 1
            _, medicina, psicologia, cognicion = next(regla for regla in FRECUENCIAS if duracion <= regla[0])
            intervalo_psicologico = 1 if psicologia == "diario" else 7
            plan.update(
                duracion=duracion,
                estado="Programada" if hoy < inicio else "En curso" if hoy <= fin else "Finalizada",
                psicologia=psicologia,
                medica=cumplimiento(inicio, fin, hoy, medicina, [chequeos[identificador]]),
                psicologica=cumplimiento(inicio, fin, hoy, intervalo_psicologico,
                                         [campos[f"{psicologia}_psicologico"][identificador]]),
                cognitiva=cumplimiento(inicio, fin, hoy, cognicion, [campos[c][identificador] for c in (
                    "praxis_motora", CAMPO_VOLT, CAMPO_LOT,
                )]),
            )
        planes.append(plan)
    return planes
