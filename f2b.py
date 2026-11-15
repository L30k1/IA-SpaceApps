from random import Random
from statistics import median


CAMPO_F2B = "fractal_2_back"
VERSION_F2B = "medispace-f2b-1"
ESTIMULOS_F2B = 62
COINCIDENCIAS_F2B = 15
EXPOSICION_F2B_MS = 1750
FIGURAS_F2B = tuple(range(12))


def secuencia_f2b(identificador):
    rng = Random(identificador)
    objetivos = set(rng.sample(range(2, ESTIMULOS_F2B), COINCIDENCIAS_F2B))
    secuencia = rng.sample(FIGURAS_F2B, 2)
    for indice in range(2, ESTIMULOS_F2B):
        anterior = secuencia[indice - 2]
        secuencia.append(anterior if indice in objetivos else rng.choice([f for f in FIGURAS_F2B if f != anterior]))
    return secuencia


def puntuar_f2b(identificador, respuestas):
    if not isinstance(respuestas, list) or len(respuestas) != ESTIMULOS_F2B:
        raise ValueError("La ronda de Fractal 2-Back está incompleta.")
    secuencia = secuencia_f2b(identificador)
    tiempos_aciertos = []
    falsas_alarmas = 0
    tiempos = []
    for indice, tiempo in enumerate(respuestas):
        if tiempo is None:
            tiempos.append(None)
            continue
        if type(tiempo) not in (int, float) or not 0 <= tiempo < EXPOSICION_F2B_MS:
            raise ValueError("Un tiempo de respuesta de Fractal 2-Back está fuera del intervalo permitido.")
        tiempo = min(round(tiempo, 3), EXPOSICION_F2B_MS - 0.001)
        tiempos.append(tiempo)
        if indice >= 2 and secuencia[indice] == secuencia[indice - 2]:
            tiempos_aciertos.append(tiempo)
        else:
            falsas_alarmas += 1
    aciertos = len(tiempos_aciertos)
    return {
        "aciertos": aciertos,
        "omisiones": COINCIDENCIAS_F2B - aciertos,
        "falsas_alarmas": falsas_alarmas,
        "rechazos_correctos": ESTIMULOS_F2B - COINCIDENCIAS_F2B - falsas_alarmas,
        "mediana_aciertos_ms": round(median(tiempos_aciertos), 3) if aciertos else None,
        "respuestas_ms": tiempos,
    }
