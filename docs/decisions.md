# Decisions

The rules this product is built on. A change that breaks one of these needs a new decision here first.

## ADR-001: Private chat never leaves the laptop

WhatsApp exports, private claim drafts and anything in `data/private/` stay local and are never committed. Zip exports, contact cards (`.vcf`) and SQLite files are gitignored. Senders become salted `rider-` pseudonyms and phone numbers and emails are redacted before anything is stored.

## ADR-002: Only the public snapshot reaches a model

Model calls receive route stages and notes from `anbaric/src/atlas.json` and nothing else. No model, API or third-party service is ever sent private draft text, sender ids or raw messages.

## ADR-003: Rider notes are accounts, not facts

Every note shown to a rider is attributed to riders and keeps its date. Briefs never state a note as verified fact, never invent towns, distances, rules or services, and say plainly when no note covers a stretch. Route distances are straight lines between towns and are labelled that way.

## ADR-004: Each model does one job

- Claude Haiku 5.5 writes every brief, in the rider's language. It is the cheap, fast default.
- Jev scores safety and border risk as probabilities. The review threshold is a number (`RISK_THRESHOLD`, 0.5).
- Claude Opus 5.5 reviews only briefs the risk step flags. It never runs on every request, because it costs about 30 times more than Haiku per brief.
- A model step that fails or has no key falls back offline and records why in the trace. A model failure never fails the route job.

## ADR-005: A person signs off on risky advice

A brief flagged for safety or border risk is never shown to riders as approved unless a person approves it, or Claude Opus reviews it and recommends `approve`. A brief Opus recommends editing or withholding always waits for a person. Every approval is recorded in the Anbaric audit trail against the actor who made it.

## ADR-006: Every step is an auditable actor

Each step of a route job runs as a named Anbaric actor (`route-planner`, `claude-haiku-briefer`, `jev-risk-scorer`, `claude-opus-reviewer`, or the human moderator) and appends its model, time, tokens and cost to the job's `trace`.

## ADR-007: Keys live in the secret store

API keys are read from the Anbaric secret store (`anthropic-api-key`, `ai-gateway-api-key`), which falls back to `ANTHROPIC_API_KEY` and `AI_GATEWAY_API_KEY` locally. Keys are never committed, logged, or put in a URL.
