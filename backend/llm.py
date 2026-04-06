import os
import re
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL = "gemini-3-flash-preview"
MAX_TOKENS = 512
THINKING_BUDGET = 2048

SYSTEM_PROMPT = (
    "Tu es un traducteur FR↔ES expert en messages WhatsApp. "
    "Texte espagnol → traduis en français. Texte français → traduis en espagnol. "
    "Les messages contiennent : argot, abréviations SMS, fautes, accents manquants, "
    "mots collés, onomatopées (jajaja=mdr, xd=lol), Spanglish, langage de rue. "
    "Traduis le sens complet du message avec le même ton familier. "
    "IMPORTANT : donne toujours la traduction COMPLÈTE en une seule réponse courte. "
    "Jamais d'alternatives, guillemets, préfixes ou explications. Juste la traduction."
)

_config = genai.types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.0,
    max_output_tokens=MAX_TOKENS,
    thinking_config=genai.types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
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
