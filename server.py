#!/usr/bin/env python
"""OpenAI-compatible LAN server for Gemma 4 12B (4-bit MLX) — memory-safe on 16 GB.

Safety design (this 12B model peaks near the 13.5 GB GPU limit):
  * MAX_INPUT_TOKENS guard  -> rejects oversized prompts with HTTP 413 instead of
    OOM-crashing the process (prefill memory scales with input length).
  * Single global lock      -> serializes generation; concurrent requests would
    double the working set and OOM.
  * max_tokens cap + bounded KV cache.

Run:
  ~/gemma4/.venv/bin/python ~/gemma4/server.py            # binds 0.0.0.0:8080
Endpoints: GET /v1/models, GET /healthz, POST /v1/chat/completions  (OpenAI shape)
"""
import time, threading, argparse
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from mlx_vlm import load, generate

MODEL = "mlx-community/gemma-4-12B-4bit"
MAX_INPUT_TOKENS = 600     # measured-safe guard: ~600 in-tokens peaks ~12.3 GB
MAX_OUTPUT_TOKENS = 512
MAX_KV_SIZE = 2048
KV_BITS = 8

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="0.0.0.0")
ap.add_argument("--port", type=int, default=8080)
args = ap.parse_args()

print(f"loading {MODEL} ...", flush=True)
model, processor = load(MODEL)
tokenizer = getattr(processor, "tokenizer", processor)
LOCK = threading.Lock()
print("model ready.", flush=True)

def build_prompt(messages):
    """Apply Gemma turn format manually (this conversion ships no chat_template)."""
    sys_txt = ""
    parts = []
    for m in messages:
        role, content = m.get("role"), m.get("content", "")
        if role == "system":
            sys_txt += content + "\n\n"
        elif role == "user":
            parts.append(f"<start_of_turn>user\n{sys_txt}{content}<end_of_turn>\n")
            sys_txt = ""
        elif role == "assistant":
            parts.append(f"<start_of_turn>model\n{content}<end_of_turn>\n")
    parts.append("<start_of_turn>model\n")
    return "".join(parts)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: Optional[str] = MODEL
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.7

app = FastAPI(title="gemma4-local")

@app.get("/healthz")
def healthz():
    return {"status": "ok", "model": MODEL}

@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "local"}]}

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):  # async -> runs in main thread that owns the MLX GPU stream
    prompt = build_prompt([m.dict() for m in req.messages])
    n_in = len(tokenizer.encode(prompt))
    if n_in > MAX_INPUT_TOKENS:
        raise HTTPException(status_code=413,
            detail=f"Prompt {n_in} tokens exceeds MAX_INPUT_TOKENS={MAX_INPUT_TOKENS} "
                   f"(memory-safety guard for 16 GB). Shorten the input.")
    max_out = min(req.max_tokens or 256, MAX_OUTPUT_TOKENS)
    if not LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server busy (single-request limit on 16 GB). Retry.")
    try:
        t = time.time()
        res = generate(model, processor, prompt, max_tokens=max_out,
                       temperature=req.temperature or 0.7, eos_tokens=["<end_of_turn>"],
                       repetition_penalty=1.1, skip_special_tokens=True, verbose=False,
                       max_kv_size=MAX_KV_SIZE, kv_bits=KV_BITS)
        text = res.text if hasattr(res, "text") else str(res)
        text = text.split("<end_of_turn")[0].split("<start_of_turn")[0]  # strip leaked turn markers
        dt = time.time() - t
    finally:
        LOCK.release()
    return {
        "id": f"chatcmpl-{int(t)}", "object": "chat.completion", "created": int(t),
        "model": MODEL,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text.strip()},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": n_in, "completion_tokens": getattr(res, "generation_tokens", None),
                  "gen_tps": round(getattr(res, "generation_tps", 0) or 0, 1), "latency_s": round(dt, 1)},
    }

if __name__ == "__main__":
    print(f"serving on http://{args.host}:{args.port}  (LAN-accessible)", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
