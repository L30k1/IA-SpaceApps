import re

from werkzeug.security import check_password_hash, generate_password_hash


EDIT_KEY_FIELD = "clave_edicion_hash"
EDIT_KEY_METHOD = "scrypt:32768:8:1"


def create_edit_key(form_data):
    edit_key = form_data.get("llave_edicion", "")
    if not 8 <= len(edit_key) <= 128 or not edit_key.strip():
        raise ValueError("Enter an editing key between 8 and 128 characters.")
    if edit_key != form_data.get("confirmar_llave", ""):
        raise ValueError("The editing keys do not match.")
    return generate_password_hash(edit_key, method=EDIT_KEY_METHOD, salt_length=16)


def extract_edit_key(medical_record):
    value = medical_record.pop(EDIT_KEY_FIELD, None)
    if value is not None and (
        not isinstance(value, str)
        or not re.fullmatch(r"scrypt:32768:8:1\$[a-zA-Z0-9]{16}\$[0-9a-f]{128}", value)
    ):
        raise ValueError("The editing key in the JSON file has an invalid format.")
    return value


def verify_credential(stored_hash, value):
    return bool(stored_hash and 0 < len(value) <= 128 and check_password_hash(stored_hash, value))
