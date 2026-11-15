from itertools import combinations
from random import Random
from statistics import mean

from idioma import traducir as t


CAMPO_LOT = "orientacion_linea"
VERSION_LOT = "medispace-lot-1"
ENSAYOS_LOT = 12
ANGULOS_LOT = tuple(range(165, 14, -15))
OPCIONES_LOT = range(1, len(ANGULOS_LOT) + 1)


def pares_lot(identificador):
    return Random(identificador).sample(list(combinations(OPCIONES_LOT, 2)), ENSAYOS_LOT)


def puntuar_lot(identificador, respuestas):
    if not isinstance(respuestas, list) or len(respuestas) != ENSAYOS_LOT:
        raise ValueError(t("Completa los {cantidad} pares de líneas.", cantidad=ENSAYOS_LOT))
    ensayos = []
    for respuesta, esperado in zip(respuestas, pares_lot(identificador)):
        if not isinstance(respuesta, dict):
            raise ValueError("La respuesta de orientación no es válida.")
        seleccion = respuesta.get("lineas")
        if (not isinstance(seleccion, list) or len(seleccion) != 2
                or any(type(n) is not int or n not in OPCIONES_LOT for n in seleccion)
                or seleccion[0] == seleccion[1]):
            raise ValueError("Selecciona dos números de línea distintos en cada par.")
        tiempo = respuesta.get("tiempo_ms")
        if type(tiempo) not in (int, float) or not 0 <= tiempo <= 2**53 - 1:
            raise ValueError("Cada par debe tener un tiempo válido en milisegundos.")
        ensayos.append({
            "lineas": sorted(seleccion), "tiempo_ms": round(tiempo, 3),
            "coincidencias": len(set(seleccion).intersection(esperado)),
        })
    return {
        "pares_correctos": sum(r["coincidencias"] == 2 for r in ensayos),
        "lineas_correctas": sum(r["coincidencias"] for r in ensayos),
        "promedio_ms": round(mean(r["tiempo_ms"] for r in ensayos), 3),
        "respuestas": ensayos,
    }
