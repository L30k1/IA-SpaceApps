from itertools import combinations
from random import Random
from statistics import mean

from language import translate as t


LOT_FIELD = "orientacion_linea"
LOT_VERSION = "medispace-lot-1"
LOT_TRIAL_COUNT = 12
LOT_ANGLES = tuple(range(165, 14, -15))
LOT_OPTIONS = range(1, len(LOT_ANGLES) + 1)


def lot_pairs(identifier):
    return Random(identifier).sample(list(combinations(LOT_OPTIONS, 2)), LOT_TRIAL_COUNT)


def score_lot(identifier, answers):
    if not isinstance(answers, list) or len(answers) != LOT_TRIAL_COUNT:
        raise ValueError(t("Complete all {cantidad} pairs of lines.", cantidad=LOT_TRIAL_COUNT))
    trials = []
    for reply, expected_choice in zip(answers, lot_pairs(identifier)):
        if not isinstance(reply, dict):
            raise ValueError("The line orientation answer is invalid.")
        selection = reply.get("lineas")
        if (not isinstance(selection, list) or len(selection) != 2
                or any(type(n) is not int or n not in LOT_OPTIONS for n in selection)
                or selection[0] == selection[1]):
            raise ValueError("Select two different line numbers for each pair.")
        duration_ms = reply.get("tiempo_ms")
        if type(duration_ms) not in (int, float) or not 0 <= duration_ms <= 2**53 - 1:
            raise ValueError("Each pair needs a valid response time in milliseconds.")
        trials.append({
            "lineas": sorted(selection), "tiempo_ms": round(duration_ms, 3),
            "coincidencias": len(set(selection).intersection(expected_choice)),
        })
    return {
        "pares_correctos": sum(r["coincidencias"] == 2 for r in trials),
        "lineas_correctas": sum(r["coincidencias"] for r in trials),
        "promedio_ms": round(mean(r["tiempo_ms"] for r in trials), 3),
        "respuestas": trials,
    }
