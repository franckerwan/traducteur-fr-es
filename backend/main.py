import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm import translate, translate_stream, client as llm_client, MODEL as LLM_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 5000
TRANSLATE_TIMEOUT = 60
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def warmup():
    import time
    t0 = time.time()
    logger.info("[WARMUP] Pré-chauffe Gemini...")
    try:
        llm_client.models.generate_content(
            model=LLM_MODEL,
            contents=[{"role": "user", "parts": [{"text": "Bonjour"}]}],
            config={"max_output_tokens": 1},
        )
        logger.info("[WARMUP] Gemini prêt (%.1fs)", time.time() - t0)
    except Exception as e:
        logger.warning("[WARMUP] Gemini: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(warmup)
    yield

app = FastAPI(title="Traducteur FR-ES", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/translate")
async def route_translate(data: TranslateRequest):
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Texte vide")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(translate, text),
            timeout=TRANSLATE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "La traduction a pris trop de temps")
    except Exception as e:
        logger.exception("Erreur traduction: %s", e)
        raise HTTPException(502, "Erreur du service de traduction")
    return {"translation": result}


@app.post("/api/translate/stream")
async def route_translate_stream(data: TranslateRequest):
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Texte vide")

    async def event_stream():
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _produce():
            try:
                for chunk in translate_stream(text):
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        future = loop.run_in_executor(None, _produce)

        parts: list[str] = []
        had_error = False
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, Exception):
                logger.warning("Erreur streaming: %s", item)
                yield f"data: {json.dumps({'type': 'error', 'message': 'Erreur du service de traduction'})}\n\n"
                had_error = True
                break
            parts.append(item)
            yield f"data: {json.dumps({'type': 'text', 'content': item})}\n\n"

        if not had_error:
            yield f"data: {json.dumps({'type': 'done', 'full_text': ''.join(parts)})}\n\n"

        # S'assurer que le thread producteur est bien terminé
        try:
            await asyncio.wait_for(asyncio.wrap_future(future), timeout=5.0)
        except Exception:
            logger.debug("Thread producteur: timeout ou erreur à la fermeture")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Frontend ---

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
