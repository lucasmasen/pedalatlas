# PedalAtlas

**Explore further. Ride informed.**

Long-distance cyclists plan their routes in huge WhatsApp groups. The tips that matter (a campground that closed, a border rule that changed, the last water tap for 175 km) get buried under thousands of messages in several languages. PedalAtlas turns those messages into route-by-route briefs: pick two towns and a language, see the route on a map with every rider note along it, and get a short brief that a chain of models has written, risk-scored and reviewed, with a person signing off on border advice.

- **Live app** (Anbaric Cloud, sign-in required): https://pedalatlas.cloud.anbaric.ai
- **Run it yourself** without any account or key: see [Run it](#run-it).
- **All rider notes in this repository are simulated.** The real group chats never leave our laptops (see [Privacy](#privacy)).

## Why it takes more than one model

Writing a readable brief, deciding whether it could hurt someone, checking it carefully, and taking responsibility for it are different jobs with very different costs. Each route request is an [Anbaric](https://anbaric.ai) job, and each step is done by the actor that suits it:

| Step | Actor | Why this one |
|---|---|---|
| 1. Assemble the route | Code (`route-planner`) | Shortest path over a fixed highway graph of 48 towns and 44 highway segments. Deterministic, so no model is needed. |
| 2. Write the brief | **Claude Haiku 5.5** (`claude-haiku-5-5`) | A fast, cheap writer that runs on every route. It turns the stages and the newest note per topic into a short brief in the rider's language (English, Español, Deutsch, Français or Português), translating notes written in other languages, and attributes every note to riders with its date. |
| 3. Score the risk | **Jev** (`typesafe-ai/jev`, by TypeSafe, via Vercel AI Gateway) | A decision model, not a writer. It returns probabilities that the brief is safety-critical or gives border advice, so "needs review" is a number (`RISK_THRESHOLD = 0.5`), not a judgement buried in prose. |
| 4. Review flagged briefs | **Claude Opus 5.5** (`claude-opus-5-5`) | A careful reviewer that runs **only on briefs Jev flags**, because it costs about 30 times more than Haiku. It checks every claim against the route stages and source notes, recommends approve, edit or withhold, explains why in plain English, and when it recommends an edit, writes the corrected brief. |
| 5. Approve | **Claude Opus or a person** (Anbaric `Await`) | A brief flagged only for safety that Opus approves is published straight away. **Border, visa and legal advice always waits for a person**, as does anything Opus wants edited or withheld. The moderator sees Opus's advice and can publish Opus's rewrite in one click. |

Every step runs as a named Anbaric actor and is recorded in the audit trail (`route-planner → claude-haiku-briefer → jev-risk-scorer → claude-opus-reviewer → awaiting a human → moderator`). The page shows the same chain as a **"Who did what"** table with each step's model, time, tokens and cost.

```
requested ─code─▶ assembled ─Haiku─▶ briefed ─Jev─┬─ risk < 0.5 ─────────────────────────────────────────▶ ready
                                                 └─ risk ≥ 0.5 ─▶ flagged ─Opus─┬─ approve + safety ─────────▶ ready
                                                                                └─ border, edit or withhold ─▶ review ─person─▶ ready | withheld
```

### Design decisions, checked on every pull request

The rules above are written down in [`docs/decisions.md`](docs/decisions.md): private chat never leaves the laptop, only the public snapshot reaches a model, notes are accounts and not facts, each model has one job, a person signs off on risky advice, every step is auditable, and keys live in the secret store. [Prelint](https://prelint.com) reviews each pull request against them. On [pull request #1](https://github.com/lucasmasen/pedalatlas/pull/1) it flagged that letting Opus auto-approve the riskiest briefs removed human oversight where the stakes are highest; we agreed and now keep border advice with a person.

## Cost

Measured on the live app, Fairbanks → Whitehorse (8 stages), standard API pricing:

| Step | Time | Cost per route |
|---|---|---|
| Claude Haiku 5.5 (every route) | 2.5–7.5 s | $0.0002–$0.0009 |
| Jev (every route) | 0.3–1 s | about $0.00002 |
| Claude Opus 5.5 (flagged routes only) | 5–16 s | $0.013–$0.038 |

A route Jev doesn't flag costs **under a tenth of a cent**, so 1,000 of them cost about $0.25–$0.95. A flagged route costs about **2–4 cents**, because that is where the careful model runs. Haiku is $0.10 / $0.50 and Opus $4 / $20 per million input / output tokens; Jev is billed through Vercel AI Gateway.

## Privacy

The source chats are private group conversations, and the riders in them didn't agree to be published.

- **No real chat is in this repository.** The WhatsApp exports, contact cards and the private database stay on our laptops. `.gitignore` blocks `*.zip`, `*.vcf`, root-level `*.txt` and `data/`, and [`tests/test_public_repo_privacy.py`](tests/test_public_repo_privacy.py) fails the build if a chat export, contact card, database, real phone number, export-style message line or API key is ever committed.
- **The 31 rider notes in [`anbaric/src/atlas.json`](anbaric/src/atlas.json) and the texts in the slide demo are simulated**, written for this demo. The live page says so in a banner.
- **Only that public snapshot reaches a model.** Models receive stage names, highways, distances and the simulated notes, never private drafts, sender ids or raw messages.
- When the real pipeline runs locally, senders become salted `rider-` pseudonyms and phone numbers and emails are redacted before anything is stored.
- Notes are shown as rider accounts with their dates, never as checked facts.

## Run it

### The route app (the multi-model part)

Requires Node 20 or later.

```bash
cd anbaric
npm install
npx tsx src/main.ts
```

Open http://localhost:3000, pick two places and a language, then click **Show stages**. The map shows the highway corridor, the planned route along the real roads, and a pin for every simulated rider note (click a pin to read the notes at that town). Scroll or pinch to zoom.

- **With no keys** it still runs end to end. Each model step falls back to an offline version and the "Who did what" table says so.
- **With Claude:** `export ANTHROPIC_API_KEY=...` before starting (used by both Haiku and Opus).
- **With Jev:** `export AI_GATEWAY_API_KEY=...`, a Vercel AI Gateway key with paid credit (the free tier returns 403 for Jev).

On Anbaric Cloud the same keys are read from the secret store:

```bash
anbaric secrets set anthropic-api-key
anbaric secrets set ai-gateway-api-key
anbaric app deploy
```

### How chat becomes notes (slide demo)

A live, step-by-step demo of the real Python pipeline on simulated rider texts: messages arrive one by one, are redacted and stored, claims are extracted by the community agent, and wiki notes are filed by stage and need. These steps are rule-based; no model writes the notes. The last two slides show what happens next: notes scored for safety and border risk and flagged at 0.5, then a person approving or withholding each flagged one. The demo has no model keys, so each note's category stands in for Jev there. No private data or API keys needed.

```bash
pip install -e .
python -m demo.wiki_notes.server   # http://127.0.0.1:8091
```

### The Python wiki and tests

The Python side parses WhatsApp exports, redacts and pseudonymises them, extracts claims, files notes by stage and need, and serves a local wiki and map. The tests run without any private data.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # 34 tests, including the privacy checks
python -m backend.main                   # local wiki, http://127.0.0.1:8000
```

To rebuild notes from real exports, put the WhatsApp `.zip` files in the repository root (git ignores them) and run `python -m scripts.run_community_agent`, which writes to `data/private/`.

## How it's built

```
WhatsApp exports (local only)
  └─ Python: parse → redact → pseudonymise → extract claims → file by stage and need   (rule-based)
       └─ public snapshot: anbaric/src/atlas.json   (towns, highways, road shapes, simulated notes)
            └─ Anbaric app (TypeScript): one job per route request, steps run by code, Haiku, Jev, Opus and a person
```

| Path | What it does |
|---|---|
| `anbaric/src/machine.ts` | The route state machine: states, transitions, job properties |
| `anbaric/src/agents.ts` | The Haiku, Jev and Opus steps, the moderator `Await`, cost tracking and offline fallbacks |
| `anbaric/src/corridor.ts` | Route finding over the highway graph, notes per route, map data |
| `anbaric/src/main.ts` | HTTP routes: request a route, read a job, record a moderator decision |
| `anbaric/src/page.ts` | The page: map, language picker, brief, moderator buttons, "Who did what" table |
| `anbaric/src/atlas.json` | The public snapshot: 48 towns, 44 highway segments with road shapes, 31 simulated notes |
| `demo/wiki_notes/` | The slide demo of the Python pipeline |
| `ingestion/`, `agents/`, `backend/` | Python: chat parsing, redaction, claim extraction, stage filing, local wiki |
| `docs/decisions.md` | The product decisions Prelint reviews against |

## Limitations

- **Distances are straight lines between towns**, so they understate the ride (Fairbanks → Whitehorse is about 830 km straight-line and about 970 km by road). The map draws the real highways, using road shapes fetched once from OpenStreetMap via the OSRM demo router, but routing and the distances in briefs still use the straight-line graph. It is not a checked cycling itinerary.
- **Only the newest note per topic reaches the brief**, so an older note that contradicts a newer one isn't shown to the models. The map shows every note.
- The rider-facing scope is Alaska to Vancouver, while most of the real chat volume is further south (Mexico to Argentina).
- The live app is behind Anbaric sign-in. On Anbaric Cloud a route takes about 30 seconds to pass through every step, longer right after a deploy; locally it takes seconds.

## Built with

[Anbaric](https://anbaric.ai) for jobs, agents, human approval, audit, secrets and hosting · [Claude](https://www.anthropic.com) Haiku 5.5 for briefs and Opus 5.5 for review · [Jev](https://vercel.com/changelog/ai-gateway-now-supports-typesafe-clients-and-an-http-api-for-jev) by TypeSafe via Vercel AI Gateway for risk scoring · [Prelint](https://prelint.com) for decision review on pull requests · [Leaflet](https://leafletjs.com) and [OpenStreetMap](https://www.openstreetmap.org) for the map.

Built by Mark Choe, Lucas Masen and team at the Multi Model Hackathon, SF Tech Week, October 11 2026.
