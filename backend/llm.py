import os
import re
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL = "gemini-3.1-flash"
MAX_TOKENS = 256

SYSTEM_PROMPT = (
    "Traducteur FR↔ES strict. "
    "Texte français → répondre en espagnol. Texte espagnol → répondre en français. "
    "Répondre UNIQUEMENT la traduction, sans guillemets, sans explication, sans préfixe, sans correction."
)

_config = genai.types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.0,
    max_output_tokens=MAX_TOKENS,
    top_k=1,
)

# Patterns parasites que le modèle peut ajouter
_NOISE_RE = re.compile(
    r'^(?:"|\'|«|»|"|"|Traducción:\s*|Traduction:\s*|Voici la traduction:\s*)+|(?:"|\'|«|»|"|")+$',
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Supprime guillemets, préfixes parasites et espaces superflus."""
    text = text.strip()
    text = _NOISE_RE.sub("", text)
    return text.strip()


def _make_contents(text: str) -> list:
    return [{"role": "user", "parts": [{"text": text}]}]


def translate(text: str) -> str:
    """Traduit le texte FR→ES ou ES→FR. Retourne uniquement la traduction."""
    response = client.models.generate_content(
        model=MODEL,
        contents=_make_contents(text),
        config=_config,
    )
    return _clean(response.text)


def translate_stream(text: str):
    """Traduit en streaming pour une réponse progressive."""
    for chunk in client.models.generate_content_stream(
        model=MODEL,
        contents=_make_contents(text),
        config=_config,
    ):
        if chunk.text:
            yield chunk.text
