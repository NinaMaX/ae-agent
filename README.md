# Personio Call-Prep Agent

An assistant that helps AEs surface what they might miss before a call — not a generic chatbot over Salesforce. Built for the Internal AI PM case study.

Ask it about an account and it pulls live CRM/product/support data from Snowflake, cross-references Personio's sales enablement docs (playbook, ICP, battlecards, objection handling, pricing, case studies), and holds a real multi-turn conversation — follow-ups keep context, it doesn't just answer once and forget.

## What this helps an AE do

- **"Prep me for my renewal call with [account]"** — pulls account summary, recent activity, opportunities, usage trend, and support tickets, then leads with what's notable (a usage drop, a stalled opportunity, an unresolved ticket) rather than reading every field back.
- **"What does the playbook say about handling a stalled renewal?"** — searches the actual enablement docs instead of you remembering which of ten battlecards has the answer.
- **"Are they evaluating any competitors?"** — proactively surfaces the relevant battlecard the moment a competitor shows up in the account's activity, without you having to ask for it by name.
- **"Prep me for my call with [account that doesn't exist]"** — says so plainly instead of inventing a plausible-sounding answer. This matters more than it sounds: one AE interview put it as *"if a tool tells me a wrong fact about a customer, I lose three months of trust in it."*

## Status

Everything is live: Google Drive, Anthropic, and Snowflake, all verified end-to-end against real data — see `scenarios.py` for full transcripts.

Getting Snowflake working took two fixes worth noting, since they'll matter for anyone else hitting this sandbox:
1. **MFA blocks plain password auth entirely** for programmatic access (`MFA authentication is required, but none of your current MFA methods are supported for programmatic authentication`). Fix: use a Snowflake Personal Access Token instead (`SNOWFLAKE_PAT` in `.env`) — PATs are exempt from the interactive MFA requirement. `connection.py` tries PAT auth first and falls back to password.
2. **PATs themselves require a network policy** to be attached to the account or user before Snowflake will accept them at all (`Fail : Network policy is required`). The provisioned role (`APPLICANT_FR`) doesn't have `CREATE NETWORK POLICY`, confirmed by testing directly rather than guessing. The actual fix needed no admin: self-issuing a *new* PAT with a temporary bypass works with a normal user's own privileges —
   ```sql
   ALTER USER "<your_username>" ADD PROGRAMMATIC ACCESS TOKEN <name>
     DAYS_TO_EXPIRY = 7
     MINS_TO_BYPASS_NETWORK_POLICY_REQUIREMENT = 10080;
   ```

## Setup

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
```

Populate `.env` (see `.env.example` for the full list and PAT setup notes):
- Snowflake credentials from the case study's shared 1Password link, plus a `SNOWFLAKE_PAT` (see *Status* above for why).
- `ANTHROPIC_API_KEY` from console.anthropic.com.
- `GOOGLE_DRIVE_API_KEY`: Google Cloud Console → enable the Drive API → Credentials → API key. Works without OAuth because the enablement folder is shared as "anyone with the link can view."
- `GOOGLE_DRIVE_FOLDER_ID`: from the shared Drive folder's URL.

Pull the enablement docs (required, not optional — `data/enablement/` isn't committed, since it's fetched content, not source; re-run if the Drive folder changes):

```bash
python drive_docs.py
```

## Run it

```bash
streamlit run app.py
```

The sidebar has a few real example prompts against live accounts (Tide Logistics AG, Fjord Logistics AS, Brightline Retail GmbH) — a first-time user shouldn't have to guess what this can do, which matters given the interview research: skeptical AEs try once and don't come back if it doesn't earn its keep immediately.

Or from the terminal, no Streamlit required:

```bash
python agent.py
```

## Architecture

No agent framework — Claude's native tool use in a plain loop ([agent.py](agent.py)). At ~75 accounts and 7 enablement docs, LangChain/LlamaIndex-style orchestration would add indirection without buying anything; a `while` loop around `client.messages.create()` is the whole agent runtime and is easy to read end-to-end in the technical deep-dive.

**Two tool families:**
- `search_playbook` ([playbook_search.py](playbook_search.py)) — keyword search over the 7 enablement docs, split into `##`-level sections. No vector DB: with ~800 lines of source material total, embeddings would be solving a problem that doesn't exist yet. Would switch to embeddings if the corpus grew past what keyword scoring can rank well.
- Account-data tools ([snowflake_tools.py](snowflake_tools.py)) — `find_account`, `get_account_summary`, `get_contacts`, `get_opportunities`, `get_recent_activities`, `get_product_usage`, `get_support_tickets`. Each is a fixed, parameterized query written against the confirmed schema, not free-form SQL the model writes itself — deliberate, given Snowflake access issues meant the schema had to be confirmed manually (via the Snowflake UI) rather than trusted from the case brief, which described a different database/schema layout than what's actually provisioned.

**Data flow:** Drive docs are synced to local markdown once ([drive_docs.py](drive_docs.py)) rather than queried live on every turn — they're static reference content, so there's no reason to pay a network round-trip per question. Snowflake is queried live per tool call, with the connection reused across calls in a session (`connection.py`) rather than reconnecting every query — a "prep me for X" turn fires 5-6 queries back to back, and re-authenticating on each one is real added latency for someone prepping under time pressure.

**System prompt** ([agent.py](agent.py)) is shaped by `research/13_ae_interview_notes.md` (AE interviews from prior PM discovery), not just the case brief. The strongest unmet need across interviewees wasn't "restate the account facts" — it was "tell me what changed" and "tell me what I'd miss" (Lena, Marcus, Thomas), with trust hinging on never stating an ungrounded fact (Sofia: *"I'd rather it told me less and was right than told me more and was wrong"*). The prompt instructs the agent to lead with what's notable rather than listing fields back, proactively surface competitive/case-study context, and never fabricate account or pricing details.

## Testing

```bash
python -m unittest tests.test_agent
```

The tool-schema check needs nothing. The playbook-search checks need `data/enablement/` populated first (`python drive_docs.py`, requires `GOOGLE_DRIVE_API_KEY`) — not committed, since it's fetched content, not source (see *Setup*). A real CI pipeline would need that key as a secret, or a small committed fixture separate from the live cache; skipped that for a prototype this size.

End-to-end behavior with live data is verified via realistic multi-turn scenarios:

```bash
python scenarios.py
```

This mirrors the persona's two calls (a renewal with an at-risk customer, a discovery call with a hot prospect) plus a drill-down/follow-up test and an unknown-account honesty test. Accounts are picked live from real data (e.g. a customer with a renewal opportunity stalled longest in stage) rather than hardcoded, since there's no explicit "at risk" flag in the schema — that's a judgment call the agent has to make from signals, which is exactly the synthesis the interview research asked for.

## Scope

What's built: multi-turn chat, live enablement-doc search, live account-data tools, a system prompt grounded in real AE research.

What's deliberately cut, given the ~3-5 hour box: no persistent memory across sessions, no write-back to Salesforce, no enterprise-AE flow (the interview notes are explicit that enterprise AEs want a different tool — see Ines Dubois's notes), no bespoke anomaly-detection model for "what changed" (the system prompt asks Claude to reason over the raw tool output instead, which is far cheaper to build and iterate on than a dedicated diffing/scoring pipeline, at the cost of being less deterministic).

See the submitted one-pager (Google Slides, sent separately from this repo) for the full scoping rationale, quality bar, and path to production.
