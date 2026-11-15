from itertools import product
from random import Random
from statistics import median


CAMPO_EMOCIONES = "reconocimiento_emociones"
VERSION_EMOCIONES = "medispace-ert-1"
EXPOSICION_EMOCIONES_MS = 750
EMOCIONES = {
    "alegria": "Alegría", "tristeza": "Tristeza", "ira": "Ira",
    "miedo": "Miedo", "asco": "Asco", "sorpresa": "Sorpresa",
}
INTENSIDADES = {"leve": "Leve", "intensa": "Intensa"}
LAMINAS = ("rostros-a.png", "rostros-b.png")


def estimulos_emociones(identificador):
    ensayos = [
        {"lamina": lamina, "casilla": casilla, "emocion": emocion, "intensidad": intensidad}
        for lamina in LAMINAS
        for casilla, (emocion, intensidad) in enumerate(product(EMOCIONES, INTENSIDADES))
    ]
    Random(identificador).shuffle(ensayos)
    return ensayos


def puntuar_emociones(identificador, respuestas):
    ensayos = estimulos_emociones(identificador)
    if not isinstance(respuestas, list) or len(respuestas) != len(ensayos):
        raise ValueError("La ronda de reconocimiento facial está incompleta.")
    por_emocion = {emocion: {"aciertos": 0, "total": 0} for emocion in EMOCIONES}
    por_intensidad = {nivel: {"aciertos": 0, "total": 0} for nivel in INTENSIDADES}
    respuestas_validas = []
    tiempos = []
    for ensayo, respuesta in zip(ensayos, respuestas):
        if not isinstance(respuesta, dict):
            raise ValueError("La respuesta de reconocimiento facial no es válida.")
        seleccion, tiempo = respuesta.get("emocion"), respuesta.get("tiempo_ms")
        if (not isinstance(seleccion, str) or seleccion not in EMOCIONES
                or type(tiempo) not in (int, float) or not 0 <= tiempo <= 2**53 - 1):
            raise ValueError("La respuesta de reconocimiento facial no es válida.")
        tiempo = round(tiempo, 3)
        acierto = seleccion == ensayo["emocion"]
        for grupo in (por_emocion[ensayo["emocion"]], por_intensidad[ensayo["intensidad"]]):
            grupo["aciertos"] += acierto
            grupo["total"] += 1
        if acierto:
            tiempos.append(tiempo)
        respuestas_validas.append({"emocion": seleccion, "tiempo_ms": tiempo})
    return {
        "aciertos": len(tiempos),
        "total": len(ensayos),
        "precision_pct": round(100 * len(tiempos) / len(ensayos), 2),
        "mediana_aciertos_ms": median(tiempos) if tiempos else None,
        "por_emocion": por_emocion,
        "por_intensidad": por_intensidad,
        "respuestas": respuestas_validas,
    }
