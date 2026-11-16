from datetime import date, timedelta, timezone

from database.medical_records import PRAXIS_FIELD, utc_datetime
from exercise import EXERCISE_FIELD
from lot import LOT_FIELD
from volt import VOLT_FIELD


MISSION_TIMEZONE = timezone(timedelta(hours=-6), "UTC−6")
COGNITIVE_TEST_FIELDS = (PRAXIS_FIELD, VOLT_FIELD, LOT_FIELD)
ASSESSMENT_FREQUENCIES = (
    (7, 1, "diario", 7),
    (30, 3, "semanal", 14),
    (date.max.toordinal(), 7, "semanal", 30),
)
DAILY_EXERCISE_TARGETS = (
    (7, 20, ("general",)),
    (30, 30, ("aerobico", "fuerza")),
    (date.max.toordinal(), 45, ("aerobico", "fuerza", "movilidad")),
)
EXERCISE_EXAMPLES = {
    "general": "Aerobic, strength, or mobility activity from the mission plan.",
    "aerobico": "Stationary cycling or treadmill, depending on available equipment.",
    "fuerza": "Resistance exercises using the equipment designated for the mission.",
    "movilidad": "Mobility and recovery activities from the mission plan.",
}


def mission_dates(mission):
    try:
        start = date.fromisoformat(mission.get("fecha_inicio"))
        end = date.fromisoformat(mission.get("fecha_fin"))
    except (TypeError, ValueError):
        return None
    return (start, end) if start <= end else None


def assessment_dates(entries, missions, current_time):
    by_mission = {identifier: [] for identifier in missions}
    preflight = {identifier: [] for identifier in missions}
    for entry in entries:
        phase = entry.get("fase")
        if phase == "posvuelo":
            continue
        timestamp_value = utc_datetime(entry["fecha_hora"])
        if timestamp_value > current_time:
            continue
        day = timestamp_value.astimezone(MISSION_TIMEZONE).date()
        identifier = entry.get("mision_id")
        candidate_missions = [lookup_key for lookup_key, (start, end) in missions.items() if start <= day <= end]
        if not identifier:
            if len(candidate_missions) == 1:
                identifier = candidate_missions[0]
            elif not candidate_missions:
                future = [lookup_key for lookup_key, (start, _) in missions.items() if day < start]
                if len(future) == 1:
                    identifier = future[0]
        if identifier not in missions:
            continue
        start, end = missions[identifier]
        if day < start or (phase == "preflight" and day <= end):
            preflight[identifier].append(day)
        elif phase != "preflight" and start <= day <= end:
            by_mission[identifier].append(day)
    return by_mission, preflight


def assessment_schedule(start, end, today, interval, components, prior_entries):
    duration = (end - start).days + 1
    total = max(1, duration // interval)
    elapsed_days = (today - start).days
    i = min(total - 1, max(0, elapsed_days // interval))
    deadline = min(duration, (i + 1) * interval)
    limit_value = start + timedelta(days=deadline - 1)
    ciclos = []
    on_schedule = []
    for days_count in components:
        elapsed_units = [(day - start).days for day in days_count]
        ciclos.append({min(total - 1, day // interval) for day in elapsed_units})
        on_schedule.append({day // interval for day in elapsed_units if day < total * interval})
    complete = set.intersection(*ciclos)
    on_time = set.intersection(*on_schedule)
    overdue = i - sum(period < i for period in on_time)
    remaining = sum(i not in piece for piece in ciclos)
    previous_value = max((day for days_count in prior_entries for day in days_count), default=None)
    if today < start:
        remaining = sum(not days_count for days_count in prior_entries)
        state = "Preflight recorded" if previous_value else "Scheduled"
    elif i in complete:
        state = "Completed" if i in on_time else "Completed after deadline"
    elif today > limit_value:
        state = "Overdue"
    else:
        state = "Pending"
    if i in complete and i + 1 < total:
        next_date = start + timedelta(days=deadline + interval - 1)
    else:
        next_date = None
    return {"intervalo": interval, "total": total, "estado": state, "limite": limit_value, "vencidas": overdue,
            "restantes": remaining, "proxima": next_date, "previo": previous_value}


def mission_exercise_routine(mission, start, end, today, sesiones):
    duration = (end - start).days + 1
    _, base_minimum, kinds = next(rule for rule in DAILY_EXERCISE_TARGETS if duration <= rule[0])
    lower_bound = mission.get("ejercicio_min_diarios", base_minimum)
    medical_summary = sesiones[mission["id"]]
    return {
        "activa": start <= today <= end, "minimo": lower_bound, **medical_summary,
        "faltan": max(0, lower_bound - medical_summary["minutos_hoy"]),
        "ejemplos": [EXERCISE_EXAMPLES[kind] for kind in kinds],
    }


def summarize_exercise(sesiones, missions, current_time):
    medical_summary = {identifier: {"minutos_hoy": 0, "total_sesiones": 0} for identifier in missions}
    today = current_time.astimezone(MISSION_TIMEZONE).date()
    for sesion in sesiones:
        timestamp_value = utc_datetime(sesion["fecha_hora"])
        if timestamp_value > current_time:
            continue
        day = timestamp_value.astimezone(MISSION_TIMEZONE).date()
        candidate_missions = [lookup_key for lookup_key, (start, end) in missions.items() if start <= day <= end]
        identifier = sesion.get("mision_id")
        if not identifier and len(candidate_missions) == 1:
            identifier = candidate_missions[0]
        if identifier in candidate_missions:
            medical_summary[identifier]["total_sesiones"] += 1
            if day == today:
                medical_summary[identifier]["minutos_hoy"] += sesion["duracion_min"]
    return medical_summary


def build_mission_schedule(medical_record, medical_entries, current_time):
    today = current_time.astimezone(MISSION_TIMEZONE).date()
    missions = {m["id"]: dates for m in medical_record["misiones"] if (dates := mission_dates(m))}
    fields = {field_name: assessment_dates(medical_record.get(field_name, []), missions, current_time) for field_name in (
        "diario_psicologico", "semanal_psicologico", *COGNITIVE_TEST_FIELDS,
    )}
    checkup_entries, prior_medical_entries = assessment_dates(medical_entries, missions, current_time)
    sesiones = summarize_exercise(medical_record.get(EXERCISE_FIELD, []), missions, current_time)
    schedules = []
    for mission in medical_record["misiones"]:
        identifier = mission["id"]
        plan = {"mision": mission}
        if identifier in missions:
            start, end = missions[identifier]
            duration = (end - start).days + 1
            _, prescription, psychological_support, cognition = next(rule for rule in ASSESSMENT_FREQUENCIES if duration <= rule[0])
            psychological_interval = 1 if psychological_support == "diario" else 7
            psychological_entries, prior_psychological_entries = fields[f"{psychological_support}_psicologico"]
            other_module = "diario" if psychological_support == "semanal" else "semanal"
            others, other_prior_entries = fields[f"{other_module}_psicologico"]
            plan.update(
                duracion=duration, inicio=start,
                estado="Scheduled" if today < start else "In progress" if today <= end else "Ended",
                psicologia=psychological_support,
                otro_cuestionario=other_module,
                ultimo_otro=max(others[identifier] + other_prior_entries[identifier], default=None),
                medica=assessment_schedule(start, end, today, prescription, [checkup_entries[identifier]],
                                    [prior_medical_entries[identifier]]),
                psicologica=assessment_schedule(start, end, today, psychological_interval,
                                         [psychological_entries[identifier]], [prior_psychological_entries[identifier]]),
                cognitiva=assessment_schedule(start, end, today, cognition,
                                       [fields[c][0][identifier] for c in COGNITIVE_TEST_FIELDS],
                                       [fields[c][1][identifier] for c in COGNITIVE_TEST_FIELDS]),
                rutina=mission_exercise_routine(mission, start, end, today, sesiones),
            )
        schedules.append(plan)
    return schedules
