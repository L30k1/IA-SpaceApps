from random import Random
from statistics import median


F2B_FIELD = "fractal_2_back"
F2B_VERSION = "medispace-f2b-1"
F2B_STIMULUS_COUNT = 62
F2B_MATCHES = 15
F2B_EXPOSURE_MS = 1750
F2B_SHAPE_COUNT = tuple(range(12))


def f2b_sequence(identifier):
    rng = Random(identifier)
    targets_count = set(rng.sample(range(2, F2B_STIMULUS_COUNT), F2B_MATCHES))
    sequence = rng.sample(F2B_SHAPE_COUNT, 2)
    for index_score in range(2, F2B_STIMULUS_COUNT):
        previous = sequence[index_score - 2]
        sequence.append(previous if index_score in targets_count else rng.choice([f for f in F2B_SHAPE_COUNT if f != previous]))
    return sequence


def score_f2b(identifier, answers):
    if not isinstance(answers, list) or len(answers) != F2B_STIMULUS_COUNT:
        raise ValueError("The Fractal 2-Back round is incomplete.")
    sequence = f2b_sequence(identifier)
    correct_times = []
    false_alarms = 0
    response_times = []
    for index_score, duration_ms in enumerate(answers):
        if duration_ms is None:
            response_times.append(None)
            continue
        if type(duration_ms) not in (int, float) or not 0 <= duration_ms < F2B_EXPOSURE_MS:
            raise ValueError("A Fractal 2-Back response time is outside the allowed window.")
        duration_ms = min(round(duration_ms, 3), F2B_EXPOSURE_MS - 0.001)
        response_times.append(duration_ms)
        if index_score >= 2 and sequence[index_score] == sequence[index_score - 2]:
            correct_times.append(duration_ms)
        else:
            false_alarms += 1
    correct_count = len(correct_times)
    return {
        "aciertos": correct_count,
        "omisiones": F2B_MATCHES - correct_count,
        "falsas_alarmas": false_alarms,
        "rechazos_correctos": F2B_STIMULUS_COUNT - F2B_MATCHES - false_alarms,
        "mediana_aciertos_ms": round(median(correct_times), 3) if correct_count else None,
        "respuestas_ms": response_times,
    }
