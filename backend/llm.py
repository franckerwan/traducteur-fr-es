import os
import re
import atexit
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY manquant dans l'environnement")

client = genai.Client(api_key=api_key)

MODEL = "gemini-3-flash-preview"
MAX_TOKENS = 512
THINKING_BUDGET = 2048
THINKING_BUDGET_SHORT = 512

SYSTEM_PROMPT = (
    "Tu es un traducteur FR↔ES expert en messages WhatsApp. "
    "Texte espagnol → traduis en français. Texte français → traduis en espagnol. "
    "Si le message mélange les deux langues, traduis vers le français. "
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

_config_short = genai.types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.0,
    max_output_tokens=MAX_TOKENS,
    thinking_config=genai.types.ThinkingConfig(thinking_budget=THINKING_BUDGET_SHORT),
)

# Patterns parasites que le modèle peut ajouter
_NOISE_RE = re.compile(
    r'^(?:"|\'|«|»|\u201c|\u201d|Traducci[oó]n[^:]*:\s*|Traduction[^:]*:\s*|Voici[^:]*:\s*|Here is[^:]*:\s*|\*{1,2}|_{1,2})+|(?:"|\'|«|»|\u201c|\u201d|\*{1,2}|_{1,2}|\s*[\(\[][^\)\]]{0,20}[\)\]])+$',
    re.IGNORECASE,
)

# Détecte le format WhatsApp : [date heure] expéditeur: message
_WHATSAPP_LINE_RE = re.compile(
    r'^(\[.+?\]\s+.+?:\s*)(.+)$'
)

# Format Android sans crochets : 12/01/2024, 14:35 - Nom: message
_WHATSAPP_ANDROID_RE = re.compile(
    r'^(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}\s*-\s+.+?:\s*)(.+)$'
)

# Messages système et médias WhatsApp à ignorer (ancré au début du message)
_WHATSAPP_SKIP_RE = re.compile(
    r'^<M[eé]dias?\s+omis>$|^<Media\s+omitted>$|^<fichier\s+joint>$|'
    r'^.+\s+a\s+(cr[eé][eé]|quitt[eé]|ajout[eé]|modifi[eé])\s|'
    r'^.+\s+(created|left|added|changed)\s+the\s+',
    re.IGNORECASE,
)

# Pool de threads pour la traduction parallèle des blocs WhatsApp
_executor = ThreadPoolExecutor(max_workers=5)
atexit.register(_executor.shutdown, wait=False)


def _clean(text: str) -> str:
    """Supprime guillemets, préfixes parasites et espaces superflus."""
    text = text.strip()
    text = _NOISE_RE.sub("", text)
    return text.strip()


def _get_config(text: str):
    """Retourne la config adaptée à la longueur du message."""
    return _config_short if len(text) < 50 else _config


def _match_whatsapp_line(line: str):
    """Essaie les deux formats WhatsApp (iOS et Android)."""
    m = _WHATSAPP_LINE_RE.match(line)
    if m:
        return m
    return _WHATSAPP_ANDROID_RE.match(line)


def _is_whatsapp_block(text: str) -> bool:
    """Détecte si le texte est un bloc de conversation WhatsApp."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    matches = sum(1 for l in lines if _match_whatsapp_line(l))
    return matches >= len(lines) * 0.5


def _parse_whatsapp(text: str) -> list:
    """Parse un bloc WhatsApp et retourne [(préfixe, message, skip), ...].
    Les lignes de continuation (sans timestamp) sont rattachées au message précédent."""
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = _match_whatsapp_line(line)
        if m:
            msg = m.group(2)
            skip = bool(_WHATSAPP_SKIP_RE.search(msg))
            results.append((m.group(1), msg, skip))
        elif results:
            # Ligne de continuation : rattacher au message précédent
            prefix, prev_msg, skip = results[-1]
            results[-1] = (prefix, prev_msg + "\n" + line, skip)
        else:
            results.append(("", line, False))
    return results


def _make_contents(text: str) -> list:
    return [{"role": "user", "parts": [{"text": text}]}]


def _translate_single(text: str) -> str:
    """Traduit un seul message."""
    cfg = _get_config(text)
    response = client.models.generate_content(
        model=MODEL,
        contents=_make_contents(text),
        config=cfg,
    )
    try:
        raw = response.text
    except (ValueError, AttributeError):
        logger.warning("Réponse invalide du modèle pour: %s", text[:50])
        return text
    if not raw:
        logger.warning("Réponse vide du modèle pour: %s", text[:50])
        return text
    return _clean(raw)


def translate(text: str) -> str:
    """Traduit le texte FR→ES ou ES→FR. Gère les blocs WhatsApp en parallèle."""
    if _is_whatsapp_block(text):
        parsed = _parse_whatsapp(text)
        results = [""] * len(parsed)

        # Soumettre les traductions en parallèle
        futures = {}
        for i, (prefix, msg, skip) in enumerate(parsed):
            if skip:
                results[i] = f"{prefix}{msg}"
            else:
                futures[_executor.submit(_translate_single, msg)] = (i, prefix)

        for future in as_completed(futures):
            i, prefix = futures[future]
            try:
                translated_msg = future.result(timeout=30)
                results[i] = f"{prefix}{translated_msg}"
            except Exception as e:
                logger.warning("Erreur traduction ligne %d: %s", i, e)
                _, msg, _ = parsed[i]
                results[i] = f"{prefix}{msg}"

        return "\n".join(results)
    return _translate_single(text)


def translate_stream(text: str):
    """Traduit en streaming. Pour les blocs WhatsApp, traduit ligne par ligne."""
    if _is_whatsapp_block(text):
        parsed = _parse_whatsapp(text)
        for i, (prefix, msg, skip) in enumerate(parsed):
            if i > 0:
                yield "\n"
            if skip:
                yield f"{prefix}{msg}"
            else:
                try:
                    translated_msg = _translate_single(msg)
                    yield f"{prefix}{translated_msg}"
                except Exception as e:
                    logger.warning("Erreur streaming ligne %d: %s", i, e)
                    yield f"{prefix}{msg}"
    else:
        for chunk in client.models.generate_content_stream(
            model=MODEL,
            contents=_make_contents(text),
            config=_get_config(text),
        ):
            if chunk.text:
                yield chunk.text
