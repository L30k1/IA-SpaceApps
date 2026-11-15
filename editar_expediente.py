import json
from hashlib import sha256

from historial_formulario import SECCIONES, generar_historial


GRUPOS_EDITABLES = ("alergias", "antecedentes", "medicamentos")
CAMPOS_EDITABLES = (*GRUPOS_EDITABLES, "estado_alergias", "referencias_monitoreo", "misiones")
SECCIONES_EDICION = tuple(seccion for seccion in SECCIONES if seccion[0] != "chequeos")
META_EJERCICIO = "ejercicio_min_diarios"


class EdicionDesactualizada(ValueError):
    pass


def version_edicion(expediente):
    datos = {campo: expediente.get(campo) for campo in CAMPOS_EDITABLES}
    return sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def filas_mision(expediente, metas=None):
    return [
        {"id": mision["id"], "fecha_inicio": mision.get("fecha_inicio") or "",
         "fecha_fin": mision.get("fecha_fin") or "",
         META_EJERCICIO: metas[i] if metas is not None and i < len(metas) else mision.get(META_EJERCICIO, "")}
        for i, mision in enumerate(expediente["misiones"])
    ]


def formulario_edicion(expediente):
    formulario = {"estado_alergias": expediente.get("estado_alergias", "")}
    for tipo, rango in expediente.get("referencias_monitoreo", {}).items():
        if rango:
            formulario.update({f"referencias.{tipo}.{extremo}": valor for extremo, valor in rango.items()})
    filas = {"misiones": filas_mision(expediente)}
    for grupo in GRUPOS_EDITABLES:
        filas[grupo] = [
            {**fila, "_fila_original": str(i)} for i, fila in enumerate(expediente.get(grupo, []))
        ] or [{}]
    return formulario, filas


def aplicar_edicion(expediente, version, formulario, filas, metas):
    if version != version_edicion(expediente):
        raise EdicionDesactualizada("El expediente cambió mientras lo editabas. Vuelve a abrir el editor antes de guardar.")
    if len(metas) != len(expediente["misiones"]):
        raise ValueError("Revisa el mínimo diario de cada misión.")
    entrada = {
        **formulario, "nombre": expediente["astronauta"]["nombre"], "astronauta_id": expediente["_id"],
    }
    datos = {"misiones": [
        {campo: str(valor) for campo, valor in fila.items()} for fila in filas_mision(expediente, metas)
    ], "chequeos": []}
    usadas = {}
    for grupo in GRUPOS_EDITABLES:
        usadas[grupo] = [fila for fila in filas[grupo] if any(k != "_fila_original" and v for k, v in fila.items())]
        datos[grupo] = [{k: v for k, v in fila.items() if k != "_fila_original"} for fila in usadas[grupo]]

    validado = generar_historial(entrada, datos)
    actualizado = {**expediente, "estado_alergias": validado["estado_alergias"],
                   "referencias_monitoreo": validado.get("referencias_monitoreo", {})}
    for grupo, _, campos in SECCIONES_EDICION:
        if grupo not in GRUPOS_EDITABLES:
            continue
        editables = {campo for campo, _, _ in campos}
        originales = expediente.get(grupo, [])
        actualizados = []
        indices = set()
        for fila, nueva in zip(usadas[grupo], validado[grupo]):
            indice = fila.get("_fila_original")
            if indice is None:
                actualizados.append(nueva)
                continue
            if not indice.isascii() or not indice.isdigit() or len(indice) > 6:
                raise ValueError("Una fila del formulario no es válida.")
            i = int(indice)
            if i >= len(originales) or i in indices:
                raise ValueError("Una fila del formulario no es válida.")
            indices.add(i)
            extras = {campo: valor for campo, valor in originales[i].items() if campo not in editables}
            actualizados.append({**extras, **nueva})
        actualizado[grupo] = actualizados
    actualizado["misiones"] = [
        {**{k: v for k, v in original.items() if k != META_EJERCICIO},
         **({META_EJERCICIO: nueva[META_EJERCICIO]} if META_EJERCICIO in nueva else {})}
        for original, nueva in zip(expediente["misiones"], validado["misiones"])
    ]
    return actualizado
