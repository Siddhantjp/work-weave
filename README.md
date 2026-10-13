# WorkWeave — agentic job search for Bengaluru

Sign in with Google, say what work you want, and an AI agent checks **apna.co** live, retrieves the closest listings,
reads their requirements, and ranks them for you. Built with **LangChain + LangGraph + Groq**, traced end to end in **LangSmith**.

## Run

```
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
copy .env.example .env          # then fill in GROQ_API_KEY, GEMINI_API_KEY, LANGSMITH_API_KEY, GOOGLE_CLIENT_ID/SECRET
cd frontend && npm ci && npm run build && cd ..
start.bat                       # http://localhost:8000
```

Tests (offline: no network, Groq or LangSmith): `cd backend && ..\.venv\Scripts\python -m pytest -q`

## How a search works

```
understand → check_source → retrieve → grade_documents → augment → grade_limits → finish
  Groq #1     apna.co tool   Gemini      drop off-topic     Groq #2      hard limits
 (profile +   (live scrape,  multi-query  & expired         (read reqs,  enforced
  query plan)  polite)       MMR + RRF    listings (code)    rank, why)   by code
```

Two decision points loop back through `relax` (adds related trades, retrieves deeper). Hard limits such as
"cannot work after 9 PM" are enforced by code and are never relaxed. The LLM may only put in the profile what the
worker actually wrote (every field needs a quote that is verified by string match).

Each search is one LangSmith run named `job_search_agentic_rag` in project `LANGSMITH_PROJECT`, with every node, the
Groq calls, the scrape tool and each retriever call nested under it, plus four code-based evaluator scores
(`hard_limit_violations`, `profile_grounding`, `source_fresh_or_live`, `results_found`).

## Voice and languages

Press 🎤 on the search page and speak. The browser records, the backend sends the clip to **Whisper (`whisper-large-v3-turbo`) on
Groq**, and the transcript lands in the text box for you to check before the search runs (or runs straight away if
"Search right after I speak" is ticked). Pick a language or leave it on Auto-detect: English, Hindi, Kannada, Tamil, Telugu,
Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu.

You can also just type in any of those languages. The agent understands the request in that language, matches your words
against the listings in English, and **writes its explanations back in your language**. The "quote must appear in your own
words" check runs on the original script, so nothing is invented in translation. Audio is never stored. Accuracy on short or
noisy clips, especially for less common languages, is imperfect, which is why you always see the transcript first.

## Accounts and data

Three storage areas, deliberately separate:

| What | Where | Why |
|---|---|---|
| Users, login sessions, **what each user searched for** and the results they saw | **Accounts database**: `DATABASE_URL` (Postgres in production) or `data/users.db` locally; code in `app/accounts/` | Personal data. Must survive deploys; must be erasable. |
| Scraped listings, scrape log, geocodes, listing embeddings | `data/listings.db` (SQLite) | Public data that can be re-scraped and re-embedded at any time. |
| Cached LLM answers | `data/llm_cache.db` | Contains prompts (so what users typed), kept away from listings. |

Sign-in is **Google OAuth** only (no passwords stored). Accounts are matched on Google's stable id, sessions are random tokens of which only
a hash is stored, and users can clear their history or delete their account and everything in it from the account menu.
Setup: Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (Web application) → add the authorised redirect URI
`http://localhost:8000/api/auth/google/callback` (and your Render URL's equivalent later) → put the id and secret in `.env`.

## Deploying to Render

`render.yaml` describes a web service and a Postgres database. Push to GitHub → Render → New → Blueprint, then fill the secrets it asks for
(`GROQ_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BASE_URL`, LangSmith keys) and add the Render URL's callback to the Google client.
Notes: Render's free web disk is wiped on every deploy and restart, which is fine for listings, vectors and the LLM cache (they rebuild) but is
exactly why accounts live in Postgres. Render's free Postgres expires after 30 days; for a longer-lived free database use Neon or Supabase and
paste their connection string into `DATABASE_URL`. The free instance has 512 MB of RAM: embeddings are therefore computed by the hosted Gemini API (`GEMINI_API_KEY`) instead of a local model, which keeps the app at roughly 130 MB.

## Layout

```
backend/app/
  config.py  db.py  models.py  llm.py  auth.py  tasks.py     settings · listings DB · data models · Groq + cache · who-is-calling · background tasks
  accounts/   store.py: users, sessions, searches (SQLAlchemy; Postgres or SQLite)
  api/        main + routes_auth (Google OAuth) / routes_search / routes_data / routes_voice
  sources/    apna.py (scraper) · geo.py (Nominatim distances) · refresher.py · cli.py
  search/     graph.py (LangGraph) · chains.py (LCEL prompts) · retrieval.py · index.py · tools.py
              limits.py · extraction.py · schemas.py · tracing.py
  matching/   stable-matching extension (Gale–Shapley, audit, keyword baseline, simulations); not wired into the UI yet
backend/tests/   frontend/ (React + Vite + Tailwind, fonts bundled; `npm run build` outputs to frontend/dist)
```

## Data honesty

* Listings are real, scraped from apna.co (robots.txt honoured, 2.5 s between requests) and stored with the time they were fetched.
  If apna.co cannot be reached the app says so and falls back to previously cached listings; it never invents any.
* Simulated workers exist only in the `matching` extension and are labelled `simulated`.
* Check apna.co's terms of service before using this beyond a demo.

## Free-tier limits (Groq)

`gpt-oss-120b` allows about 8,000 tokens per minute and 200,000 per day. A search uses two calls; identical prompts are
answered from a persistent cache. If a limit is hit the app shows Groq's message.

## Optional commands

* Scrape by hand: `cd backend && ..\.venv\Scripts\python -m app.sources.cli --trades delivery --stats`
* Stable-matching experiment (uses many LLM calls): `..\.venv\Scripts\python -m scripts.run_experiment --n 12`
