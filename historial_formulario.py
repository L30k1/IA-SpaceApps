import json
from datetime import datetime
from itertools import zip_longest
from math import isfinite
from uuid import uuid4

from calendario_mision import ZONA_MISION
from database.expedientes import SIGNOS, leer_expediente


SECCIONES = (
    ("misiones", "Misiones", (
        ("id", "ID de misión", "text"), ("fecha_inicio", "Inicio", "date"), ("fecha_fin", "Fin", "date"),
    )),
    ("alergias", "Alergias", (
        ("sustancia", "Sustancia", "text"), ("reaccion", "Reacción", "text"), ("gravedad", "Gravedad", "text"),
        ("fecha", "Fecha", "date"), ("confirmacion", "Confirmación", "text"),
        ("reportado_por", "Reportado por", "text"), ("verificado_por", "Verificado por", "text"),
    )),
    ("antecedentes", "Antecedentes", (
        ("condicion", "Condición", "text"), ("fecha_inicio", "Inicio", "date"), ("estado", "Estado", "text"),
        ("observaciones", "Observaciones", "textarea"), ("reportado_por", "Reportado por", "text"),
        ("verificado_por", "Verificado por", "text"),
    )),
    ("medicamentos", "Medicamentos", (
        ("nombre", "Medicamento", "text"), ("dosis", "Dosis", "number"), ("unidad", "Unidad de la dosis", "text"),
        ("via", "Vía", "text"), ("frecuencia", "Frecuencia", "text"), ("motivo", "Motivo", "text"),
        ("fecha_inicio", "Inicio", "date"), ("fecha_fin", "Fin", "date"), ("estado", "Estado", "text"),
        ("reportado_por", "Reportado por", "text"), ("verificado_por", "Verificado por", "text"),
    )),
    ("chequeos", "Chequeos anteriores", (
        ("fecha_hora", "Fecha y hora (Ciudad de México)", "datetime-local"), ("mision_id", "ID de misión", "text"),
        ("fase", "Fase de misión", "fase"), ("motivo", "Motivo", "text"), ("actividad", "Actividad", "text"),
        ("frecuencia_cardiaca", "Frecuencia cardíaca (lpm)", "number"), ("spo2", "SpO₂ (%)", "number"),
        ("temperatura", "Temperatura (°C)", "number"), ("estado_revision", "Estado de revisión", "text"),
        ("accion_acordada", "Acción acordada", "text"), ("fecha_seguimiento", "Fecha de seguimiento", "date"),
    )),
)


def filas_formulario(formulario):
    filas = {}
    for grupo, _, campos in SECCIONES:
        columnas = [formulario.getlist(f"{grupo}.{campo}") for campo, _, _ in campos]
        nombres = [campo for campo, _, _ in campos]
        filas[grupo] = [
            {campo: valor for campo, valor in zip(nombres, valores) if valor.strip()}
            for valores in zip_longest(*columnas, fillvalue="")
        ]
    return filas


def generar_historial(formulario, filas):
    expediente = {
        "_id": formulario.get("astronauta_id", ""), "astronauta": {"nombre": formulario.get("nombre", "")},
        "estado_alergias": formulario.get("estado_alergias", "").strip(),
        "diario_psicologico": [], "semanal_psicologico": [], "praxis_motora": [],
        "memoria_visual": [], "orientacion_linea": [],
    }
    for grupo, _, _ in SECCIONES:
        expediente[grupo] = [
            {campo: valor.strip() for campo, valor in fila.items() if valor.strip()}
            for fila in filas[grupo] if any(valor.strip() for valor in fila.values())
        ]
    for medicamento in expediente["medicamentos"]:
        if "dosis" in medicamento:
            try:
                medicamento["dosis"] = float(medicamento["dosis"])
                if not isfinite(medicamento["dosis"]):
                    raise ValueError
            except ValueError:
                raise ValueError("Escribe la dosis como número y su unidad en el campo separado.") from None
    for chequeo in expediente["chequeos"]:
        try:
            fecha = datetime.fromisoformat(chequeo.get("fecha_hora", ""))
        except ValueError:
            raise ValueError("Cada chequeo anterior necesita fecha y hora.") from None
        chequeo["id"] = f"chequeo-{uuid4().hex}"
        chequeo["fecha_hora"] = (fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=ZONA_MISION)).isoformat()
        try:
            chequeo["mediciones"] = [
                {"tipo": tipo, "unidad": unidad, "valor": float(chequeo.pop(tipo))}
                for tipo, (_, unidad) in SIGNOS.items() if tipo in chequeo
            ]
        except ValueError:
            raise ValueError("Escribe los signos vitales como números.") from None
        evaluacion = {campo: chequeo.pop(campo) for campo in (
            "estado_revision", "accion_acordada", "fecha_seguimiento",
        ) if campo in chequeo}
        if evaluacion:
            chequeo["evaluacion"] = evaluacion
    return leer_expediente(json.dumps(expediente, ensure_ascii=False))
