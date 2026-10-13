import { useCallback, useEffect, useState } from "react";
import { ApiError, del, friendly, get, pollTask, post } from "../api";
import { useAsk } from "../ask";
import type { HistoryRow, Me, SearchResult } from "../types";
import Hero from "./Hero";
import SearchBar from "./SearchBar";
import TopBar from "./TopBar";
import Workspace, { STEP_OF } from "./Workspace";

export default function Dashboard({ user, onLogout, onDeleted }: { user: Me; onLogout: () => void; onDeleted: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string>();
  const [history, setHistory] = useState<HistoryRow[]>([]);

  const ask = useAsk((t, auto) => { setText(t); if (auto) void run(t); });
  const inWork = busy || !!result || !!error;

  const loadHistory = useCallback(() => {
    get<HistoryRow[]>("/api/searches").then(rows => setHistory(rows.filter(r => r.status === "done" && r.result).slice(0, 8))).catch(() => {});
  }, []);
  useEffect(loadHistory, [loadHistory]);

  const open = (r: HistoryRow) => { setText(r.request); setError(undefined); setResult(r.result); window.scrollTo({ top: 0 }); };
  const clearHistory = async () => { await del("/api/searches").catch(() => {}); setHistory([]); };
  const reset = () => { if (busy) return; setText(""); setResult(null); setError(undefined); window.scrollTo({ top: 0 }); };

  async function run(override?: string) {
    const request = (override ?? text).trim();
    if (busy) return;
    if (request.length < 5) { setResult(null); return setError("Please write a sentence about the job you want."); }
    setBusy(true); setError(undefined); setResult(null); setStep(0); window.scrollTo({ top: 0 });
    try {
      const { task } = await post<{ task: string }>("/api/search", { request });
      setResult(await pollTask<SearchResult>(task, ev => setStep(Math.max(0, ...ev.map(e => STEP_OF[e.node] ?? 0)))));
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? friendly(e.message) : "Something went wrong. Please try again.");
    }
    setBusy(false); loadHistory();
  }

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar user={user} history={history} inWork={inWork} onNew={reset} onOpen={open} onLogout={onLogout} onDeleted={onDeleted} onClearHistory={clearHistory} />
      <main className="mx-auto w-full max-w-[1240px] flex-1 px-5 pb-20 pt-8 sm:px-8 sm:pt-12">
        {inWork ? (
          <div className="grid gap-7">
            <div className="animate-rise"><SearchBar ask={ask} value={text} onChange={setText} onSubmit={() => run()} busy={busy} /></div>
            <Workspace busy={busy} step={step} error={error} result={result} />
          </div>
        ) : (
          <Hero ask={ask} value={text} onChange={setText} onSubmit={() => run()} history={history} onOpen={open} />
        )}
      </main>
      <footer className="mx-auto flex w-full max-w-[1240px] flex-wrap justify-between gap-x-8 gap-y-1 border-t border-line px-5 py-6 text-[13px] text-ink-3 sm:px-8">
        <span>Jobs in Bengaluru, from <a className="underline underline-offset-2 hover:text-ink" href="https://apna.co" target="_blank" rel="noopener noreferrer">apna.co</a></span>
        <span>Always confirm the details with the employer before you apply.</span>
      </footer>
    </div>
  );
}
