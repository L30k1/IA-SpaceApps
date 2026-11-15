import os
import re

import httpx2


def configuracion_elevenlabs():
    clave = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voz = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    modelo = os.getenv("ELEVENLABS_MODEL_ID", "").strip() or "eleven_multilingual_v2"
    if clave and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", voz):
        return clave, voz, modelo
    return None


def sintetizar_elevenlabs(texto, configuracion):
    clave, voz, modelo = configuracion
    respuesta = httpx2.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz}",
        params={"output_format": "mp3_22050_32"},
        headers={"xi-api-key": clave, "Accept": "audio/mpeg"},
        json={"text": texto, "model_id": modelo},
        timeout=10,
    )
    respuesta.raise_for_status()
    if respuesta.headers.get("Content-Type", "").split(";", 1)[0].lower() != "audio/mpeg" or not respuesta.content:
        raise ValueError("ElevenLabs no devolvió audio.")
    return respuesta.content
