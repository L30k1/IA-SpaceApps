import re

from werkzeug.security import check_password_hash, generate_password_hash


CAMPO_LLAVE = "clave_edicion_hash"
METODO_LLAVE = "scrypt:32768:8:1"


def preparar_llave(formulario):
    llave = formulario.get("llave_edicion", "")
    if not 8 <= len(llave) <= 128 or not llave.strip():
        raise ValueError("Escribe una llave de edición de 8 a 128 caracteres.")
    if llave != formulario.get("confirmar_llave", ""):
        raise ValueError("Las llaves de edición no coinciden.")
    return generate_password_hash(llave, method=METODO_LLAVE, salt_length=16)


def llave_del_expediente(expediente):
    valor = expediente.pop(CAMPO_LLAVE, None)
    if valor is not None and (
        not isinstance(valor, str)
        or not re.fullmatch(r"scrypt:32768:8:1\$[a-zA-Z0-9]{16}\$[0-9a-f]{128}", valor)
    ):
        raise ValueError("La llave de edición del archivo JSON no tiene un formato válido.")
    return valor


def verificar_credencial(hash_guardado, valor):
    return bool(hash_guardado and 0 < len(valor) <= 128 and check_password_hash(hash_guardado, valor))
