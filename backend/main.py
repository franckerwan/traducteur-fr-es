import os
import json
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm import translate, translate_stream, client as llm_client, MODEL as LLM_MODEL

MAX_TEXT_LENGTH = 5000
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def warmup():
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
    await asyncio.to_thread(warmup)
    yield

app = FastAPI(title="Traducteur FR-ES", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)


@app.post("/api/translate")
async def route_translate(data: TranslateRequest):
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Texte vide")
    try:
        result = await asyncio.to_thread(translate, text)
    except Exception as e:
        raise HTTPException(502, f"Erreur du service de traduction: {e}")
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

        loop.run_in_executor(None, _produce)

        parts: list[str] = []
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, Exception):
                yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
                break
            parts.append(item)
            yield f"data: {json.dumps({'type': 'text', 'content': item})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'full_text': ''.join(parts)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Frontend ---

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
