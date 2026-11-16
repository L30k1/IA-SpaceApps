from datetime import datetime, timedelta
from random import Random
from statistics import mean
from uuid import uuid4


VOLT_FIELD = "memoria_visual"
VOLT_VERSION = "medispace-volt-1"
SHAPE_COUNT = 10
EXPOSURE_SECONDS = 5
DELAY = timedelta(minutes=15)


def make_stimuli(identifier):
    """Create ten families of shapes, each with two similar distractors."""
    rng = Random(identifier)
    axes = range(3)
    original_items, distractors, delayed_distractors = [], [], []
    used_indices = set()
    while len(original_items) < SHAPE_COUNT:
        baseline = {(0, 0, 0)}
        while len(baseline) < 7:
            neighbor = list(rng.choice(sorted(baseline)))
            neighbor[rng.randrange(3)] += rng.choice((-1, 1))
            baseline.add(tuple(neighbor))

        family = []
        for axis in axes:
            boundary = list(max(sorted(baseline), key=lambda point: (point[axis], sum(point))))
            boundary[axis] += 1
            shape = baseline | {tuple(boundary)}
            minimums = [min(point[i] for point in shape) for i in axes]
            family.append(tuple(sorted(tuple(point[i] - minimums[i] for i in axes) for point in shape)))
        if len(set(family)) != 3 or used_indices.intersection(family):
            continue
        used_indices.update(family)
        rng.shuffle(family)
        original_items.append(family[0])
        distractors.append(family[1])
        delayed_distractors.append(family[2])

    def recognition_round(new_items):
        trials = [(shape, True) for shape in original_items] + [(shape, False) for shape in new_items]
        rng.shuffle(trials)
        return trials

    return original_items, recognition_round(distractors), recognition_round(delayed_distractors)


def score(answers, trials):
    if not isinstance(answers, list) or len(answers) != SHAPE_COUNT * 2:
        raise ValueError("Answer all 20 shapes.")
    entries = []
    for reply, (_, expected_answer) in zip(answers, trials):
        if not isinstance(reply, dict) or type(reply.get("vista")) is not bool:
            raise ValueError("Each shape needs a valid answer.")
        duration_ms = reply.get("tiempo_ms")
        if type(duration_ms) not in (int, float) or not 0 <= duration_ms <= 2**53 - 1:
            raise ValueError("Each shape needs a valid response time in milliseconds.")
        entries.append({"vista": reply["vista"], "esperada": expected_answer, "tiempo_ms": round(duration_ms, 3)})
    return {
        "correctas": sum(r["vista"] == r["esperada"] for r in entries),
        "reconocidas": sum(r["vista"] and r["esperada"] for r in entries),
        "falsos_positivos": sum(r["vista"] and not r["esperada"] for r in entries),
        "promedio_ms": round(mean(r["tiempo_ms"] for r in entries), 3),
        "respuestas": entries,
    }


def advance_test(active_draft, entries, action, identifier, answers, current_time):
    if action == "iniciar":
        return active_draft or {"id": uuid4().hex, "fase": "aprendizaje", "inicio": current_time.isoformat()}, None, None
    if action == "diferido" and any(r["id"] == identifier for r in entries):
        return active_draft, None, identifier
    if active_draft is None or active_draft["id"] != identifier:
        raise ValueError("This test is no longer active. Return to the Visual Object Learning Test page.")
    phase = active_draft["fase"]
    if action == "cancelar":
        return None, None, None
    if action == "inmediato":
        if phase != "aprendizaje":
            return active_draft, None, None
        if (current_time - datetime.fromisoformat(active_draft["inicio"])).total_seconds() < SHAPE_COUNT * EXPOSURE_SECONDS:
            raise ValueError("Complete the learning phase first.")
        return {
            **active_draft, "fase": "espera", "inmediato": score(answers, make_stimuli(identifier)[1]),
            "fin_inmediato": current_time.isoformat(),
        }, None, None
    if action == "abrir_diferido":
        if phase == "diferido":
            return active_draft, None, None
        if phase != "espera" or current_time < datetime.fromisoformat(active_draft["fin_inmediato"]) + DELAY:
            raise ValueError("The 15-minute interval has not passed yet.")
        return {**active_draft, "fase": "diferido", "inicio_diferido": current_time.isoformat()}, None, None
    if action == "diferido" and phase == "diferido":
        start = datetime.fromisoformat(active_draft["inicio_diferido"])
        immediate_end = datetime.fromisoformat(active_draft["fin_inmediato"])
        return None, {
            "id": identifier, "version": VOLT_VERSION, "fecha_hora": current_time.isoformat(),
            "intervalo_segundos": (start - immediate_end).total_seconds(),
            "inmediato": active_draft["inmediato"], "diferido": score(answers, make_stimuli(identifier)[2]),
        }, identifier
    raise ValueError("The requested phase is unavailable.")
