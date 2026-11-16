import json
from pathlib import Path

from flask import has_request_context, request


LANGUAGES = ("es", "en")
DEFAULT_LANGUAGE = "en"
ENGLISH_BY_LEGACY_MESSAGE = json.loads(Path(__file__).with_name("translations.json").read_text(encoding="utf-8"))
SPANISH_BY_ENGLISH_MESSAGE = {}
for spanish, english in ENGLISH_BY_LEGACY_MESSAGE.items():
    if english in SPANISH_BY_ENGLISH_MESSAGE:
        SPANISH_BY_ENGLISH_MESSAGE[english] = english
    else:
        SPANISH_BY_ENGLISH_MESSAGE[english] = spanish


def requested_language():
    language = request.args.get("lang")
    return language if language in LANGUAGES else None


def current_language():
    if not has_request_context():
        return DEFAULT_LANGUAGE
    preferred_language = request.cookies.get("medispace_lang")
    return requested_language() or (preferred_language if preferred_language in LANGUAGES else DEFAULT_LANGUAGE)


def translate(message_text, **fields):
    catalog = ENGLISH_BY_LEGACY_MESSAGE if current_language() == "en" else SPANISH_BY_ENGLISH_MESSAGE
    message_text = catalog.get(str(message_text), str(message_text))
    return message_text.format(**fields) if fields else message_text


def short_date(timestamp):
    return timestamp.strftime("%b %d, %Y" if current_language() == "en" else "%d/%m/%Y")
