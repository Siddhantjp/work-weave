import { useEffect, useRef, useState } from "react";
import { get } from "./api";
import { useVoice } from "./components/useVoice";
import { readFlag, writeFlag } from "./util";

const LANG_KEY = "voice-language";
const AUTO_KEY = "search-after-speaking";

/** Everything about *asking* (language, voice, auto-search) lives here so the big hero and the compact bar share one state. */
export function useAsk(onTranscript: (text: string, auto: boolean) => void) {
  const [languages, setLanguages] = useState<string[]>(["Auto-detect"]);
  const [language, setLang] = useState(() => { try { return localStorage.getItem(LANG_KEY) ?? "Auto-detect"; } catch { return "Auto-detect"; } });
  const [auto, setAutoState] = useState(() => readFlag(AUTO_KEY, true));
  const autoRef = useRef(auto); autoRef.current = auto;

  useEffect(() => { get<string[]>("/api/languages").then(setLanguages).catch(() => {}); }, []);
  const voice = useVoice(language, text => onTranscript(text, autoRef.current));
  return {
    languages, language, auto, voice,
    setLanguage: (l: string) => { setLang(l); try { localStorage.setItem(LANG_KEY, l); } catch { /* ignore */ } },
    setAuto: (v: boolean) => { setAutoState(v); writeFlag(AUTO_KEY, v); },
  };
}
export type Ask = ReturnType<typeof useAsk>;

export const NATIVE: Record<string, string> = {
  "Auto-detect": "Auto", English: "English", Hindi: "हिन्दी", Kannada: "ಕನ್ನಡ", Tamil: "தமிழ்", Telugu: "తెలుగు", Malayalam: "മലയാളം", Marathi: "मराठी",
  Bengali: "বাংলা", Gujarati: "ગુજરાતી", Punjabi: "ਪੰਜਾਬੀ", Urdu: "اردو",
};
