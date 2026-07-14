# Personio Call-Prep Agent — Approach

## Scope

**The pitch:** an assistant that helps AEs surface what they might miss before a call — not "a chatbot for sales." Today, prep means four systems (Salesforce, Gong, Drive, Slack) and tribal memory, and the synthesis — what changed, what's easy to miss, which battlecard applies — lives in the AE's head, inconsistently. The redesign puts that synthesis *in* the tool instead of leaving it as a skill some AEs have and others don't.

**Built:** a multi-turn conversational agent (Claude, native tool use) over live Snowflake CRM/product/support data (7 tools) and Personio's 7 sales enablement docs (keyword search over Drive content). Every answer shows its sources; every response has thumbs-up/down feedback.

**Cut, deliberately:**
- **Enterprise AE flow** — the interview notes are explicit that enterprise (Ines: 12-stakeholder cycles, needs stakeholder-connecting) and mid-market (fast context, gap-surfacing) are different problems; building one thing for both was named as a specific failure mode by the interviewee herself.
- **A bespoke "what changed" detection model** — asking Claude to reason over raw tool output, with an explicit instruction to lead with what's notable, gets most of the value at a fraction of the build/iteration cost of a dedicated scoring pipeline.
- **In-call support** — Sofia wants to be "nudged" mid-call, but the brief itself defines the shape as pre-call Q&A ("the AE asks, the agent answers, the AE drills in"). Building live-call support would be scope creep relative to the brief, not a gap in meeting it.
- **Persistent memory, Salesforce write-back, proactive push** — real ideas, out of scope for a same-day prototype (see *Path to production*).
- **Text-to-SQL** — the model never writes its own SQL. The case brief's described schema (`CASE_STUDY.GTM`) didn't match what's actually provisioned (`PERSONIO.CRM/PRODUCT/SUPPORT`); I verified the real schema by hand and wrote 7 fixed, parameterized queries against it.

## Architecture

**No agent framework.** A `while` loop around Claude's tool-use API (`agent.py`) is the entire runtime. At ~75 accounts and 7 documents, LangChain-style orchestration adds indirection without solving a real problem, and a loop anyone can read top to bottom is a better artifact for a technical deep-dive.

**Two tool families:** enablement search (`playbook_search.py` — keyword-ranked doc sections, no vector DB; 7 short docs don't justify embeddings) and account data (`snowflake_tools.py` — fixed parameterized queries, not a query-writing agent, for the same reason text-to-SQL was cut). Snowflake connections are reused across a turn's 5-6 queries rather than reconnected each time.

**Grounding is a hard rule.** The prompt instructs the model to never state an ungrounded fact and say "I don't have that" rather than guess — directly from Sofia Alvarez's interview: *"I'd rather it told me less and was right than told me more and was wrong sometimes."* This is checkable, not just claimed: every answer's Sources panel lists the exact tool calls behind it, and every call is logged with latency and outcome.

## Quality — what "good" means and how I'd measure it

1. **Zero fabricated facts** — the trust bar the AEs set themselves. `eval_suite.py` is a small starter version: scripted conversations asserting on tool usage (right account resolved, unknown accounts fail honestly, follow-ups hold context) rather than eyeballed transcripts. A real launch needs a much larger hand-verified golden set grading every claim for tool-traceability.
2. **Does it surface what a Salesforce skim would miss?** Harder to grade automatically — needs human review against a golden set. Actually running the eval suite surfaced a real, non-obvious finding (two system-prompt instructions in tension, resolved well by the model but not by my first test) — the full log is in `TESTING_NOTES.md`, since testing found several genuine issues that reading the code alone wouldn't have.
3. **Speed** — an AE prepping in a 10-minute gap won't wait per turn. Every tool call is timed; connection reuse already measured ~3.6s (first call, auth) vs. ~200-660ms (subsequent calls, same turn).
4. **Would she reach for it tomorrow?** Marcus's interview is the sharpest adoption signal: skeptical AEs try once and don't come back if it doesn't earn its keep immediately. I'd track week-4 weekly-active-AE rate over any offline benchmark; the thumbs-up/down capture is day-one instrumentation toward that, not a v2 idea.

## Path to production

- **Auth & governance:** real SSO-based Snowflake access per AE (not a shared credential); register in Personio's Tool Register with a named owner and documented data-access scope.
- **Eval harness:** grow `eval_suite.py` into the full golden set above, run in CI against every prompt change.
- **Guardrails:** explicit deal-desk escalation handling for pricing questions near approval thresholds, rather than the agent improvising.
- **Proactive, in two distinct forms:** a pushed daily brief (Lena's "tell me what I'd miss," pre-call) and Sofia's in-call nudge (real-time, a genuinely different product surface) — worth keeping separate rather than one roadmap line.
- **Personalization by tenure:** Sofia wants the playbook explained; Marcus wants zero hand-holding. One prompt for both is a v1 simplification.
- **Beyond this build:** the natural next slices are manager forecast-prep and CS renewal-prep (same data, different synthesis question), and moving the surface into Slack/Salesforce rather than a standalone app — a tool you have to remember to open is its own adoption tax.

## Status

All three integrations (Snowflake, Drive, Anthropic) are live and verified end-to-end — see `scenarios.py` and `TESTING_NOTES.md`. Getting Snowflake working surfaced two real sandbox access-control issues (MFA blocking programmatic password auth; PATs separately requiring a network policy), both diagnosed and resolved without elevated privileges — see `README.md`'s Status section for specifics.
