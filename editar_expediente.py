import json
from hashlib import sha256

from database.expedientes import leer_expediente


CAMPOS_EDITABLES = ("alergias", "antecedentes", "medicamentos", "estado_alergias", "referencias_monitoreo", "misiones")
CAMPOS_MISION = ("id", "fecha_inicio", "fecha_fin")
META_EJERCICIO = "ejercicio_min_diarios"


class EdicionDesactualizada(ValueError):
    pass


def datos_editables(expediente):
    datos = {campo: expediente[campo] for campo in CAMPOS_EDITABLES if campo in expediente}
    datos.setdefault("estado_alergias", "")
    datos.setdefault("referencias_monitoreo", {})
    datos["misiones"] = [
        {**{campo: mision[campo] for campo in CAMPOS_MISION if campo in mision},
         META_EJERCICIO: mision.get(META_EJERCICIO)}
        for mision in expediente["misiones"]
    ]
    return datos


def version_edicion(datos):
    return sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def aplicar_edicion(expediente, version, contenido):
    editables = datos_editables(expediente)
    if version != version_edicion(editables):
        raise EdicionDesactualizada("El expediente cambió mientras lo editabas. Copia tus cambios y vuelve a abrir el editor.")
    try:
        nuevos = json.loads(contenido)
        json.dumps(nuevos, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, RecursionError):
        raise ValueError("El archivo no contiene un JSON válido.") from None
    if not isinstance(nuevos, dict) or nuevos.keys() - set(CAMPOS_EDITABLES):
        raise ValueError("Edita únicamente los campos que aparecen en este editor.")
    if "estado_alergias" in nuevos and not isinstance(nuevos["estado_alergias"], str):
        raise ValueError("El estado de alergias debe ser texto.")
    misiones = nuevos.get("misiones", [])
    if not isinstance(misiones, list) or not all(isinstance(m, dict) for m in misiones):
        raise ValueError("Las misiones del editor deben ser una lista.")
    fechas_originales = [{k: v for k, v in m.items() if k != META_EJERCICIO} for m in editables["misiones"]]
    fechas_enviadas = [{k: v for k, v in m.items() if k != META_EJERCICIO} for m in misiones]
    if fechas_enviadas != fechas_originales:
        raise ValueError("En las misiones puedes editar el mínimo diario de ejercicio.")

    nuevos.setdefault("estado_alergias", "")
    nuevos.setdefault("referencias_monitoreo", {})
    for mision in misiones:
        if mision.get(META_EJERCICIO) is None:
            mision.pop(META_EJERCICIO, None)
    validado = leer_expediente(json.dumps({"_id": expediente["_id"], "astronauta": expediente["astronauta"], **nuevos}))
    actualizado = {campo: valor for campo, valor in expediente.items() if campo not in CAMPOS_EDITABLES}
    actualizado.update({campo: validado[campo] for campo in CAMPOS_EDITABLES if campo in validado})
    actualizado["misiones"] = [
        {**{k: v for k, v in original.items() if k != META_EJERCICIO},
         **({META_EJERCICIO: nueva[META_EJERCICIO]} if META_EJERCICIO in nueva else {})}
        for original, nueva in zip(expediente["misiones"], validado["misiones"])
    ]
    return actualizado
