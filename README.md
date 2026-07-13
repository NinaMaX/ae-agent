# Personio Call-Prep Agent

A conversational assistant for Account Executives prepping for account calls. Built for the Internal AI PM case study.

Ask it about an account and it pulls live CRM/product/support data from Snowflake, cross-references Personio's sales enablement docs (playbook, ICP, battlecards, objection handling, pricing, case studies), and holds a real multi-turn conversation — follow-ups keep context, it doesn't just answer once and forget.

## Status

- **Google Drive (unstructured data):** live and working.
- **Anthropic (the agent itself):** live and working.
- **Snowflake (structured CRM/product/support data):** blocked. The provisioned `CASE_STUDY_RO`-equivalent account enforces MFA on password auth, which fails for programmatic/API access (`snowflake.connector.errors.DatabaseError: ... MFA authentication is required, but none of your current MFA methods are supported for programmatic authentication`). Flagged to Eva Wong; no response yet as of this submission. Every account-data code path is written and tool-tested with mocked failures, but not yet verified against live rows — see [snowflake_tools.py](snowflake_tools.py) and the note in that file.

When Snowflake access is restored: run `python discover_schema.py` to confirm the schema hasn't drifted from what's documented below, then run the agent — no code changes should be needed.

## Setup

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
```

Populate `.env`:
- Snowflake credentials from the case study's shared 1Password link.
- `ANTHROPIC_API_KEY` from console.anthropic.com.
- `GOOGLE_DRIVE_API_KEY`: Google Cloud Console → enable the Drive API → Credentials → API key. Works without OAuth because the enablement folder is shared as "anyone with the link can view."
- `GOOGLE_DRIVE_FOLDER_ID`: from the shared Drive folder's URL.

Pull the enablement docs (one-time, re-run if the Drive folder changes):

```bash
python drive_docs.py
```

## Run it

```bash
streamlit run app.py
```

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

Runs without live credentials (playbook search + tool-schema checks) so it works in CI. End-to-end behavior with live data is verified manually — see the demo in the live session.

## Scope

What's built: multi-turn chat, live enablement-doc search, live account-data tools (pending Snowflake access), a system prompt grounded in real AE research.

What's deliberately cut, given the ~3-5 hour box: no persistent memory across sessions, no write-back to Salesforce, no enterprise-AE flow (the interview notes are explicit that enterprise AEs want a different tool — see Ines Dubois's notes), no bespoke anomaly-detection model for "what changed" (the system prompt asks Claude to reason over the raw tool output instead, which is far cheaper to build and iterate on than a dedicated diffing/scoring pipeline, at the cost of being less deterministic).

See the one-pager for the full scoping rationale, quality bar, and path to production.
