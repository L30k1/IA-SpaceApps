from datetime import timedelta
from random import Random
from statistics import mean


CAMPO_VOLT = "memoria_visual"
VERSION_VOLT = "medispace-volt-1"
FIGURAS = 10
EXPOSICION = 5
ESPERA = timedelta(minutes=15)


def estimulos(identificador):
    """Crea diez familias de figuras, cada una con dos distractores parecidos."""
    rng = Random(identificador)
    ejes = range(3)
    originales, distractores, distractores_diferidos = [], [], []
    usados = set()
    while len(originales) < FIGURAS:
        base = {(0, 0, 0)}
        while len(base) < 7:
            vecino = list(rng.choice(sorted(base)))
            vecino[rng.randrange(3)] += rng.choice((-1, 1))
            base.add(tuple(vecino))

        familia = []
        for eje in ejes:
            extremo = list(max(sorted(base), key=lambda punto: (punto[eje], sum(punto))))
            extremo[eje] += 1
            forma = base | {tuple(extremo)}
            minimos = [min(punto[i] for punto in forma) for i in ejes]
            familia.append(tuple(sorted(tuple(punto[i] - minimos[i] for i in ejes) for punto in forma)))
        if len(set(familia)) != 3 or usados.intersection(familia):
            continue
        usados.update(familia)
        rng.shuffle(familia)
        originales.append(familia[0])
        distractores.append(familia[1])
        distractores_diferidos.append(familia[2])

    def reconocimiento(nuevos):
        ensayos = [(forma, True) for forma in originales] + [(forma, False) for forma in nuevos]
        rng.shuffle(ensayos)
        return ensayos

    return originales, reconocimiento(distractores), reconocimiento(distractores_diferidos)


def puntuar(respuestas, ensayos):
    if not isinstance(respuestas, list) or len(respuestas) != FIGURAS * 2:
        raise ValueError("Completa las respuestas de las 20 figuras.")
    registros = []
    for respuesta, (_, esperada) in zip(respuestas, ensayos):
        if not isinstance(respuesta, dict) or type(respuesta.get("vista")) is not bool:
            raise ValueError("Cada figura debe tener una respuesta válida.")
        tiempo = respuesta.get("tiempo_ms")
        if type(tiempo) not in (int, float) or not 0 <= tiempo <= 2**53 - 1:
            raise ValueError("Cada figura debe tener un tiempo válido en milisegundos.")
        registros.append({"vista": respuesta["vista"], "esperada": esperada, "tiempo_ms": round(tiempo, 3)})
    return {
        "correctas": sum(r["vista"] == r["esperada"] for r in registros),
        "reconocidas": sum(r["vista"] and r["esperada"] for r in registros),
        "falsos_positivos": sum(r["vista"] and not r["esperada"] for r in registros),
        "promedio_ms": round(mean(r["tiempo_ms"] for r in registros), 3),
        "respuestas": registros,
    }
