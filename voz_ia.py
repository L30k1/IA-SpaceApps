import os
import re
from struct import pack

import httpx2


ERRORES_PROVEEDOR = {
    "invalid_api_key": "ELEVENLABS_CLAVE",
    "missing_api_key": "ELEVENLABS_CLAVE",
    "insufficient_permissions": "ELEVENLABS_PERMISO",
    "missing_permissions": "ELEVENLABS_PERMISO",
    "quota_exceeded": "ELEVENLABS_CREDITOS",
    "insufficient_credits": "ELEVENLABS_CREDITOS",
    "voice_not_found": "ELEVENLABS_VOZ",
    "invalid_voice_id": "ELEVENLABS_VOZ",
    "voice_access_denied": "ELEVENLABS_PLAN",
    "feature_not_available": "ELEVENLABS_PLAN",
    "subscription_required": "ELEVENLABS_PLAN",
    "paid_plan_required": "ELEVENLABS_PLAN",
    "model_access_denied": "ELEVENLABS_PLAN",
    "model_not_found": "ELEVENLABS_MODELO",
    "invalid_model_id": "ELEVENLABS_MODELO",
}
ERRORES_HTTP = {
    400: "ELEVENLABS_PARAMETROS", 401: "ELEVENLABS_CLAVE", 402: "ELEVENLABS_CREDITOS",
    403: "ELEVENLABS_ACCESO", 404: "ELEVENLABS_VOZ", 422: "ELEVENLABS_PARAMETROS",
    429: "ELEVENLABS_LIMITE",
}
MENSAJES_ELEVENLABS = {
    "ELEVENLABS_CLAVE": "ElevenLabs rechazó la clave. Revisa ELEVENLABS_API_KEY en Render.",
    "ELEVENLABS_PERMISO": "La clave de ElevenLabs requiere permiso de Text to Speech.",
    "ELEVENLABS_CREDITOS": "ElevenLabs indica que faltan créditos. Revisa el saldo y el límite de la clave.",
    "ELEVENLABS_VOZ": "ElevenLabs no encontró la voz. Copia el Voice ID en ELEVENLABS_VOICE_ID.",
    "ELEVENLABS_PLAN": "Tu cuenta de ElevenLabs no tiene acceso a esa voz o modelo desde la API.",
    "ELEVENLABS_MODELO": "ElevenLabs rechazó el modelo. Revisa ELEVENLABS_MODEL_ID en Render.",
    "ELEVENLABS_PARAMETROS": "ElevenLabs rechazó los parámetros. Revisa el ID de voz y el modelo.",
    "ELEVENLABS_ACCESO": "ElevenLabs rechazó el acceso. Revisa los permisos de la clave y de la voz.",
    "ELEVENLABS_LIMITE": "ElevenLabs limitó temporalmente las solicitudes. Inténtalo de nuevo más tarde.",
    "ELEVENLABS_RED": "El servidor no pudo conectar con ElevenLabs a tiempo.",
    "ELEVENLABS_AUDIO": "ElevenLabs devolvió una respuesta sin audio válido.",
    "ELEVENLABS_SERVICIO": "ElevenLabs no pudo generar el audio en este momento.",
}

# ID3v1.1 lleva la procedencia dentro del MP3, incluso al guardarlo fuera de MediSpace.
ETIQUETA_AUDIO_IA = pack(
    "3s30s30s30s4s28sBBB", b"TAG", b"Audio generado por IA", b"ElevenLabs",
    b"MediSpace", b"", b"Generado por IA - ElevenLabs", 0, 0, 255,
)


class ErrorElevenLabs(Exception):
    def __init__(self, codigo, estado_http=None):
        self.codigo = codigo
        self.estado_http = estado_http
        super().__init__(codigo)


def configuracion_elevenlabs():
    clave = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voz = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    modelo = os.getenv("ELEVENLABS_MODEL_ID", "").strip() or "eleven_multilingual_v2"
    if clave and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", voz):
        return clave, voz, modelo
    return None


def sintetizar_elevenlabs(texto, configuracion):
    clave, voz, modelo = configuracion
    if not re.fullmatch(r"[!-~]+", clave):
        raise ErrorElevenLabs("ELEVENLABS_CLAVE")
    try:
        respuesta = httpx2.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voz}",
            params={"output_format": "mp3_22050_32"},
            headers={"xi-api-key": clave, "Accept": "audio/mpeg"},
            json={"text": texto, "model_id": modelo},
            timeout=10,
        )
    except httpx2.RequestError:
        raise ErrorElevenLabs("ELEVENLABS_RED") from None
    if not respuesta.is_success:
        try:
            datos = respuesta.json()
        except (ValueError, RecursionError):
            datos = None
        if isinstance(datos, dict):
            for detalle in (datos.get("detail"), datos.get("error"), datos):
                if not isinstance(detalle, dict):
                    continue
                for campo in ("code", "status"):
                    valor = detalle.get(campo)
                    if isinstance(valor, str) and valor in ERRORES_PROVEEDOR:
                        raise ErrorElevenLabs(ERRORES_PROVEEDOR[valor], respuesta.status_code)
        raise ErrorElevenLabs(ERRORES_HTTP.get(respuesta.status_code, "ELEVENLABS_SERVICIO"), respuesta.status_code)
    mime = respuesta.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if mime not in {"audio/mpeg", "audio/mp3"} or not respuesta.content:
        raise ErrorElevenLabs("ELEVENLABS_AUDIO", respuesta.status_code)
    audio = respuesta.content
    if audio[-128:-125] == b"TAG":
        audio = audio[:-128]
    return audio + ETIQUETA_AUDIO_IA
