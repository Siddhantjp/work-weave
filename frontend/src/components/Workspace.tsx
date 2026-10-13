import { ArrowLeft, Check, ChevronRight, ExternalLink, IndianRupee, MapPin, Pause, SearchX, Sparkles, Sun, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Job, SearchResult } from "../types";
import { ago, hour12, titleCase } from "../util";
import { canSpeak, speak, stopSpeaking } from "../speech";

const place = (j: Job) => (j.locality ?? "").replace(/, Bengaluru\/Bangalore|, Bengaluru|, Bangalore/g, "") || "Bengaluru";

/** "₹18,000 - ₹24,000 a month" -> ["₹18,000 - ₹24,000", "per month"]. */
function splitPay(s?: string | null): [string, string] {
  if (!s) return ["Not stated", ""];
  const m = s.match(/^(.*?)\s+(?:a|per)\s+(month|day|week|hour|year)\s*$/i);
  return m ? [m[1], `per ${m[2].toLowerCase()}`] : [s, ""];
}

export const STEPS = ["Understanding your request", "Checking the latest jobs", "Finding the closest matches", "Reading what each job needs", "Ranking jobs for you"];
export const STEP_OF: Record<string, number> = { understand: 0, check_source: 1, retrieve: 2, grade_documents: 2, relax: 2, augment: 3, grade_limits: 4, finish: 4 };

/* ---------- loading ---------- */
function Loading({ step }: { step: number }) {
  return (
    <div className="animate-rise" aria-live="polite">
      <div className="flex items-center gap-4">
        <div className="flex flex-1 gap-1.5" aria-hidden>
          {STEPS.map((_, i) => <span key={i} className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${i < step ? "bg-brand" : i === step ? "animate-pulse bg-sun" : "bg-line-strong/60"}`} />)}
        </div>
        <span className="text-sm text-ink-3">Step {step + 1} of {STEPS.length}</span>
      </div>
      <p className="mt-3 font-display text-2xl">{STEPS[step]}…</p>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,400px)_1fr]" aria-hidden>
        <div className="grid gap-3">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-[88px] animate-shimmer rounded-2xl" style={{ opacity: 1 - i * 0.18 }} />)}</div>
        <div className="skeleton hidden h-[420px] animate-shimmer rounded-3xl lg:block" />
      </div>
    </div>
  );
}

/* ---------- list ---------- */
function Row({ job, index, active, onPick }: { job: Job; index: number; active: boolean; onPick: () => void }) {
  const [pay] = splitPay(job.salary_text);
  return (
    <li className="animate-rise" style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}>
      <button type="button" onClick={onPick} aria-current={active}
        className={`group relative flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition-all ${active ? "border-brand/40 bg-white shadow-card ring-1 ring-brand/25" : "border-transparent bg-white/60 hover:border-line hover:bg-white"}`}>
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl font-display text-lg font-semibold ${index === 0 ? "bg-sun-soft text-sun-ink" : "bg-brand-soft text-brand-ink"}`}>{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2"><span className="truncate font-display text-[1.05rem] font-semibold leading-snug">{job.title}</span>
            {index === 0 && <Sparkles size={14} className="shrink-0 text-sun" aria-label="Best match" />}</span>
          <span className="block truncate text-sm text-ink-2">{job.employer}</span>
          <span className="mt-1 block truncate text-[13px] text-ink-3">{job.distance_km != null ? `${job.distance_km} km · ` : ""}{pay}</span>
        </span>
        <ChevronRight size={18} className={`shrink-0 transition-transform ${active ? "translate-x-0.5 text-brand" : "text-ink-3 group-hover:translate-x-0.5"}`} />
      </button>
    </li>
  );
}

/* ---------- detail ---------- */
function Tile({ Icon, label, value, unit, wide }: { Icon: typeof MapPin; label: string; value: string; unit?: string; wide?: boolean }) {
  return (
    <div className={`rounded-2xl bg-canvas px-4 py-3.5 ${wide ? "col-span-2" : ""}`}>
      <p className="flex items-center gap-1.5 text-xs font-medium text-ink-3"><Icon size={14} />{label}</p>
      <p className="mt-1.5 font-display text-xl font-semibold leading-tight">{value}</p>
      {unit && <p className="mt-0.5 text-xs text-ink-3">{unit}</p>}
    </div>
  );
}

function Detail({ job, best, language, onBack }: { job: Job; best: boolean; language: string; onBack: () => void }) {
  const q = job.requirements;
  const [pay, unit] = splitPay(job.salary_text);
  const [playing, setPlaying] = useState(false);
  const [noVoice, setNoVoice] = useState(false);
  useEffect(() => { setPlaying(false); setNoVoice(false); return stopSpeaking; }, [job.url]);

  const needs: string[] = [];
  if (q?.vehicle_required === "yes") needs.push("You need your own vehicle");
  if (q?.min_experience_months) needs.push(`At least ${q.min_experience_months} months of experience`);
  if (q?.shift && q.shift !== "unknown") needs.push(`${titleCase(q.shift)} shift`);
  if (job.valid_through) needs.push(`Apply by ${job.valid_through}`);
  const ask = job.verdict?.missing ?? [];

  function listen() {
    if (playing) { stopSpeaking(); return setPlaying(false); }
    const text = `${job.title}, ${job.employer}. ${job.salary_text ?? ""}. ${job.rationale ?? ""}`;
    const ok = speak(text, language, () => setPlaying(false));
    setNoVoice(!ok); setPlaying(ok);
  }

  return (
    <article className="card animate-rise overflow-hidden" key={job.url}>
      {best && <div className="h-1.5 bg-sun" aria-hidden />}
      <div className="p-6 sm:p-8">
        <button type="button" onClick={onBack} className="-ml-2 mb-4 inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-ink-2 hover:bg-canvas lg:hidden"><ArrowLeft size={16} />All jobs</button>
        <div className="flex items-start gap-4">
          <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl font-display text-2xl font-semibold ${best ? "bg-sun-soft text-sun-ink" : "bg-brand-soft text-brand-ink"}`} aria-hidden>{(job.employer || job.title)[0]?.toUpperCase()}</span>
          <div className="min-w-0">
            {best && <p className="mb-1 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-sun-ink"><Sparkles size={13} />Best match for you</p>}
            <h2 className="text-[1.75rem] leading-tight sm:text-[2rem]">{job.title}</h2>
            <p className="mt-1 text-base text-ink-2">{job.employer} · {place(job)}</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tile Icon={MapPin} label="Distance" value={job.distance_km != null ? `${job.distance_km} km` : "—"} unit={job.distance_km != null ? "from where you live" : "Not known"} />
          <Tile Icon={IndianRupee} label="Pay" value={pay} unit={unit} wide />
          <Tile Icon={Sun} label="Shift" value={q?.shift && q.shift !== "unknown" ? titleCase(q.shift) : "Not stated"} />
        </div>

        {job.rationale && (
          <section className="mt-6 rounded-2xl border border-sun/40 bg-sun-soft/50 p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-lg">Why it suits you</h3>
              {canSpeak() && <button type="button" onClick={listen} className="btn-ghost btn-sm" aria-pressed={playing}>{playing ? <><Pause size={15} />Stop</> : <><Volume2 size={15} />Listen</>}</button>}
            </div>
            <p className="mt-2 text-base leading-relaxed">{job.rationale}</p>
            {noVoice && <p className="mt-2 text-sm text-ink-3">This device has no {language} voice installed, so it cannot read this aloud.</p>}
          </section>
        )}

        {(needs.length > 0 || ask.length > 0) && (
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            {needs.length > 0 && (
              <section><h3 className="text-lg">What the job needs</h3>
                <ul className="mt-3 grid gap-2.5">{needs.map(n => <li key={n} className="flex items-start gap-2.5 text-[15px]"><span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-soft text-brand"><Check size={12} strokeWidth={3} /></span>{n}</li>)}</ul></section>
            )}
            {ask.length > 0 && (
              <section><h3 className="text-lg">Ask the employer</h3>
                <ul className="mt-3 grid gap-2.5">{ask.map(n => <li key={n} className="flex items-start gap-2.5 text-[15px]"><span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-sun-soft text-sun-ink text-xs font-bold">?</span>{n}</li>)}</ul></section>
            )}
          </div>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
          <p className="text-[13px] text-ink-3">{job.acquired_at ? `Checked ${ago(job.acquired_at)} on apna.co` : "Listed on apna.co"}</p>
          <a className="btn-primary w-full sm:w-auto" href={job.url} target="_blank" rel="noopener noreferrer">View and apply<ExternalLink size={16} /></a>
        </div>
      </div>
    </article>
  );
}

/* ---------- workspace ---------- */
function Summary({ res }: { res: SearchResult }) {
  const p = res.profile; if (!p) return null;
  const bits = [p.desired_trades?.length ? titleCase(p.desired_trades.join(", ")) : null,
    p.experience_months != null ? `${p.experience_months} months experience` : null,
    p.home_locality ? `Lives in ${p.home_locality}` : null, p.has_vehicle ? "Has a vehicle" : null, p.owns_tools ? "Has own tools" : null,
    p.latest_shift_end_hour ? `Done by ${hour12(p.latest_shift_end_hour)}` : null].filter(Boolean) as string[];
  if (!bits.length) return null;
  const lang = res.language && res.language !== "English" ? res.language : null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="mr-1 text-sm font-semibold text-ink-2">We understood</span>
      {bits.map(b => <span key={b} className="chip border border-line bg-white">{b}</span>)}
      {lang && <span className="chip bg-sun-soft text-sun-ink">Replies in {lang}</span>}
    </div>
  );
}

interface Props { busy: boolean; step: number; error?: string; result: SearchResult | null }

export default function Workspace({ busy, step, error, result }: Props) {
  const [sel, setSel] = useState(0);
  const [detailOpen, setDetailOpen] = useState(false);   // phones show list OR detail
  const top = useRef<HTMLDivElement>(null);
  useEffect(() => { setSel(0); setDetailOpen(false); }, [result]);

  if (busy) return <Loading step={step} />;
  if (error) return <p className="rounded-2xl bg-bad-soft px-5 py-4 text-[15px] font-medium text-bad" role="alert">{error}</p>;
  if (!result) return null;

  const jobs = result.ranked, hidden = result.removed_by_hard_limits ?? [];
  const language = result.language || "English";
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel(s => Math.min(jobs.length - 1, s + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel(s => Math.max(0, s - 1)); }
  };

  return (
    <div ref={top} className="grid gap-5">
      <Summary res={result} />
      {result.refresh_failed && <p className="rounded-2xl bg-sun-soft px-4 py-3 text-sm font-medium text-sun-ink" role="status">We could not fetch the very latest openings just now, so some of these may be a little out of date.</p>}
      {jobs.length === 0 ? (
        <section className="card mx-auto w-full max-w-xl px-6 py-14 text-center">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-canvas text-ink-3"><SearchX size={24} /></span>
          <h3 className="mt-4 text-xl">No suitable jobs right now</h3>
          <p className="mx-auto mt-2 max-w-md text-[15px] text-ink-2">Nothing matched your request and your limits. Try describing the work more broadly, or check back later as new jobs are added.</p>
        </section>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,400px)_1fr]">
          <div className={detailOpen ? "hidden lg:block" : "block"} onKeyDown={onKey}>
            <div className="mb-3 flex items-baseline justify-between"><h2 className="text-[1.6rem]">{jobs.length} {jobs.length === 1 ? "job" : "jobs"} for you</h2><span className="text-sm text-ink-3">Best first</span></div>
            <ul className="grid gap-2.5">{jobs.map((j, i) => <Row key={j.url} job={j} index={i} active={i === sel} onPick={() => { setSel(i); setDetailOpen(true); }} />)}</ul>
            {hidden.length > 0 && (
              <details className="mt-5 text-sm text-ink-2">
                <summary className="cursor-pointer font-medium">{hidden.length} {hidden.length === 1 ? "job was" : "jobs were"} left out because of your working hours</summary>
                <ul className="mt-2 list-disc pl-5">{hidden.map((c, i) => <li key={i}>{c.title}, {c.employer}</li>)}</ul>
              </details>
            )}
          </div>
          <div className={`${detailOpen ? "block" : "hidden lg:block"} lg:sticky lg:top-[92px] lg:max-h-[calc(100vh-112px)] lg:overflow-y-auto lg:rounded-3xl`}>
            <Detail job={jobs[sel]} best={sel === 0} language={language} onBack={() => setDetailOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
