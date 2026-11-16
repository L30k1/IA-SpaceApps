from itertools import product
from random import Random
from statistics import median


ERT_FIELD = "reconocimiento_emociones"
ERT_VERSION = "medispace-ert-1"
ERT_EXPOSURE_MS = 750
EMOTIONS = {
    "alegria": "Alegría", "tristeza": "Tristeza", "ira": "Ira",
    "miedo": "Miedo", "asco": "Asco", "sorpresa": "Sorpresa",
}
INTENSITIES = {"leve": "Leve", "intensa": "Intensa"}
IMAGE_SHEETS = ("rostros-a.png", "rostros-b.png")


def make_emotion_stimuli(identifier):
    trials = [
        {"lamina": sheet, "casilla": cell, "emocion": emotion, "intensidad": intensity}
        for sheet in IMAGE_SHEETS
        for cell, (emotion, intensity) in enumerate(product(EMOTIONS, INTENSITIES))
    ]
    Random(identifier).shuffle(trials)
    return trials


def score_emotion_test(identifier, answers):
    trials = make_emotion_stimuli(identifier)
    if not isinstance(answers, list) or len(answers) != len(trials):
        raise ValueError("The facial emotion recognition round is incomplete.")
    by_emotion = {emotion: {"aciertos": 0, "total": 0} for emotion in EMOTIONS}
    by_intensity = {level: {"aciertos": 0, "total": 0} for level in INTENSITIES}
    valid_answers = []
    response_times = []
    for trial, reply in zip(trials, answers):
        if not isinstance(reply, dict):
            raise ValueError("The facial emotion recognition answer is invalid.")
        selection, duration_ms = reply.get("emocion"), reply.get("tiempo_ms")
        if (not isinstance(selection, str) or selection not in EMOTIONS
                or type(duration_ms) not in (int, float) or not 0 <= duration_ms <= 2**53 - 1):
            raise ValueError("The facial emotion recognition answer is invalid.")
        duration_ms = round(duration_ms, 3)
        correct = selection == trial["emocion"]
        for group in (by_emotion[trial["emocion"]], by_intensity[trial["intensidad"]]):
            group["aciertos"] += correct
            group["total"] += 1
        if correct:
            response_times.append(duration_ms)
        valid_answers.append({"emocion": selection, "tiempo_ms": duration_ms})
    return {
        "aciertos": len(response_times),
        "total": len(trials),
        "precision_pct": round(100 * len(response_times) / len(trials), 2),
        "mediana_aciertos_ms": median(response_times) if response_times else None,
        "por_emocion": by_emotion,
        "por_intensidad": by_intensity,
        "respuestas": valid_answers,
    }
