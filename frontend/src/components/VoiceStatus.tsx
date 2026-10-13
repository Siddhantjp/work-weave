import type { Ask } from "../ask";

/** One line of plain-language feedback about the microphone. Reserves its height so the layout never jumps. */
export default function VoiceStatus({ ask, idle, className = "" }: { ask: Ask; idle?: string; className?: string }) {
  const { voice } = ask;
  const mmss = `${Math.floor(voice.seconds / 60)}:${String(voice.seconds % 60).padStart(2, "0")}`;
  const msg = voice.error ?? (voice.state === "recording" ? `Listening… ${mmss}. Tap the red button when you are done.`
    : voice.state === "transcribing" ? "Writing down what you said…"
    : voice.heard !== undefined ? `Heard${voice.heard ? " in " + voice.heard : ""}. Please check the words and fix anything we misheard.` : idle ?? "");
  return <p role="status" aria-live="polite" className={`min-h-[24px] text-[15px] ${voice.error ? "font-medium text-bad" : voice.state === "recording" ? "font-medium text-bad" : "text-ink-2"} ${className}`}>{msg}</p>;
}
