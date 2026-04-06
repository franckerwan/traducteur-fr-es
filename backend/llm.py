import os
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL = "gemini-2.5-flash-lite"
MAX_TOKENS = 500

SYSTEM_PROMPT = """Tu es une machine de traduction français↔espagnol. Tu ne fais RIEN d'autre que traduire.

RÈGLE UNIQUE : Tout texte en français → tu réponds en espagnol. Tout texte en espagnol → tu réponds en français.

INTERDIT :
- Ne corrige JAMAIS l'orthographe ou la grammaire du texte source
- Ne donne JAMAIS d'explication, commentaire, alternative ou variante
- Ne mets JAMAIS de guillemets, préfixe ou suffixe autour de ta réponse
- Ne dis JAMAIS "Voici la traduction" ou quoi que ce soit de similaire
- Ne propose JAMAIS plusieurs versions

Ta réponse = UNIQUEMENT le texte traduit dans l'autre langue. RIEN d'autre.

Exemples (entrée → ta réponse exacte) :
salut → Hola
comment vas tu → Cómo estás
Hola → Salut
Cómo estás → Comment vas-tu
J'aime les chats → Me gustan los gatos
Me gustan los gatos → J'aime les chats
Où est la gare → Dónde está la estación
Buenos días señor → Bonjour monsieur
je ne comprends pas → No entiendo
No entiendo → Je ne comprends pas
"""

_config = genai.types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.0,
    max_output_tokens=MAX_TOKENS,
)


def _make_prompt(text: str) -> str:
    return f"Traduis : {text}"


def translate(text: str) -> str:
    """Traduit le texte FR→ES ou ES→FR. Retourne uniquement la traduction."""
    response = client.models.generate_content(
        model=MODEL,
        contents=[{"role": "user", "parts": [{"text": _make_prompt(text)}]}],
        config=_config,
    )
    return response.text.strip()


def translate_stream(text: str):
    """Traduit en streaming pour une réponse progressive."""
    for chunk in client.models.generate_content_stream(
        model=MODEL,
        contents=[{"role": "user", "parts": [{"text": _make_prompt(text)}]}],
        config=_config,
    ):
        if chunk.text:
            yield chunk.text
