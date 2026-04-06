import os
import json
import asyncio
import queue
import threading
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llm import translate, translate_stream, client as llm_client, MODEL as LLM_MODEL

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def warmup():
    """Pré-chauffe Gemini pour que la première requête soit rapide."""
    import time
    t0 = time.time()
    print("[WARMUP] Pré-chauffe Gemini...", flush=True)
    try:
        llm_client.models.generate_content(
            model=LLM_MODEL,
            contents=[{"role": "user", "parts": [{"text": "Bonjour"}]}],
            config={"max_output_tokens": 1},
        )
        print(f"[WARMUP] Gemini prêt ({time.time()-t0:.1f}s)", flush=True)
    except Exception as e:
        print(f"[WARMUP] Gemini: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, warmup)
    yield

app = FastAPI(title="Traducteur FR-ES", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TranslateRequest(BaseModel):
    text: str


@app.post("/api/translate")
async def route_translate(data: TranslateRequest):
    """Traduction instantanée (réponse complète)."""
    if not data.text.strip():
        raise HTTPException(400, "Texte vide")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, translate, data.text.strip())
    return {"translation": result}


@app.post("/api/translate/stream")
async def route_translate_stream(data: TranslateRequest):
    """Traduction en streaming SSE."""
    if not data.text.strip():
        raise HTTPException(400, "Texte vide")

    text = data.text.strip()

    async def event_stream():
        q = queue.Queue()

        def _produce():
            try:
                for chunk in translate_stream(text):
                    q.put(chunk)
            except Exception as e:
                q.put(e)
            finally:
                q.put(None)

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()

        full = ""
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None:
                break
            if isinstance(item, Exception):
                yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
                break
            full += item
            yield f"data: {json.dumps({'type': 'text', 'content': item})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'full_text': full})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Frontend ---

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
