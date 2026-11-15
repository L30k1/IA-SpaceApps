from datetime import datetime, timedelta
from random import Random
from statistics import mean
from uuid import uuid4


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


def avanzar(borrador, registros, accion, identificador, respuestas, ahora):
    if accion == "iniciar":
        return borrador or {"id": uuid4().hex, "fase": "aprendizaje", "inicio": ahora.isoformat()}, None, None
    if accion == "diferido" and any(r["id"] == identificador for r in registros):
        return borrador, None, identificador
    if borrador is None or borrador["id"] != identificador:
        raise ValueError("Esta prueba ya no está activa. Vuelve a la página de aprendizaje visual de objetos.")
    fase = borrador["fase"]
    if accion == "cancelar":
        return None, None, None
    if accion == "inmediato":
        if fase != "aprendizaje":
            return borrador, None, None
        if (ahora - datetime.fromisoformat(borrador["inicio"])).total_seconds() < FIGURAS * EXPOSICION:
            raise ValueError("Completa primero la fase de aprendizaje.")
        return {
            **borrador, "fase": "espera", "inmediato": puntuar(respuestas, estimulos(identificador)[1]),
            "fin_inmediato": ahora.isoformat(),
        }, None, None
    if accion == "abrir_diferido":
        if fase == "diferido":
            return borrador, None, None
        if fase != "espera" or ahora < datetime.fromisoformat(borrador["fin_inmediato"]) + ESPERA:
            raise ValueError("Aún no termina el intervalo de 15 minutos.")
        return {**borrador, "fase": "diferido", "inicio_diferido": ahora.isoformat()}, None, None
    if accion == "diferido" and fase == "diferido":
        inicio = datetime.fromisoformat(borrador["inicio_diferido"])
        fin_inmediato = datetime.fromisoformat(borrador["fin_inmediato"])
        return None, {
            "id": identificador, "version": VERSION_VOLT, "fecha_hora": ahora.isoformat(),
            "intervalo_segundos": (inicio - fin_inmediato).total_seconds(),
            "inmediato": borrador["inmediato"], "diferido": puntuar(respuestas, estimulos(identificador)[2]),
        }, identificador
    raise ValueError("La fase solicitada no está disponible.")
