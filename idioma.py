import json
from pathlib import Path

from flask import has_request_context, request


IDIOMAS = ("es", "en")
CATALOGO = json.loads(Path(__file__).with_name("traducciones.json").read_text(encoding="utf-8"))


def idioma_elegido():
    idioma = request.args.get("lang")
    return idioma if idioma in IDIOMAS else None


def idioma_actual():
    if not has_request_context():
        return "es"
    return idioma_elegido() or ("en" if request.cookies.get("medispace_lang") == "en" else "es")


def traducir(texto, **campos):
    texto = CATALOGO.get(str(texto), str(texto)) if idioma_actual() == "en" else str(texto)
    return texto.format(**campos) if campos else texto


def fecha_corta(fecha):
    return fecha.strftime("%b %d, %Y" if idioma_actual() == "en" else "%d/%m/%Y")
