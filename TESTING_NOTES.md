# Testing notes

What actually testing the agent (not just reading the code) surfaced, and how each was fixed. Kept here as a deep-dive reference rather than folded into `ONE_PAGER.md` — this is the log, not the pitch.

## Redundant tool re-fetch on follow-ups

**Found:** asking a follow-up ("what's their usage trend?") after already pulling that account's data re-called `get_product_usage` with identical arguments instead of answering from context already in the conversation.
**Fix:** added an explicit system-prompt rule not to re-call a data tool for an account already pulled this conversation.
**Verified:** same scenario, same two turns — tool calls in the follow-up went from 1 to 0.

## Display bug: one answer looked like two

**Found:** on the run that had the redundant re-fetch above, the UI showed what looked like two different, overlapping "complete answers" glued together with no separator.
**Root cause:** `group_into_turns()` accumulated text across *every* assistant message in a turn (`reply += text`). When Claude attaches explanatory text to a non-final tool-use message, that text got concatenated with the real final answer.
**Fix:** only the last assistant message's text counts as the reply now (matches `latest_reply_text()`, which already worked this way).

## Answers ran 3-5x longer than AEs asked for

**Found:** every live transcript ran 8-15+ lines with bolded sub-sections. Thomas Weber's interview: *"Two lines... anything longer I'm going to skim."* Marcus Byrne: wants *"a one-line answer."*
**Fix:** rewrote the length rule with those quotes as the literal anchor (2-4 lines, hard target) and changed "lead with what's notable" (which let the model list several signals) to "pick the ONE or at most TWO most important things."
**Verified:** same "prep me for X" prompt, same account — 1,367 chars → 419 chars. Re-checked pricing-contextuality (Thomas's other ask) didn't get sacrificed for brevity — it didn't; the answer stayed deal-specific.

## The model couldn't fulfill its own "want the full history?" offer

**Found:** the system prompt tells the model to offer deeper detail rather than dumping it up front. But `get_recent_activities`/`get_product_usage`'s optional `limit`/`months` overrides were never exposed in the tool schema Claude sees — only `account_id` was. Saying yes to the offer would have just re-run the same query with the same default.
**Fix:** exposed `limit`/`months` as optional tool parameters.
**Verified:** asking for "the full activity history" now calls the tool with `limit=100` and surfaces something the default window couldn't (a 13-month activity gap).

## `find_account` silently truncated results

**Found:** capped at `LIMIT 5` with no signal when more matches existed. Checked whether this was live risk, not theoretical: searching "Tide" in the real dataset returns *exactly* 5 accounts (Tide Logistics, Education, Solutions, Professional, Hospitality) - right at the old boundary. A broader search ("a") matches 65 of 75 accounts.
**Fix:** raised the cap to 10; if hit, a follow-up `COUNT(*)` (only runs in that case) gets the true total and appends a note so the agent can tell the AE to narrow their search instead of presenting a partial list as complete.

## Retrieval failure on Sofia Alvarez's exact quoted scenario

**Found:** tested her verbatim quote - *"what does the discovery playbook say about evaluating a deal stuck in qualification"* - since it's the flagship evidence for `search_playbook` existing at all. It failed: the agent said the playbook "doesn't explicitly address" it and answered from the wrong stage (Discovery instead of Qualification).
**Root cause:** plain term-frequency scoring let "discovery" (mentioned constantly throughout the doc) outrank "qualification" (rare, specific, but sitting in a section too short to rack up raw hits).
**Fix:** TF-IDF-style term weighting - down-weight terms common across chunks, up-weight rare ones. Still keyword retrieval, not embeddings.
**Verified:** Qualification section's score went from 3 (outside the top 5 entirely) to 12.62 (included); the agent's answer now correctly grounds in the real section content.

## Demo/eval account selection wasn't actually mid-market-only

**Found:** the whole scope narrative rests on "mid-market only, enterprise is a different problem" (Ines's interview) - but the account-picking queries in `scenarios.py` never filtered by `SEGMENT`. The renewal demo account was MM by chance; the discovery demo account (Fjord Logistics AS) was actually `SEGMENT='ENT'`, silently contradicting the story anyone using it as a demo example would be telling.
**Fix:** added `SEGMENT = 'MM'` to both account-picking queries. New hot-prospect example: Verdant Financial Services SAS.
**Note:** the agent's actual *behavior* on the ENT account was fine - it correctly said "Enterprise segment" and reasoned about procurement-led RFP dynamics rather than forcing an MM-shaped narrative on it. This was a demo-consistency risk, not a correctness bug.

## Feedback log was dropping the actual answer

**Found:** `log_feedback()` logged `len(reply)` (a character count) instead of the reply text. A thumbs-down told you which question got a bad answer, not what the bad answer said - not reviewable later.
**Fix:** log the full reply.

## No way back to a previous conversation

**Found:** added a "New chat" button, then the user immediately caught that it was a half-finished feature - no way to return to what you cleared.
**Fix:** real conversation history (`st.session_state.conversations`, a list with an active index), sidebar list of past conversations, titles derived from each one's first message.

---

Also cleaned up along the way, lower stakes: two stale comments claiming Snowflake MFA was still blocking access (it wasn't, hadn't been for a while), five redundant `load_dotenv()` calls, a dead `.gitignore` entry, and caught Streamlit's own auto-generated `.agents`/`.claude` symlinks about to get committed via a broad `git add -A` (reviewed the staged diff before committing, not after - would have dangled for anyone else's virtualenv).
