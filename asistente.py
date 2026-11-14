import os

from google import genai
from google.genai import types

cliente = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def generar_pregunta(respuesta: str) -> str:
    resultado = cliente.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=respuesta,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Estás en una demostración con un astronauta ficticio. "
                "A partir de su respuesta, haz una sola pregunta breve "
                "de seguimiento en español. Limítate a aclarar lo que "
                "dijo. Evita diagnósticos y recomendaciones médicas."
            )
        ),
    )
    return resultado.text or "¿Puedes contarme un poco más?"


if __name__ == "__main__":
    respuesta = input("Escribe una respuesta ficticia: ").strip()
    if respuesta:
        print("Asistente:", generar_pregunta(respuesta))