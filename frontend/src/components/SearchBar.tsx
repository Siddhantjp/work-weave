import { Search } from "lucide-react";
import { NATIVE, type Ask } from "../ask";
import Orb from "./Orb";
import VoiceStatus from "./VoiceStatus";

interface Props { ask: Ask; value: string; onChange: (v: string) => void; onSubmit: () => void; busy: boolean }

/** The compact version of the ask box, kept at the top once results are on screen so you can refine without starting over. */
export default function SearchBar({ ask, value, onChange, onSubmit, busy }: Props) {
  const recording = ask.voice.state === "recording", working = ask.voice.state === "transcribing";
  return (
    <div>
      <div className="card flex flex-wrap items-center gap-3 p-3 transition-shadow focus-within:shadow-lift focus-within:ring-4 focus-within:ring-brand/15 sm:flex-nowrap sm:rounded-full sm:py-2.5 sm:pl-3 sm:pr-3">
        <Orb ask={ask} size="sm" disabled={busy} />
        <textarea value={value} onChange={e => onChange(e.target.value)} rows={2} aria-label="Describe the job you want"
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSubmit(); } }}
          className="order-first min-h-[84px] w-full sm:min-h-[48px] min-w-0 resize-none sm:order-none sm:w-auto sm:flex-1 bg-transparent px-1 py-2 text-[16px] leading-snug text-ink focus:outline-none sm:max-h-[56px]" />
        <label className="relative">
          <span className="sr-only">Language you will speak</span>
          <select value={ask.language} disabled={recording || working} onChange={e => ask.setLanguage(e.target.value)}
            className="h-12 cursor-pointer appearance-none rounded-full border border-line-strong bg-white pl-4 pr-9 text-sm font-medium focus:outline-none focus:ring-4 focus:ring-brand/15 disabled:opacity-60">
            {ask.languages.map(l => <option key={l} value={l}>{NATIVE[l] ?? l}</option>)}
          </select>
          <svg className="pointer-events-none absolute right-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
        </label>
        <button type="button" className="btn-primary ml-auto sm:ml-0" disabled={busy || recording || working} onClick={onSubmit}><Search size={18} />Find jobs</button>
      </div>
      <VoiceStatus ask={ask} className="mt-2 px-4" />
    </div>
  );
}
