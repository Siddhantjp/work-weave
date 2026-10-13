export const titleCase = (s: string) => s.replace(/\b\w/g, c => c.toUpperCase());
export const hour12 = (h24: number) => `${((h24 + 11) % 12) + 1} ${h24 % 24 >= 12 ? "PM" : "AM"}`;

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
export function ago(iso?: string | null): string {
  const t = iso ? new Date(iso).getTime() : NaN;
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return rtf.format(-mins, "minute");
  if (mins < 1440) return rtf.format(-Math.round(mins / 60), "hour");
  return rtf.format(-Math.round(mins / 1440), "day");
}

export function readFlag(key: string, fallback: boolean): boolean {
  try { const s = localStorage.getItem(key); return s === null ? fallback : s === "1"; } catch { return fallback; }
}
export function writeFlag(key: string, value: boolean) {
  try { localStorage.setItem(key, value ? "1" : "0"); } catch { /* storage unavailable */ }
}
