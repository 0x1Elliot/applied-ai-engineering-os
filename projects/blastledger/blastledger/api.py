"""Zero-persistence prototype HTTP adapter; do not expose publicly without auth."""
import json

from fastapi import FastAPI, HTTPException, Request

from . import InputError, assess

app = FastAPI(
    title="BlastLedger Assess API",
    version="0.1.0",
    description="Read-only, deterministic change risk assessment. Prototype: no auth; deploy privately only.",
)


@app.post("/assess")
async def assess_change(request: Request) -> dict:
    # Reading a bounded stream prevents unnecessary memory use on untrusted bodies.
    size = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Maximum request size is 1 MiB")
        chunks.append(chunk)
    try:
        data = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc
    try:
        return assess(data)
    except InputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
