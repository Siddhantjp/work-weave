import { ChevronDown, Clock3, Eraser, LogOut, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { HistoryRow, Me } from "../types";
import { ago } from "../util";
import Brand from "./Brand";

/** Small popover that closes on outside click or Escape. */
function Popover({ button, children, align = "right" }: { button: (open: boolean) => React.ReactNode; children: (close: () => void) => React.ReactNode; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <div onClick={() => setOpen(o => !o)}>{button(open)}</div>
      {open && <div className={`card absolute top-[calc(100%+10px)] z-30 w-[min(340px,86vw)] animate-rise p-2 shadow-lift ${align === "right" ? "right-0" : "left-0"}`}>{children(() => setOpen(false))}</div>}
    </div>
  );
}

interface Props { user: Me; history: HistoryRow[]; inWork: boolean; onNew: () => void; onOpen: (r: HistoryRow) => void; onLogout: () => void; onDeleted: () => void; onClearHistory: () => void }

function Avatar({ user, size = 8 }: { user: Me; size?: number }) {
  const cls = size === 10 ? "h-10 w-10" : "h-8 w-8";
  return user.picture
    ? <img src={user.picture} alt="" referrerPolicy="no-referrer" className={`${cls} rounded-full object-cover`} />
    : <span className={`${cls} grid place-items-center rounded-full bg-brand text-sm font-semibold text-white`}>{user.name[0]?.toUpperCase()}</span>;
}

function AccountMenu({ user, onLogout, onDeleted, onClearHistory }: Pick<Props, "user" | "onLogout" | "onDeleted" | "onClearHistory">) {
  const [confirm, setConfirm] = useState(false);
  return (
    <Popover button={open => (
      <button className="flex h-10 items-center gap-2 rounded-full border border-line-strong bg-white py-1 pl-1 pr-3 hover:bg-canvas" aria-expanded={open} aria-label="Account">
        <Avatar user={user} /><ChevronDown size={14} className="text-ink-3" />
      </button>)}>
      {() => (
        <div className="p-1">
          <div className="flex items-center gap-3 px-3 pb-3 pt-2.5">
            <Avatar user={user} size={10} />
            <p className="min-w-0 text-sm"><span className="block truncate font-semibold">{user.name}</span><span className="block truncate text-xs text-ink-3">{user.email}</span></p>
          </div>
          <div className="grid gap-0.5 border-t border-line pt-1.5">
            <button onClick={onLogout} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium hover:bg-canvas"><LogOut size={16} />Sign out</button>
            <button onClick={onClearHistory} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium hover:bg-canvas"><Eraser size={16} />Clear my search history</button>
            {!confirm
              ? <button onClick={() => setConfirm(true)} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-bad hover:bg-bad-soft"><Trash2 size={16} />Delete my account</button>
              : <div className="rounded-xl bg-bad-soft p-3">
                  <p className="text-sm text-bad">This deletes your account and everything you searched for. It cannot be undone.</p>
                  <div className="mt-3 flex gap-2">
                    <button onClick={onDeleted} className="btn h-10 flex-1 bg-bad px-3 text-sm text-white hover:brightness-110">Yes, delete</button>
                    <button onClick={() => setConfirm(false)} className="btn-ghost btn-sm flex-1">Keep it</button>
                  </div>
                </div>}
          </div>
        </div>
      )}
    </Popover>
  );
}

export default function TopBar({ user, history, inWork, onNew, onOpen, onLogout, onDeleted, onClearHistory }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-line/80 bg-canvas/80 backdrop-blur-md">
      <div className="mx-auto flex h-[68px] max-w-[1240px] items-center justify-between px-5 sm:px-8">
        <button type="button" onClick={onNew} aria-label="WorkWeave home"><Brand /></button>
        <div className="flex items-center gap-2">
          {inWork && <button className="btn-soft btn-sm" onClick={onNew}><Plus size={16} /><span className="hidden sm:inline">New search</span></button>}
          {history.length > 0 && (
            <Popover button={() => <button className="btn-ghost btn-sm"><Clock3 size={16} /><span className="hidden sm:inline">Recent</span></button>}>
              {close => (
                <ul className="grid gap-0.5">
                  <li className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Your searches</li>
                  {history.map(r => (
                    <li key={r.id}><button type="button" onClick={() => { onOpen(r); close(); }} className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-canvas">
                      <span className="line-clamp-2 text-[14.5px] font-medium leading-snug">{r.request}</span>
                      <span className="mt-0.5 block text-xs text-ink-3">{r.result?.ranked.length ?? 0} jobs · {ago(r.created_at)}</span>
                    </button></li>
                  ))}
                </ul>
              )}
            </Popover>
          )}
          <AccountMenu user={user} onLogout={onLogout} onDeleted={onDeleted} onClearHistory={onClearHistory} />
        </div>
      </div>
    </header>
  );
}
