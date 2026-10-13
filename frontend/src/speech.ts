/** Reads text aloud with the browser's built-in voices (no network, no key). Helps people who read slowly or not at all. */
const TAG: Record<string, string> = {
  English: "en-IN", Hindi: "hi-IN", Kannada: "kn-IN", Tamil: "ta-IN", Telugu: "te-IN", Malayalam: "ml-IN", Marathi: "mr-IN",
  Bengali: "bn-IN", Gujarati: "gu-IN", Punjabi: "pa-IN", Urdu: "ur-IN",
};

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function hasVoiceFor(language: string): boolean {
  const base = (TAG[language] ?? "en-IN").slice(0, 2);
  return speechSynthesis.getVoices().some(v => v.lang.toLowerCase().startsWith(base));
}

/** Speaks `text`; resolves when finished or stopped. Returns false if this device has no voice for the language. */
export function speak(text: string, language: string, onEnd: () => void): boolean {
  speechSynthesis.cancel();
  if (!hasVoiceFor(language) && speechSynthesis.getVoices().length) return false;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = TAG[language] ?? "en-IN"; u.rate = 0.95;
  u.onend = u.onerror = onEnd;
  speechSynthesis.speak(u);
  return true;
}
export const stopSpeaking = () => { if (canSpeak()) speechSynthesis.cancel(); };
