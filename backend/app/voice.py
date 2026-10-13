"""Speech to text: Whisper (large-v3-turbo) on Groq. Multilingual; the language is detected unless the user picks one.

The transcript is returned to the user to review before any search runs, because speech recognition can mishear
names and places, and nothing downstream should silently act on a misheard word.
"""
from __future__ import annotations

import os

import groq
from langsmith import traceable

from . import config

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MIN_SECONDS = 0.6          # Whisper invents text ("Thank you.") for near-silence; refuse clips this short

# Display name -> ISO 639-1 code accepted by Whisper (None = auto-detect)
LANGUAGES: dict[str, str | None] = {
    "Auto-detect": None, "English": "en", "Hindi": "hi", "Kannada": "kn", "Tamil": "ta", "Telugu": "te",
    "Malayalam": "ml", "Marathi": "mr", "Bengali": "bn", "Gujarati": "gu", "Punjabi": "pa", "Urdu": "ur",
}

# Biases recognition toward the vocabulary of this app (helps short clips and local place names).
CONTEXT_PROMPT = ("Job search in Bengaluru: delivery, driver, electrician, plumber, security guard, housekeeping, cook, "
                  "Kammanahalli, Indiranagar, Whitefield, Electronic City, two-wheeler, shift, salary.")

_EXTENSIONS = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "m4a": "m4a", "mpeg": "mp3", "mp3": "mp3", "wav": "wav", "x-wav": "wav", "flac": "flac"}


class VoiceError(Exception):
    """A problem the user can act on (shown as-is in the UI)."""


def filename_for(content_type: str | None) -> str:
    """Whisper infers the format from the file name, so derive one from the upload's MIME type."""
    sub = (content_type or "").split(";")[0].strip().lower().split("/")[-1]
    if sub not in _EXTENSIONS:
        raise VoiceError(f"Unsupported audio format ({content_type or 'unknown'}). Use a browser that records WebM, OGG or MP4 audio.")
    return "speech." + _EXTENSIONS[sub]


def language_code(name: str | None) -> str | None:
    if not name or name == "Auto-detect":
        return None
    if name not in LANGUAGES:
        raise VoiceError(f"Unsupported language: {name}")
    return LANGUAGES[name]


@traceable(run_type="tool", name="transcribe_audio", tags=["whisper", "groq", "speech-to-text"])
def transcribe(audio: bytes, content_type: str | None, language: str | None = None) -> dict:
    """Return {'text', 'language', 'seconds'}. Raises VoiceError for problems the user can fix."""
    if not audio:
        raise VoiceError("No audio was received.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceError("That recording is too long. Please keep it under about a minute.")
    if not config.GROQ_API_KEY:
        raise VoiceError("Speech recognition is not configured (GROQ_API_KEY is missing).")
    name = filename_for(content_type)
    try:
        r = groq.Groq(api_key=config.GROQ_API_KEY, max_retries=1).audio.transcriptions.create(
            file=(name, audio), model=WHISPER_MODEL, language=language_code(language), prompt=CONTEXT_PROMPT,
            response_format="verbose_json", temperature=0.0)
    except groq.RateLimitError as e:
        raise VoiceError(f"Speech recognition hit Groq's free-tier limit. Try again shortly. ({str(e)[:160]})") from e
    except groq.APIStatusError as e:
        raise VoiceError(f"Speech recognition failed: {str(e)[:200]}") from e
    except groq.APIConnectionError as e:
        raise VoiceError("Could not reach the speech service. Check your connection.") from e
    text = (getattr(r, "text", "") or "").strip()
    seconds = float(getattr(r, "duration", 0) or 0)
    if not text or (seconds and seconds < MIN_SECONDS):
        raise VoiceError("I could not hear anything clear. Please try again, closer to the microphone.")
    detected = (getattr(r, "language", None) or "").strip().title() or None
    return {"text": text, "language": detected, "seconds": round(seconds, 1)}
