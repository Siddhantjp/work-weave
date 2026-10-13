import { useCallback, useEffect, useRef, useState } from "react";
import { friendly, postAudio } from "../api";

const MAX_SECONDS = 60;
const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export type VoiceState = "idle" | "recording" | "transcribing";

/** Records from the microphone, sends the audio to the backend for transcription and returns the text.
 *  `analyser` exposes the live signal so the UI can draw a level meter while recording. */
export function useVoice(language: string, onText: (text: string, heardIn: string | null) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string>();
  const [heard, setHeard] = useState<string>();
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef({ language, onText });
  latest.current = { language, onText };

  const release = useCallback(() => {
    window.clearInterval(timer.current);
    stream.current?.getTracks().forEach(t => t.stop());
    void audioCtx.current?.close().catch(() => {});
    stream.current = null; audioCtx.current = null; setAnalyser(null);
  }, []);
  useEffect(() => release, [release]);

  const upload = useCallback(async (blob: Blob) => {
    setState("transcribing");
    try {
      const q = latest.current.language === "Auto-detect" ? "" : `?language=${encodeURIComponent(latest.current.language)}`;
      const r = await postAudio<{ text: string; language?: string }>(`/api/transcribe${q}`, blob);
      setHeard(r.language ?? ""); latest.current.onText(r.text, r.language ?? null);
    } catch (e) { setError(friendly((e as Error).message)); }
    setState("idle");
  }, []);

  const start = useCallback(async () => {
    setError(undefined); setHeard(undefined);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined")
      return setError("Voice is not supported in this browser. Please type instead, or use Chrome, Edge or Firefox.");
    try { stream.current = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) {
      return setError((e as DOMException).name === "NotAllowedError"
        ? "Microphone access is blocked. Allow it in your browser's address bar and try again." : "We could not find a microphone.");
    }
    try {
      const ctx = new AudioContext(); audioCtx.current = ctx;
      const node = ctx.createAnalyser(); node.fftSize = 64; node.smoothingTimeConstant = 0.75;
      ctx.createMediaStreamSource(stream.current).connect(node); setAnalyser(node);
    } catch { /* the meter is optional */ }
    const mime = MIME_CANDIDATES.find(m => MediaRecorder.isTypeSupported(m));
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined);
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => { release(); void upload(new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" })); };
    recorder.current = rec; rec.start();
    setSeconds(0); setState("recording");
    let s = 0;
    timer.current = window.setInterval(() => { setSeconds(++s); if (s >= MAX_SECONDS && rec.state !== "inactive") rec.stop(); }, 1000);
  }, [release, upload]);

  const stop = useCallback(() => { if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop(); }, []);
  return { state, seconds, error, heard, analyser, start, stop };
}
