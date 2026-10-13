## A Stable Matching Market for Informal-Sector Work

A Multi-Agent Agentic AI System using LangGraph, Agentic RAG and Deferred Acceptance

Agentic AI (26CD7PEAAI) | Vineet R Kamath, Siddhant Patil | Guide: Dr. Seemanthini K

## 1. Problem Statement

India's informal sector — electricians, plumbers, delivery riders, drivers, domestic workers, security guards — employs the majority of the national workforce, yet these workers have no resumes, certifications or digital profiles. Their skills exist only as spoken self-description: "I have done house wiring for three years, I own my tools, I cannot work night shifts." Existing platforms serve them through keyword search and relevance ranking, which carries a structural defect that is rarely acknowledged: ranking is

one-sided. It optimises only what the platform believes the worker wants and ignores what the employer wants, producing a market in which mutually preferable pairings are systematically left unformed.

## The Core Defect — Blocking Pairs

A blocking pair is a worker W and an employer E such that W prefers E over the job W was actually matched to, AND E prefers W over the worker E actually hired. Both sides would be better off together, yet the system placed them apart. A matching containing blocking pairs is called unstable. Keyword ranking provides no guarantee against instability because it never models employer preferences at all. Every blocking pair is a real, measurable economic loss borne by two parties who could both have been made better off at zero additional cost.

This project reframes informal job matching as a two-sided matching market rather than a search-and-rank problem: on one side, real live-scraped listings carrying stated requirements (experience, locality, shift, vehicle ownership, wage band); on the other, worker profiles. The obstacle to applying classical matching theory is that it requires ranked preference lists and neither side possesses one — worker preferences exist as unstructured speech, employer preferences as unstructured listing text. Converting both into ranked orders while reasoning correctly about hard constraints and trade-offs is a task no deterministic solver can perform. This is where an agentic AI system is not merely convenient but necessary. Formally: design and implement a multi-agent agentic AI system that elicits preference orderings from unstructured worker self-descriptions and live- scraped listings using LLM-driven agentic retrieval, executes a provably stable two-sided matching mechanism over those preferences using LangGraph state orchestration, and empirically demonstrates that the resulting allocation contains measurably fewer blocking pairs than

conventional keyword-relevance ranking.

## 2. Objectives

- O1 — Acquire a real, live job-listing corpus. Build a scraper against public informal-work listing sources with rate limiting, backoff retries, robots.txt compliance and explicit block detection, and cache results to SQLite with acquisition timestamps, using no mock or placeholder listing

- data at any stage. • O2 — Elicit structured preferences from unstructured language. Implement an AutoGen two-agent Elicitor–Clarifier conversation that extracts skills, experience, location and hard constraints from a worker's spoken or typed self-description, with a mandatory human-in-the-loop

- confirmation step before any ranking occurs. • O3 — Construct ranked preference orders using Agentic RAG. Implement query transformation, retrieval grading, adaptive constraint relaxation and rejection-aware re-retrieval over a vector-indexed listing corpus, producing a justified rationale per ranked listing rather than a

- similarity score. • O4 — Orchestrate a two-sided market in LangGraph. Implement Gale–Shapley deferred acceptance as a stateful proposal loop with a typed state schema, conditional cyclical edges, per-round checkpointing and warm-start memory across successive scrapes. • O5 — Verify stability and strategyproofness. Exhaustively enumerate all worker–employer pairs to count blocking pairs, verify termination, and probe strategyproofness by instructing agents to misreport and confirming no improvement in outcome. • O6 — Quantify the improvement over conventional ranking. Implement a keyword-relevance baseline and report the difference in blocking- pair count on identical real listing data, supported by extraction precision/recall and an LLM-as-a-judge assessment of ranking rationales. • O7 — Deploy and instrument the system. Expose the pipeline through a FastAPI backend with a minimal worker-facing interface, and

- instrument every proposal round with LangSmith traces and AgentOps per-agent cost and performance monitoring.

## 3. Abstract

## 3.1 Introduction to the Problem

Informal employment is coordinated through brokers, contractors, word of mouth and digital classifieds, all of which match one side at a time: none computes an allocation accounting for both parties' preferences simultaneously. The result is an unstable market where a worker and an employer who would each have preferred the other end up matched elsewhere, and neither learns the better match existed. The deficiency is not data availability — live listings are public and carry explicit employer requirements — but mechanism: ranking is not allocation. Matching theory has solved allocation rigorously since 1962 and runs at national scale in medical residency and school admissions, but has never reached informal labour for one reason: it requires ranked preference lists, and this population has none.

## 3.2 Design and Implementation

The system is governed by a single architectural principle: the language model elicits preferences, and a proven mechanism allocates. The LLM is deployed only where it is irreplaceable — converting unstructured language into structured, ranked, justified preference orders. The allocation is performed by Gale–Shapley deferred acceptance, which carries guarantees of termination and stability no language model can offer. Listings are acquired by a live scraper against real public sources and cached to SQLite with timestamps; no mock data enters the system at any stage, and a scraper failure raises an explicit error rather than substituting synthetic listings. Cached listings are embedded and indexed in a vector store, forming the retrieval substrate for the agent layer. Elicitation is an AutoGen two-agent conversation: an Elicitor extracts skills, experience, location and hard constraints while a Clarifier challenges gaps and unstated assumptions. A human-in-the-loop interrupt then lets the worker confirm or correct the profile before ranking, so a misheard skill never

silently propagates into the allocation.


Preference construction is Agentic RAG rather than similarity lookup. The worker-side agent performs query transformation — rewriting one spoken description into several targeted queries covering role synonyms, constraint phrasings and equipment ownership — then grades each hit for viability, discarding hard conflicts such as shift clashes, missing licences or infeasible commutes, relaxing constraints when too few survive and tightening when too many do. Crucially, retrieval is market-state-aware: as a worker accumulates rejections the retriever excludes already-rejected employers and re- ranks over what remains, compressed rationales preventing the same non-viable options resurfacing. The employer-side agent mirrors this over worker profiles, ranking applicants strictly against the listing's stated requirements and deliberately blind to worker-side utilities — an enforced

asymmetry making the two sides genuinely opposed. The market is orchestrated as a LangGraph state machine: each proposal round is a node; rejection sets, tentative holds, capacity and the round

counter live in a typed state schema persisting across iterations; and a conditional edge routes control back to the proposal node while any unmatched worker retains an unexhausted option. This cyclical, state-dependent control flow — rather than a linear chain with a retry branch — distinguishes the system from a conventional pipeline. Every round is checkpointed, and a fresh scrape warm-starts from the previous matching.

## 3.3 Expected Results

Evaluation is structured so the headline result is verifiable by exhaustive computation rather than estimated by a model. Stability is checked by brute- force enumeration over all worker–employer pairs, giving a deterministic blocking-pair count: deferred acceptance is expected to yield zero, as theory guarantees, while the keyword baseline is expected to yield a substantial non-zero count. This difference on identical real listing data is the principal

empirical contribution. Three supporting results accompany it: strategyproofness, demonstrated by instructing a worker agent to misreport and verifying across repeated

probes that it never improves its outcome; extraction quality, measured against a hand-labelled set and reported as precision and recall; and ranking quality, scored by an LLM-as-a-judge evaluator — reported alongside the deterministic metrics, never in place of them, so no claim rests solely on a model's assessment of itself.

## 4. Brief Review

Gale and Shapley introduced deferred acceptance in 1962, proving a stable matching always exists for any two-sided market with strict preferences and is computable in polynomial time. Roth and Sotomayor (1990) extended it to many-to-one markets with capacities — the exact structure of a job market where one listing has several openings — and Dubins and Freedman (1981) established that the proposing side cannot benefit from misreporting, the property this project demonstrates empirically. These are not curiosities: deferred acceptance runs the US National Resident

Matching Program and the school-choice systems of New York and Boston, and Alvin Roth received the 2012 Nobel Memorial Prize for this work. Notably, Shoham and Leyton-Brown's Multi-Agent Systems: Algorithmic, Game-Theoretic and Logical Foundations is a prescribed reference text for this course and treats stable matching, mechanism design and strategyproofness directly — the theoretical spine of this project sits inside the

syllabus's own reading list. The reason matching theory has not reached informal labour is an input problem, not a theoretical one, and recent agentic architectures make the bridge tractable: ReAct interleaves reasoning with tool invocation, ReWOO separates planning from observation for structured extraction, Reflection enables self-critique, and Agentic RAG treats retrieval as iterative and self-corrective — the property this project depends on when relaxing or

tightening constraints. LangGraph supplies the stateful cyclical orchestration a multi-round protocol requires and linear chains cannot express. Existing informal-work platforms (OLX Jobs, Apna, WorkIndia) are search-and-rank systems, while recent LLM recruitment tools automate resume

parsing for the formal sector where structured resumes already exist. Neither computes a two-sided stable allocation or reports stability as a metric. The contribution here is not a new algorithm but a demonstrated bridge — and a measurement of what conventional ranking loses by not crossing it.

## 5. Agent Architecture

Seven components — five LLM-driven agents and two deterministic components, orchestrated by a LangGraph supervisor.

| # | Agent | What It Does | Pattern | Type |
| --- | --- | --- | --- | --- |
| 1 | Elicitor | Extracts skills, years of experience, location and hard constraints from the | ReWOO | LLM |
|   |   | worker's raw spoken or typed self-description. Structured output only — never | (AutoGen) |   |
|   |   | invents a skill that was not stated. |   |   |
| 2 | Clarifier | Challenges the Elicitor's output — probes gaps and ambiguity ("does 'wiring' | Reflection | LLM |
|   |   | mean domestic or industrial?"), as a two-agent AutoGen conversation. | (AutoGen) |   |
| 3 | Worker Preference | Builds the worker's ranked list over live listings: query transformation, viability | ReAct + | LLM |
|   | Agent | grading, hard-conflict rejection, adaptive relaxation. Outputs a rationale per | Agentic RAG |   |
|   |   | listing, not a similarity score. |   |   |
| 4 | Employer | Builds each listing's ranked list over applicants using only the listing's stated | ReAct + | LLM |
|   | Preference Agent | requirements. Deliberately blind to worker-side utilities — the enforced | Agentic RAG |   |
|   |   | asymmetry that makes the sides opposed. |   |   |
| 5 | Matcher | Executes Gale–Shapley deferred acceptance: workers propose, employers hold up | Deterministic | Code |
|   |   | to capacity and reject the rest, repeating until no unmatched worker has an | algorithm |   |
|   |   | option left. No LLM, by design. |   |   |
| 6 | Auditor | Exhaustively enumerates all worker–employer pairs to count blocking pairs, | Reflection | Code |
|   |   | verifies termination, runs strategyproofness probes, reports welfare. Feeds | feedback |   |
|   |   | extraction failures back to the Elicitor. |   |   |
| 7 | Supervisor | Routes proposal rounds, evaluates the convergence condition on the conditional | CWD — | Orchestr |
|   |   | edge, dispatches the worker and employer subgraphs, handles the unmatched- | Coordinator |   |
|   |   | worker fallback. |   | . |

Flow: worker description → Elicitor and Clarifier converse until the profile is complete → human-in-the-loop confirmation → Preference Agents independently build ranked lists via agentic retrieval → Supervisor dispatches the first round → Matcher runs proposals, holds and rejections → the conditional edge returns control while any unmatched worker retains an option → on convergence, the Auditor verifies stability.

Why This Is a Multi-Agent System, Not a Pipeline


Agents 3 and 4 hold private, structurally opposed objectives and cannot see each other's utilities. Their interaction is a multi-round protocol with persistent state — proposals, tentative holds, rejection sets — not a single pass. Remove the LLM agents and the mechanism has no preference lists to run on; remove the mechanism and the output is an unranked pile with no stability guarantee. Each half is necessary and neither is decorative.

## 6. Tools Used

| Tool / Framework | Role in the System | Module |
| --- | --- | --- |
| LangGraph | State machine orchestrating the deferred-acceptance proposal loop; typed state schema; | M2, M4 |
|   | conditional cyclical edges; per-round checkpointing; warm-start memory across scrapes |   |
| LangChain | Tool-calling interface, structured output parsing, retriever abstractions and chain | M1, M3 |
|   | composition for the preference-construction agents |   |
| AutoGen | Two-agent conversational elicitation — Elicitor extracts the worker profile, Clarifier | M4 |
|   | challenges gaps and ambiguity |   |
| LlamaIndex + Chroma | Document indexing, embedding storage and semantic retrieval over the cached listing corpus | M3 |
|   | and the worker-profile index |   |
| Anthropic Claude API | Reasoning model for extraction, preference ranking with rationale, retrieval grading and the | M1–M5 |
|   | LLM-as-a-judge evaluator |   |
| LangSmith + AgentOps | Trace capture per proposal round, evaluation datasets, blocking-pair and LLM-as-a-judge | M5 |
|   | evaluators; per-agent cost and performance monitoring |   |
| Scraper, SQLite, | Live acquisition of real listings with rate limiting, backoff retries, robots.txt compliance and | M2, M4 |
| FastAPI, HTML/JS | explicit block detection; cached store with timestamps and URL uniqueness; backend |   |
|   | exposing the matching pipeline plus a minimal worker-facing interface |   |

## Data Integrity Position

All job listings are real and live-scraped; no mock or hardcoded listing data is permitted at any stage, including development and testing. Worker profiles are explicitly simulated and labelled as such in code, interface and report, with their distribution grounded in national informal-sector employment survey statistics. Simulating market participants while using real market structure is standard practice in the matching-market literature, and the distinction is stated openly rather than obscured.

## 7. Applications

## 7.1 Real-World Scenario — The Delivery Rider

Ramesh owns a two-wheeler, has eighteen months of delivery experience, lives in Kammanahalli and cannot work past 9 PM because he cares for a parent. He searches "delivery job." The top results are night-shift roles in Electronic City — high paying, well ranked, entirely unworkable. He applies anyway because they are at the top, is rejected after a call, and repeats the cycle. Meanwhile a restaurant in Banaswadi, four kilometres away, advertises day-shift delivery work and specifically prefers riders who own a vehicle and have experience. Ramesh never sees it; the restaurant never sees Ramesh. They are a blocking pair, and the platform's ranking created them. Under this system his evening constraint is extracted and confirmed before ranking, the grader discards night-shift roles as hard conflicts, the Banaswadi listing's own preferences rank Ramesh well on the employer side, and deferred acceptance pairs them — stably.

## 7.2 Real-World Scenario — The Festival Surge

During a festival, twenty small businesses in a locality simultaneously advertise short-term electrical work, and forty electricians are available with differing skill depth, tool ownership, travel tolerance and rate expectations. A ranking system processes each query in isolation, so the two or three most visible listings absorb most applications while other employers receive none and skilled workers are matched below their capability. This is a market-clearing failure, not a search failure. A stable mechanism allocates all forty workers across all twenty employers in one coordinated round, respecting capacity and both sides' preferences simultaneously.

## 7.3 Extended Applications

- Skilled trade and apprenticeship placement — matching trainees to workshops where both the trainee's learning goals and the workshop's skill needs must be satisfied.

- Public healthcare staffing — allocating nurses and community health workers across primary health centres; the closest structural analogue to the NRMP, where this algorithm already runs nationally.

- Disaster-relief volunteer deployment — assigning volunteers with heterogeneous skills to sites with heterogeneous needs under time pressure, where unstructured self-description makes LLM elicitation essential.

- Government scheme allocation — matching applicants to limited-capacity schemes or training programmes where eligibility and preference are both in natural language and fairness is publicly scrutinised.

The practical value of stability is not abstract: an unstable allocation is one participants have an incentive to abandon, manifesting as early attrition — the worker leaves, the employer re-advertises, and the replacement cost falls on a business least able to absorb it. Stability therefore predicts placement durability, which for workers with no income buffer is the outcome that matters most.

## 8. Sustainable Development Goals Addressed

| SDG | Goal | Contribution |
| --- | --- | --- |
| SDG 8 | Decent Work and | Target 8.5 seeks full and productive employment and decent work for all. The system improves |
| Primary | Economic Growth | match quality in the informal labour market, where most of the workforce is employed and |
|   |   | placement is mediated by brokers and one-sided ranking. Stable matching raises placement |
|   |   | durability and cuts the repeated search cost borne by workers with no income buffer. |


| SDG | Goal | Contribution |
| --- | --- | --- |
| SDG 1 | No Poverty | Target 1.4 concerns equal rights to economic resources. Workers without resumes or digital |
| Supporting |   | credentials are structurally disadvantaged in digital labour markets; eliciting preferences from |
|   |   | spoken self-description rather than formal documentation removes a barrier correlating directly |
|   |   | with economic vulnerability. |
| SDG 10 | Reduced Inequalities | Target 10.2 seeks economic inclusion irrespective of status. One-sided ranking advantages |
| Supporting |   | listings with strong textual visibility and workers who articulate themselves in platform-friendly |
|   |   | vocabulary; computing allocation from both sides' stated preferences, with an externally |
|   |   | verifiable fairness property, reduces this structural bias. |

## A Note on Verifiability

This project's fairness claim is not rhetorical. Stability is a mathematically defined property, checkable by exhaustive enumeration over all participant pairs. The system can state precisely how many mutually preferable pairings its allocation leaves unformed, and compare that figure against the conventional approach on identical data. Social-impact claims in software projects are frequently asserted; here the central one is measured.

## 9. Future Enhancements

- Matching with contracts — negotiating wage and shift terms as part of the match rather than fixing them by the listing, following the Hatfield– Milgrom framework; converts allocation into genuine bilateral negotiation.

- Couples and joint constraints — supporting workers who must be placed together, common in migrant domestic and construction work; a known hard extension.

- Distributional constraints and dynamic markets — quotas or floors for underrepresented groups while preserving stability; and a move from periodic batch clearing to continuously arriving listings and workers.

- Multilingual voice-first elicitation — speech input in Kannada, Hindi and other regional languages, removing the literacy barrier limiting reach for the population targeted.

- Employer-side verification agent — an adversarial agent cross-checking listing authenticity against duplicate postings and known fraud patterns, addressing fake listings.

- Explainability surface — showing each worker why their match was assigned and that no blocking pair exists for them, turning the stability guarantee into something they can see and contest.

Deployment carries two risks treated here as design requirements: scoring heuristics must never be presented as verified credentials, since an opaque score a worker cannot contest entrenches disadvantage; and human-in-the-loop confirmation must stay mandatory, being the only point at which an extraction error can be corrected before it affects income.

## 10. References

[1] Gale, D. and Shapley, L. S. (1962). College Admissions and the Stability of Marriage. American Mathematical Monthly, 69(1), 9–15. [2] Roth, A. E. and Sotomayor, M. (1990). Two-Sided Matching. Cambridge University Press. [3] Dubins, L. E. and Freedman, D. A. (1981). Machiavelli and the Gale–Shapley Algorithm. American Mathematical Monthly, 88(7), 485–494. [4] Shoham, Y. and Leyton-Brown, K. (2009). Multi-Agent Systems. Cambridge University Press. [Prescribed reference] [5] Biswas & Talukdar (2025), Building Agentic AI Systems, Packt [T1]. [6] Oshin & Campos (2025), Learning LangChain, O'Reilly [T2]. [7] Lanham (2025), AI Agents in Action, Manning [T3]. [8] Yao et al. (2023), ReAct, ICLR. [9] Xu et al. (2023), ReWOO, arXiv:2305.18323.
