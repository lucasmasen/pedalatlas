# PedalAtlas

**Explore further. Ride informed.**

Long-distance cyclists plan their routes in huge WhatsApp groups. The tips that matter (a campground that closed, a border rule that changed, where the water is) get buried under thousands of messages in several languages. PedalAtlas turns those chats into route-by-route briefs: pick two towns and get the latest rider notes for each stage, in your language, with anything about safety or borders checked by a person before riders see it.

Live app (Anbaric Cloud, sign-in required): https://pedalatlas.cloud.anbaric.ai

## Why it takes more than one model

One model can't do this job well on its own. Writing a readable brief, deciding whether that brief could hurt someone, checking it carefully, and taking responsibility for it are different tasks with very different costs. Each route request is an [Anbaric](https://anbaric.ai) job, and each step is done by the actor best suited to it:

| Step | Actor | Why this one |
|---|---|---|
| 1. Assemble the route | Code (`route-planner`) | Shortest path over a fixed highway graph. Deterministic, so no model is needed. |
| 2. Write the brief | **Claude Haiku 5.5** (`claude-haiku-5-5`) | A cheap, fast writer. It summarises the stage notes and translates them into the rider's language (English, Spanish, German, French or Portuguese). |
| 3. Score the risk | **Jev** (`typesafe-ai/jev` via Vercel AI Gateway) | A decision model, not a writer. It returns calibrated probabilities that the brief is safety-critical or gives border advice, so the review threshold is a number (0.5), not a vibe. |
| 4. Review flagged briefs | **Claude Opus 5.5** (`claude-opus-5-5`) | A careful, costly reviewer that runs **only on flagged briefs**. It checks every claim against the route data and source notes and tells the moderator what to fix (e.g. a border tip that is second-hand, or advice the brief added that no rider gave). |
| 5. Approve or withhold | **A person** (Anbaric `Await`) | If Opus recommends approving, the brief is published without waiting. If it recommends an edit or withholding, a moderator decides with Opus's advice in front of them. Every approval is recorded against the actor who made it. |

Every step is written to Anbaric's audit trail (`route-planner → claude-haiku-briefer → jev-risk-scorer → claude-opus-reviewer → awaiting a human → moderator`) and shown on the page as a "Who did what" table with the model, time, tokens and cost.

## Cost

Measured on the live app, Fairbanks → Whitehorse (8 stages, 830 km), brief in Spanish:

| | Per route |
|---|---|
| Claude Haiku 5.5 (every route) | about 1,080 input / 750–1,200 output tokens, 4–7 s, **about $0.0005–$0.0008** |
| Claude Opus 5.5 (flagged routes only) | about 1,100 input / 800–1,100 output tokens, about 11 s, **about $0.021–$0.023** |
| 1,000 route briefs | **about $0.60** from Haiku, plus about $0.02 for each one Jev flags |

At standard API pricing Haiku costs $0.10 / $0.50 per million input / output tokens and Opus $4 / $20, so Opus is about 30 times the price per brief. That is why it only sees what Jev flags. Jev is billed through Vercel AI Gateway.

## Privacy

The chats are private group conversations, and the riders in them didn't agree to be published.

- **Raw chat exports are not in this repository.** They are processed locally and never committed here.
- Senders become `rider-` pseudonyms. Phone numbers and emails are removed before anything is stored.
- **Only the public snapshot reaches a model.** `anbaric/src/atlas.json` holds route stages and simulated rider notes written for this demo. They are not messages from a real group. Private drafts never leave the laptop.
- Notes are shown as rider accounts with their dates, never as checked facts.
- A person approves anything about safety or borders.

## Run it

### The Anbaric app (the multi-model part)

Requires Node 20 or later.

```bash
cd anbaric
npm install
npx tsx src/main.ts
```

Open http://localhost:3000, pick two places and a language, then click **Show stages**.

- **With no keys** it still runs. Each model step falls back to an offline version and the table says so.
- **With Claude:** `export ANTHROPIC_API_KEY=...` before starting.
- **With Jev:** `export AI_GATEWAY_API_KEY=...` (a Vercel AI Gateway key; Jev needs paid Gateway credit, the free tier returns 403).

Deployed on Anbaric Cloud, the same keys are read from the secret store:

```bash
anbaric secrets set anthropic-api-key
anbaric secrets set ai-gateway-api-key
anbaric app deploy
```

### The Python wiki and pipeline (optional)

The Python side parses the chat exports, removes personal details, sorts notes by stage and topic, and serves a local wiki and map. The tests run without any private data. To rebuild the notes, put the WhatsApp `.zip` exports in the repository root; `.gitignore` keeps them, contact cards and `data/` out of git.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m scripts.run_community_agent   # needs the exports, writes data/private/
python -m backend.main                 # http://127.0.0.1:8000
```

## How it's built

```
WhatsApp exports (local only)
  └─ Python: parse → redact → pseudonymise → file notes by stage and need
       └─ public snapshot: anbaric/src/atlas.json
            └─ Anbaric app (TypeScript), one job per route request:
                 requested ─code─▶ assembled ─Claude Haiku─▶ briefed ─Jev─┬─ risk ≥ 0.5 ─▶ flagged ─Claude Opus─▶ review ─human─▶ ready | withheld
                                                          └─ low risk ──────────────────────────────────────▶ ready
```

| Path | What it does |
|---|---|
| `anbaric/src/machine.ts` | The route state machine |
| `anbaric/src/agents.ts` | The Haiku, Jev, Opus and moderator steps, plus their offline fallbacks |
| `anbaric/src/main.ts` | HTTP routes: request a route, read a job, record a moderator decision |
| `anbaric/src/page.ts` | The route page: language picker, brief, approve/withhold, trace table |
| `ingestion/`, `agents/`, `backend/` | Python: chat parsing, redaction, stage filing, local wiki |

## Limitations

- Routes are straight lines between towns along public highways. They are not a checked cycling itinerary.
- The rider-facing scope is Alaska to Vancouver, but most of the chat volume is further south (Mexico to Argentina). Extending the place list is the next step.
- On Anbaric Cloud a job takes about 30 seconds to pass through all its steps, longer just after a deploy. Locally it takes seconds.
- Jev needs paid Vercel AI Gateway credit. Without it, the risk step falls back to the categories the published notes already carry, and the trace says so.

## Built with

[Anbaric](https://anbaric.ai) for jobs, agents, human review, audit and hosting · [Claude](https://www.anthropic.com) Haiku 5.5 for briefs and Opus 5.5 for review · [Jev](https://vercel.com/changelog/ai-gateway-now-supports-typesafe-clients-and-an-http-api-for-jev) via Vercel AI Gateway for risk scoring.

Built at the Multi Model Hackathon, SF Tech Week, October 11 2026.
