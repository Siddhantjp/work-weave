export class ApiError extends Error {}

/** Turns technical backend messages into wording a customer can act on. */
export function friendly(msg: string): string {
  if (/rate limit|429|tokens per/i.test(msg)) return "We are getting a lot of requests right now. Please try again in a minute.";
  if (/GROQ_API_KEY|api key/i.test(msg)) return "This feature is unavailable right now. Please try again later.";
  return msg;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try { r = await fetch(path, init); }
  catch { throw new ApiError("We cannot reach the server. Check your internet connection and try again."); }
  if (!r.ok) {
    let detail: unknown = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not json */ }
    throw new ApiError(friendly(typeof detail === "string" ? detail : "Something went wrong. Please try again."));
  }
  return r.json() as Promise<T>;
}

export const get = <T = any>(path: string) => request<T>(path);
export const post = <T = any>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const del = <T = any>(path: string) => request<T>(path, { method: "DELETE" });
export const postAudio = <T = any>(path: string, blob: Blob) =>
  request<T>(path, { method: "POST", headers: { "content-type": blob.type }, body: blob });

export interface TaskEvent { node: string; message: string }
interface Task<T> { status: "running" | "done" | "failed"; events: TaskEvent[]; result: T | null; error: string | null }

/** Polls a backend task, reporting progress events as they arrive. */
export async function pollTask<T = any>(id: string, onEvents: (e: TaskEvent[]) => void): Promise<T> {
  for (;;) {
    const t = await get<Task<T>>(`/api/tasks/${id}`);
    onEvents(t.events);
    if (t.status === "done") return t.result as T;
    if (t.status === "failed") throw new ApiError(friendly(t.error ?? "Something went wrong. Please try again."));
    await new Promise(r => setTimeout(r, 700));
  }
}
