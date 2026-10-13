import { Globe, Mic, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { get } from "../api";
import Brand from "./Brand";

const POINTS = [
  [Mic, "Speak your request", "No typing needed. Just tell us the work you want."],
  [Globe, "Your language", "हिन्दी · ಕನ್ನಡ · தமிழ் · తెలుగు · English and more"],
  [ShieldCheck, "Fits your hours", "Jobs that clash with your timings are left out."],
] as const;

const ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled. You can try again whenever you are ready.",
  unverified: "Your Google email is not verified, so we could not sign you in.",
  failed: "We could not complete sign-in. Please try again.",
  not_configured: "Sign-in is not available right now. Please try again later.",
};

function GoogleG() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z" />
      <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}

export default function Login({ notice }: { notice?: string }) {
  const [google, setGoogle] = useState<boolean | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(() => {
    const code = new URLSearchParams(location.search).get("auth_error");
    return code ? ERRORS[code] ?? ERRORS.failed : undefined;
  });

  useEffect(() => {
    get<{ google: boolean }>("/api/auth/providers").then(p => setGoogle(p.google)).catch(() => setGoogle(false));
    if (location.search.includes("auth_error")) history.replaceState(null, "", location.pathname);        // keep the address bar clean
  }, []);

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="dots pointer-events-none absolute -right-10 -top-10 h-80 w-96 [mask-image:linear-gradient(to_bottom_left,black,transparent_70%)]" aria-hidden />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-6">
        <header className="flex h-20 items-center"><Brand size={38} /></header>

        <main className="grid flex-1 items-center gap-12 pb-16 pt-4 lg:grid-cols-[1.15fr_1fr] lg:gap-20">
          <section className="animate-rise">
            <p className="inline-flex h-8 items-center rounded-full bg-sun-soft px-4 text-[13px] font-semibold text-sun-ink">Jobs in Bengaluru</p>
            <h1 className="mt-5 text-[clamp(2.4rem,6vw,4rem)] leading-[1.05]">Work that fits your life, found in your own words.</h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">Tell us what you do, where you live and when you can work. We check the latest openings and show the ones that suit you.</p>
            <ul className="mt-10 hidden gap-5 sm:grid">
              {POINTS.map(([Icon, title, text]) => (
                <li key={title} className="flex items-start gap-4">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand"><Icon size={20} /></span>
                  <div><p className="font-semibold">{title}</p><p className="text-[15px] text-ink-2">{text}</p></div>
                </li>
              ))}
            </ul>
          </section>

          <section className="animate-rise [animation-delay:90ms]">
            {notice && <p className="mb-4 rounded-2xl bg-brand-soft px-4 py-3 text-sm font-medium text-brand-ink" role="status">{notice}</p>}
            <div className="card p-7 sm:p-9">
              <h2 className="text-[1.65rem]">Get started</h2>
              <p className="mt-1 text-[15px] text-ink-2">Sign in to find your next job. Your account is created automatically the first time.</p>
              {error && <p className="mt-5 rounded-2xl bg-bad-soft px-4 py-3 text-sm font-medium text-bad" role="alert">{error}</p>}
              <a href="/api/auth/google/login" aria-disabled={google === false}
                className={`btn-ghost mt-7 w-full gap-3 text-base shadow-sm ${google === false ? "pointer-events-none opacity-50" : "hover:shadow-card"}`}>
                <GoogleG />Continue with Google
              </a>
              {google === false && <p className="mt-3 text-center text-sm text-ink-3">{ERRORS.not_configured}</p>}
              <p className="mt-6 text-center text-[13px] leading-relaxed text-ink-3">We only use your name and email to keep your searches safe. You can delete your account and everything you asked for at any time.</p>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
