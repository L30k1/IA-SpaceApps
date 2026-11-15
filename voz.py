import os
import re

import httpx2


def configuracion_elevenlabs():
    clave = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voz = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    return (clave, voz) if clave and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", voz) else None


def sintetizar_elevenlabs(texto, configuracion):
    clave, voz = configuracion
    respuesta = httpx2.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz}",
        headers={"xi-api-key": clave, "Accept": "audio/mpeg"},
        params={"output_format": "mp3_22050_32"},
        json={"text": texto, "model_id": "eleven_flash_v2_5", "language_code": "es"},
        timeout=12,
    )
    respuesta.raise_for_status()
    if not respuesta.content or respuesta.headers.get("Content-Type", "").split(";")[0].strip().lower() != "audio/mpeg":
        raise ValueError("El servicio no devolvió audio MP3.")
    return respuesta.content
