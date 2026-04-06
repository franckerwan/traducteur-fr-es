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

# Détecte le format WhatsApp : [date heure] expéditeur: message
_WHATSAPP_LINE_RE = re.compile(
    r'^(\[.+?\]\s+.+?:\s*)(.+)$'
)


def _clean(text: str) -> str:
    """Supprime guillemets, préfixes parasites et espaces superflus."""
    text = text.strip()
    text = _NOISE_RE.sub("", text)
    return text.strip()


def _is_whatsapp_block(text: str) -> bool:
    """Détecte si le texte est un bloc de conversation WhatsApp."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    matches = sum(1 for l in lines if _WHATSAPP_LINE_RE.match(l))
    return matches >= len(lines) * 0.5


def _parse_whatsapp(text: str) -> list:
    """Parse un bloc WhatsApp et retourne [(préfixe, message), ...]."""
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = _WHATSAPP_LINE_RE.match(line)
        if m:
            results.append((m.group(1), m.group(2)))
        else:
            results.append(("", line))
    return results


def _make_contents(text: str) -> list:
    return [{"role": "user", "parts": [{"text": text}]}]


def _translate_single(text: str) -> str:
    """Traduit un seul message."""
    response = client.models.generate_content(
        model=MODEL,
        contents=_make_contents(text),
        config=_config,
    )
    return _clean(response.text)


def translate(text: str) -> str:
    """Traduit le texte FR→ES ou ES→FR. Gère les blocs WhatsApp."""
    if _is_whatsapp_block(text):
        parsed = _parse_whatsapp(text)
        translated_lines = []
        for prefix, msg in parsed:
            translated_msg = _translate_single(msg)
            translated_lines.append(f"{prefix}{translated_msg}")
        return "\n".join(translated_lines)
    return _translate_single(text)


def translate_stream(text: str):
    """Traduit en streaming. Pour les blocs WhatsApp, traduit ligne par ligne."""
    if _is_whatsapp_block(text):
        parsed = _parse_whatsapp(text)
        for i, (prefix, msg) in enumerate(parsed):
            translated_msg = _translate_single(msg)
            line = f"{prefix}{translated_msg}"
            if i > 0:
                yield "\n"
            yield line
    else:
        for chunk in client.models.generate_content_stream(
            model=MODEL,
            contents=_make_contents(text),
            config=_config,
        ):
            if chunk.text:
                yield chunk.text
