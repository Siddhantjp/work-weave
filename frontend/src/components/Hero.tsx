import { Bike, ChefHat, Car, Clock3, Home, Search, ShieldCheck, Wrench, Zap } from "lucide-react";
import { useRef } from "react";
import { NATIVE, type Ask } from "../ask";
import type { HistoryRow } from "../types";
import { ago } from "../util";
import Orb from "./Orb";
import VoiceStatus from "./VoiceStatus";

const WORK = [
  { name: "Delivery", Icon: Bike, text: "I am looking for delivery work in Bengaluru." },
  { name: "Security guard", Icon: ShieldCheck, text: "I am looking for security guard work in Bengaluru." },
  { name: "Housekeeping", Icon: Home, text: "I am looking for housekeeping and cleaning work in Bengaluru." },
  { name: "Driver", Icon: Car, text: "I am looking for driver work in Bengaluru." },
  { name: "Electrician", Icon: Zap, text: "I am an electrician looking for work in Bengaluru." },
  { name: "Plumber", Icon: Wrench, text: "I am a plumber looking for work in Bengaluru." },
  { name: "Cook", Icon: ChefHat, text: "I am looking for cook work in Bengaluru." },
];

export function LanguagePills({ ask, center }: { ask: Ask; center?: boolean }) {
  const busy = ask.voice.state !== "idle";
  return (
    <div className={`flex flex-wrap gap-2 ${center ? "justify-center" : ""}`} role="radiogroup" aria-label="Language you will speak">
      {ask.languages.map(l => (
        <button key={l} type="button" role="radio" aria-checked={ask.language === l} disabled={busy} onClick={() => ask.setLanguage(l)}
          className={`inline-flex h-10 min-w-[64px] items-center justify-center rounded-full border px-4 text-sm font-medium transition-colors disabled:opacity-60 ${ask.language === l ? "border-brand bg-brand text-white shadow-sm" : "border-line-strong bg-white/80 hover:border-brand hover:bg-brand-soft"}`}>
          {NATIVE[l] ?? l}
        </button>
      ))}
    </div>
  );
}

interface Props { ask: Ask; value: string; onChange: (v: string) => void; onSubmit: () => void; history: HistoryRow[]; onOpen: (r: HistoryRow) => void }

export default function Hero({ ask, value, onChange, onSubmit, history, onOpen }: Props) {
  const box = useRef<HTMLTextAreaElement>(null);
  const busy = ask.voice.state !== "idle";
  return (
    <div className="mx-auto flex max-w-2xl animate-rise flex-col items-center text-center">
      <p className="inline-flex h-8 items-center rounded-full bg-sun-soft px-4 text-[13px] font-semibold text-sun-ink">Jobs in Bengaluru</p>
      <h1 className="mt-5 text-[clamp(2.4rem,6.5vw,4.25rem)] leading-[1.04]">What work are you <em className="text-brand">looking for?</em></h1>
      <p className="mt-4 max-w-lg text-lg text-ink-2">Just tell us. Speak in your language, or write it down. We find the openings that suit you.</p>

      <div className="mt-6"><Orb ask={ask} size="lg" /></div>
      <VoiceStatus ask={ask} idle="Tap the button and start speaking" className="-mt-2 max-w-md" />
      <div className="mt-5"><LanguagePills ask={ask} center /></div>

      <div className="my-8 flex w-full items-center gap-4 text-[13px] font-medium uppercase tracking-wider text-ink-3">
        <span className="h-px flex-1 bg-line-strong/70" />or write it<span className="h-px flex-1 bg-line-strong/70" />
      </div>

      <div className="card w-full p-3 text-left transition-shadow focus-within:shadow-lift focus-within:ring-4 focus-within:ring-brand/15">
        <textarea ref={box} value={value} onChange={e => onChange(e.target.value)} rows={3} aria-label="Describe the job you want"
          onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); onSubmit(); } }}
          placeholder="I have 2 years of delivery experience, I own a bike, I live in Kammanahalli and cannot work after 9 PM."
          className="block w-full resize-none bg-transparent px-3 pt-3 text-[17px] leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none" />
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-3 pb-1 pt-2">
          <AutoSwitch ask={ask} />
          <button type="button" className="btn-primary w-full sm:w-auto sm:min-w-[160px]" disabled={busy} onClick={onSubmit}><Search size={18} />Find jobs</button>
        </div>
      </div>

      <div className="mt-8 flex flex-wrap justify-center gap-2">
        {WORK.map(({ name, Icon, text }) => (
          <button key={name} type="button" className="pill bg-white/80" onClick={() => { onChange(text); box.current?.focus(); }}><Icon size={16} className="text-brand" />{name}</button>
        ))}
      </div>

      {history.length > 0 && (
        <div className="mt-12 w-full text-left">
          <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-2"><Clock3 size={15} />Pick up where you left off</p>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {history.slice(0, 2).map(r => (
              <button key={r.id} type="button" onClick={() => onOpen(r)} className="rounded-2xl border border-line bg-white/80 px-4 py-3.5 text-left transition hover:-translate-y-0.5 hover:border-line-strong hover:bg-white hover:shadow-card">
                <span className="line-clamp-2 text-[15px] font-medium leading-snug">{r.request}</span>
                <span className="mt-1 block text-xs text-ink-3">{r.result?.ranked.length ?? 0} jobs · {ago(r.created_at)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function AutoSwitch({ ask }: { ask: Ask }) {
  return (
    <label className="flex cursor-pointer select-none items-center gap-3 text-sm text-ink-2">
      <button type="button" role="switch" aria-checked={ask.auto} onClick={() => ask.setAuto(!ask.auto)}
        className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${ask.auto ? "bg-brand" : "bg-line-strong"}`}>
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${ask.auto ? "translate-x-4" : ""}`} />
      </button>
      Search as soon as I finish speaking
    </label>
  );
}
