# Personio Call-Prep Agent — Approach

## Scope

**Built:** a conversational assistant an AE can chat with about any of their accounts — multi-turn, follow-ups keep context. It pulls live CRM/product/support data from Snowflake (7 tools: find account, account summary, contacts, opportunities, activities, product usage, support tickets) and cross-references 7 sales enablement docs from Drive (playbook, ICP, battlecards, objection handling, pricing, case studies) via keyword search. One system prompt, no bespoke ML.

**Cut, deliberately:**
- **Enterprise AE flow.** The AE interview notes (`research/13_ae_interview_notes.md`) are explicit that enterprise (Ines Dubois: 5 accounts, 12-stakeholder cycles, wants *"help connecting dots across stakeholders,"* not context retrieval) and mid-market (Sofia, Lena, Thomas: 30-40 accounts, wants fast context and gap-surfacing) are different problems. Building one thing for both was named as a specific failure mode by the interviewee herself. I scoped to mid-market only, matching the case persona.
- **A bespoke "what changed" detection model.** The single clearest unmet need across interviews was surfacing what the AE would otherwise miss — not restating known facts. I considered building a dedicated diffing/anomaly-scoring pipeline over activity/usage/ticket history. Cut it: asking Claude to reason over the raw tool output, guided by an explicit instruction to lead with what's notable, gets most of the value at a fraction of the build and iteration cost, and is easier to correct via prompt changes than a scoring model would be.
- **Persistent memory, Salesforce write-back, proactive push/notifications.** All real product ideas (see *Path to production*), all out of scope for a same-day prototype.
- **Text-to-SQL.** The model never writes its own SQL. Given the case brief's described schema (`CASE_STUDY.GTM`) didn't match what's actually provisioned (`PERSONIO.CRM/PRODUCT/SUPPORT`), I didn't trust either the brief or a model's guess — I verified the real schema by hand in the Snowflake UI and wrote 7 fixed, parameterized queries against it instead.

## Architecture & key technical choices

**No agent framework.** Claude's native tool-use API in a plain `while` loop (`agent.py`) is the entire agent runtime. At ~75 accounts and 7 documents, LangChain-style orchestration adds indirection without solving a real problem — and a loop anyone can read top to bottom is a better artifact for a technical deep-dive than a framework's abstractions.

**Two tool families, kept separate on purpose:**
- **Enablement search** (`playbook_search.py`) — the 7 docs are split into `##`-level sections (~800 lines of source total) and ranked by keyword overlap. No vector DB: at this corpus size, embeddings solve a problem I don't have. This is the first thing I'd swap for real retrieval if the doc set grew.
- **Account data** (`snowflake_tools.py`) — fixed queries, not a query-writing agent, for the reason above. Connections are reused across calls in a session rather than reconnected per query — a single "prep me for X" turn fires 5-6 queries, and re-authenticating on each one is real latency for someone prepping in a 10-minute gap between calls.

**Grounding is a hard rule, not a suggestion.** The system prompt explicitly instructs the model to never state an ungrounded fact and to say "I don't have that" rather than guess — directly from Sofia Alvarez's interview: *"I'd rather it told me less and was right than told me more and was wrong sometimes."* This is enforced by prompt instruction today; see *Quality* for how I'd verify it's actually holding.

## Quality — what "good" means here and how I'd measure it

Given the interview research, "good" is not primarily "the LLM writes fluently." It's:

1. **Zero fabricated account/pricing facts.** This is the trust bar the AEs themselves set, and it's the one thing that would kill adoption if violated even once. I'd build a small golden set (~15-20 prompts against known accounts) with hand-verified expected facts, and grade every response for any claim not traceable to a tool call — this is the single most important eval to run before any real AE sees this.
2. **Does it surface what a skim of Salesforce would miss?** Harder to grade automatically. I'd start with human review against the golden set — did it catch the planted anomaly (e.g. a stalled opportunity, a usage drop, an unaddressed ticket)? — and iterate the system prompt against misses.
3. **Speed.** An AE prepping in a 10-minute gap won't wait 20 seconds per turn. I'd track p50/p95 latency per tool-call round-trip as a real product metric, not an afterthought.
4. **Would she reach for it tomorrow?** Marcus Byrne's interview is the sharpest adoption signal in the research: skeptical AEs try once, and if it doesn't earn its keep on the first interaction, they don't come back. That argues for measuring real usage (return rate after first session) over any offline benchmark, once this is in front of real users.

## Path to production

- **Auth:** real SSO-based Snowflake access per AE (not a shared service credential), scoped to their own book of accounts.
- **Retrieval:** move to embeddings if/when the enablement corpus grows past what keyword ranking handles well.
- **Eval harness:** the golden-set grounding check above, run in CI against every prompt change — not just eyeballed once at launch.
- **Guardrails:** explicit handling for pricing/discount questions near deal-desk-escalation thresholds (the pricing cheat sheet itself flags these) so the agent nudges to deal desk rather than improvising an answer.
- **Proactive, not just reactive:** several AEs described wanting to be told something before they thought to ask (Lena: *"tell me what I'd miss"*). A production version could push a short daily brief for the day's calls rather than waiting to be opened.
- **Personalization by AE seniority/tenure:** Sofia (18 months) wants the playbook explained; Marcus (7 years) wants zero hand-holding and pure information retrieval. One system prompt for both is a v1 simplification, not a permanent design.

## Note on this submission's status

Snowflake access is MFA-blocked as of writing (flagged to Eva Wong, no response yet) — the account-data tools are written and unit-tested but not yet verified against live rows. Google Drive and the agent's LLM calls are live and demoed end-to-end in `scenarios.py`. See `README.md` for full status and how to re-run once access is restored.
