"""Voice input: upload a short recording, get its transcript. The raw audio is never stored."""
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..accounts.store import AuthUser
from .. import auth, voice

router = APIRouter(prefix="/api", tags=["voice"])


@router.get("/languages")
def languages(user: AuthUser = Depends(auth.current_user)):
    return list(voice.LANGUAGES)


@router.post("/transcribe")
async def transcribe(request: Request, language: str | None = None, user: AuthUser = Depends(auth.current_user)):
    """Body = the raw audio bytes; Content-Type = the recording's MIME type (e.g. audio/webm)."""
    audio = await request.body()
    try:
        return await run_in_threadpool(voice.transcribe, audio, request.headers.get("content-type"), language)
    except voice.VoiceError as e:
        raise HTTPException(422, str(e))
