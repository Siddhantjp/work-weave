"""Voice input and multilingual matching. Whisper/Groq is mocked: no audio or network is used."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config, voice
from app.api import app
from app.search.extraction import Evidence, Extraction, verify_extraction


def test_filename_follows_mime_type():
    assert voice.filename_for("audio/webm;codecs=opus") == "speech.webm"
    assert voice.filename_for("audio/mp4") == "speech.mp4"
    assert voice.filename_for("audio/x-wav") == "speech.wav"
    with pytest.raises(voice.VoiceError):
        voice.filename_for("video/quicktime")
    with pytest.raises(voice.VoiceError):
        voice.filename_for(None)


def test_language_choice_maps_to_whisper_codes():
    assert voice.language_code("Kannada") == "kn" and voice.language_code("Hindi") == "hi"
    assert voice.language_code("Auto-detect") is None and voice.language_code(None) is None
    with pytest.raises(voice.VoiceError):
        voice.language_code("Klingon")


class FakeGroq:
    """Stands in for groq.Groq; records what it was asked and returns a canned verbose_json answer."""
    calls: list[dict] = []
    reply = SimpleNamespace(text="  मैं डिलीवरी का काम करता हूँ  ", duration=3.2, language="hindi")

    def __init__(self, **kw):
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        FakeGroq.calls.append(kw)
        return FakeGroq.reply


@pytest.fixture
def fake_whisper(monkeypatch):
    FakeGroq.calls = []
    monkeypatch.setattr(voice.groq, "Groq", FakeGroq)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")


def test_transcribe_returns_text_language_and_passes_hints(fake_whisper):
    out = voice.transcribe(b"audio-bytes", "audio/webm", "Hindi")
    assert out == {"text": "मैं डिलीवरी का काम करता हूँ", "language": "Hindi", "seconds": 3.2}
    call = FakeGroq.calls[0]
    assert call["language"] == "hi" and call["file"][0] == "speech.webm" and "Bengaluru" in call["prompt"]
    assert call["response_format"] == "verbose_json"


@pytest.mark.parametrize("audio,ctype,msg", [pytest.param(b"", "audio/webm", "No audio", id="empty"),
                                             pytest.param(b"x" * (voice.MAX_AUDIO_BYTES + 1), "audio/webm", "too long", id="oversized")])
def test_transcribe_rejects_empty_or_oversized_audio(fake_whisper, audio, ctype, msg):
    with pytest.raises(voice.VoiceError, match=msg):
        voice.transcribe(audio, ctype)
    assert not FakeGroq.calls                   # nothing is sent to Whisper


def test_near_silence_is_refused_instead_of_searching_on_invented_text(fake_whisper):
    FakeGroq.reply = SimpleNamespace(text="Thank you.", duration=0.3, language="english")
    with pytest.raises(voice.VoiceError, match="could not hear"):
        voice.transcribe(b"a", "audio/webm")
    FakeGroq.reply = SimpleNamespace(text="", duration=2.0, language="english")
    with pytest.raises(voice.VoiceError):
        voice.transcribe(b"a", "audio/webm")


def test_missing_key_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    with pytest.raises(voice.VoiceError, match="GROQ_API_KEY"):
        voice.transcribe(b"a", "audio/webm")


# ---- API ----------------------------------------------------------------- #
@pytest.fixture
def client(temp_db):
    with TestClient(app) as c:
        yield c


def test_transcribe_endpoint_requires_login_then_returns_transcript(client, monkeypatch, sign_in):
    assert client.post("/api/transcribe", content=b"a", headers={"content-type": "audio/webm"}).status_code == 401
    sign_in(client)
    seen = {}
    monkeypatch.setattr(voice, "transcribe", lambda audio, ctype, lang: seen.update(n=len(audio), c=ctype, l=lang) or
                        {"text": "delivery job", "language": "English", "seconds": 2.0})
    r = client.post("/api/transcribe?language=Kannada", content=b"abcd", headers={"content-type": "audio/webm;codecs=opus"})
    assert r.status_code == 200 and r.json()["text"] == "delivery job"
    assert seen == {"n": 4, "c": "audio/webm;codecs=opus", "l": "Kannada"}


def test_transcribe_endpoint_turns_user_fixable_problems_into_422(client, monkeypatch, sign_in):
    sign_in(client)

    def boom(*a):
        raise voice.VoiceError("I could not hear anything clear.")
    monkeypatch.setattr(voice, "transcribe", boom)
    r = client.post("/api/transcribe", content=b"a", headers={"content-type": "audio/webm"})
    assert r.status_code == 422 and "could not hear" in r.json()["detail"]


def test_language_list_exposed(client, sign_in):
    sign_in(client)
    langs = client.get("/api/languages").json()
    assert langs[0] == "Auto-detect" and {"Hindi", "Kannada", "Tamil", "Telugu", "English"} <= set(langs)


# ---- grounding works for Indian scripts ---------------------------------- #
def ext(**kw):
    base = dict(desired_trades=[], skills=[], experience_months=None, home_locality=None, has_vehicle=None, vehicle_type=None,
                owns_tools=None, latest_shift_end_hour=None, avoid_night_shift=False, min_monthly_wage=None, evidence=[])
    return Extraction(**{**base, **kw})


def test_quote_in_original_script_verifies_even_with_different_unicode_composition():
    text = "मैं बेंगलुरु में रहता हूँ और रात 9 बजे के बाद काम नहीं कर सकता"
    decomposed = text.replace("ँ", "ँ")             # same text; also try a decomposed nukta below
    x = ext(home_locality="Bengaluru", latest_shift_end_hour=21,
            evidence=[Evidence(field="home_locality", quote="बेंगलुरु में रहता हूँ"),
                      Evidence(field="latest_shift_end_hour", quote="रात 9 बजे के बाद काम नहीं कर सकता")])
    kept, dropped = verify_extraction(x, decomposed)
    assert kept == {"home_locality": "Bengaluru", "latest_shift_end_hour": 21} and not dropped
    # a translated (English) quote is NOT in the worker's words, so the field is discarded
    x2 = ext(home_locality="Bengaluru", evidence=[Evidence(field="home_locality", quote="lives in Bengaluru")])
    assert verify_extraction(x2, text)[0] == {}


def test_nfkc_makes_composed_and_decomposed_forms_match():
    composed, decomposed = "क़", "क़"            # क़ as one code point vs क + nukta
    x = ext(home_locality="X", evidence=[Evidence(field="home_locality", quote=composed)])
    assert verify_extraction(x, "मैं " + decomposed + " में")[0] == {"home_locality": "X"}
