import { Loader2, Mic, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Ask } from "../ask";

/** The voice button. While recording, its rings swell with the loudness of your voice. */
export default function Orb({ ask, size, disabled }: { ask: Ask; size: "lg" | "sm"; disabled?: boolean }) {
  const { voice } = ask;
  const rec = voice.state === "recording", work = voice.state === "transcribing";
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = wrap.current, an = voice.analyser;
    if (!el || !an) return;
    const data = new Uint8Array(an.frequencyBinCount);
    let raf = 0, level = 0;
    const tick = () => {
      an.getByteFrequencyData(data);
      let sum = 0; for (const v of data) sum += v;
      level += (Math.min(1, sum / data.length / 80) - level) * 0.25;
      el.style.setProperty("--lvl", level.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => { cancelAnimationFrame(raf); el.style.setProperty("--lvl", "0"); };
  }, [voice.analyser]);

  const lg = size === "lg";
  const Icon = work ? Loader2 : rec ? Square : Mic;
  return (
    <div ref={wrap} className={`relative grid shrink-0 place-items-center ${lg ? "h-44 w-44" : "h-12 w-12"}`} style={{ ["--lvl" as string]: 0 }}>
      {lg && (rec ? <>
        <span aria-hidden className="absolute h-28 w-28 rounded-full bg-bad/25" style={{ transform: "scale(calc(1.15 + var(--lvl) * .55))" }} />
        <span aria-hidden className="absolute h-28 w-28 rounded-full bg-bad/15" style={{ transform: "scale(calc(1.45 + var(--lvl) * .9))" }} />
      </> : !work && <>
        <span aria-hidden className="absolute h-28 w-28 animate-halo rounded-full bg-brand/30" />
        <span aria-hidden className="absolute h-28 w-28 animate-halo rounded-full bg-brand/30 [animation-delay:1.3s]" />
      </>)}
      <button type="button" disabled={work || disabled} onClick={rec ? voice.stop : voice.start}
        aria-label={rec ? "Stop recording" : "Speak your request"} title={rec ? "Stop" : "Speak"}
        className={`relative grid place-items-center rounded-full text-white transition-all active:scale-95 disabled:opacity-60 ${lg ? "h-28 w-28 shadow-orb hover:scale-[1.04]" : "h-12 w-12 hover:brightness-110"} ${rec ? "bg-bad" : "bg-brand hover:bg-brand-hover"}`}>
        <Icon size={lg ? 40 : 20} strokeWidth={lg ? 1.7 : 2} className={work ? "animate-spin" : rec ? "fill-current" : ""} />
      </button>
    </div>
  );
}
