"""
Core agent loop: Claude with native tool use, no framework.

The agent has two tool families:
  - search_playbook: keyword search over the sales enablement docs (playbook,
    ICP, battlecards, objection handling, pricing, case studies).
  - Snowflake account-data tools (snowflake_tools.py): curated, parameterized
    queries against the confirmed live schema (see discover_schema.py). The
    model never writes its own SQL against a schema it's guessing at.

Conversation state is kept as a raw list of Anthropic message dicts (not a
simplified role/text pairing) so tool_use / tool_result blocks survive across
turns and the model keeps proper context on follow-up questions.
"""

import logging
import os
import time

import anthropic

import playbook_search
import snowflake_tools  # loads .env as a side effect (imports connection.py, which does)

MODEL = "claude-sonnet-4-5"

# Lightweight observability foundation: every tool call, timed and logged.
# Not a real logging pipeline - just enough that a failure or a slow tool
# call is visible in the terminal/Streamlit logs rather than silently eaten,
# which matters once this is more than a one-person demo.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ae_agent")

# System prompt encodes findings from AE interviews (documents/13_ae_interview_notes.md),
# not just the case brief. The strongest unmet need across interviewees wasn't
# "restate account facts" - it was "tell me what changed" / "tell me what I'd
# miss" (Lena, Marcus, Thomas), with trust hinging on never stating an
# ungrounded fact (Sofia: "I'd rather it told me less and was right").
SYSTEM_PROMPT = """You are a call-prep assistant for Personio Account Executives.

The user is a mid-market AE in EMEA, ~18 months tenure, owns 30-40 accounts. \
They are preparing for back-to-back account calls under time pressure.

You have two kinds of tools:
- Account data tools (find_account, get_account_summary, get_contacts, \
get_opportunities, get_recent_activities, get_product_usage, \
get_support_tickets): live CRM, product usage, and support data for a \
specific account. Account names are fuzzy - always resolve with \
find_account first if you don't already have an ACCOUNT_ID, and ask the \
user to disambiguate if find_account returns more than one plausible match.
- search_playbook: sales enablement content (playbook, ICP, competitive \
battlecards, objection handling, pricing, case studies).

How to prep for a call (when asked something like "prep me for X" or "tell \
me about X"):
1. Resolve the account, then pull account summary, recent activity, open \
opportunities, product usage, and support tickets. Gather broadly - report \
narrowly (see the length rule below). Casting a wide net here is how you \
catch what she'd otherwise miss; the discipline is in what you say next, \
not in what you look at.
2. Don't list findings. Pick the ONE or at most TWO most important things - \
not every notable signal you noticed - and lead with those: what changed \
recently, what's easy to miss (a usage drop, an unresolved ticket the \
activity log doesn't mention, an opportunity stalled in stage, a missing \
stakeholder type in the contacts), or anything that contradicts the deal's \
apparent momentum. AEs already know the obvious stuff (stage, amount) - the \
value is surfacing the one thing they wouldn't have caught skimming \
Salesforce themselves, not a comprehensive report of everything you checked.
3. If a competitor is mentioned anywhere in activities, opportunity names, \
or notes, or the deal shape matches a known battlecard, proactively surface \
the relevant battlecard angle via search_playbook without waiting to be asked.
4. If it's a renewal/expansion or the account looks like a good fit for a \
customer story, proactively check search_playbook for a matching case study.
5. Keep every answer to 2-4 lines, no exceptions. This is not a soft \
guideline - two AE interviews set the actual bar: Thomas Weber wants "two \
lines: here's what's changed, here's what's worth bringing up on the call. \
Anything longer I'm going to skim." Marcus Byrne wants literally "a one-line \
answer" to what changed on an account. State the single most important \
thing plainly, then stop - don't restate it three ways or list supporting \
detail underneath it. Offer to go deeper ("want the full activity history?") \
rather than including it up front. If your answer is running past 4 lines, \
you're including too much - cut content, don't just tighten the wording.

Other rules:
- Don't re-call a data tool for an account you've already pulled data for \
earlier in this same conversation - reason from what's already in context. \
Only call it again if the AE asks about a different account, or explicitly \
asks you to recheck or refresh something.
- Ground every factual claim about an account or about Personio's \
positioning in a tool call. Never invent account details, pricing, or \
battlecard content. If a tool returns nothing relevant or an account can't \
be found, say so plainly rather than guessing - a wrong fact costs more \
trust than an honest "I don't have that."
- Pricing is contextual: don't paste the pricing cheat sheet verbatim. \
Answer the specific question asked, using the cheat sheet as grounding.
- This AE is mid-market, not enterprise - don't assume enterprise deal \
shapes (many stakeholders, 6-month cycles) unless the account data says so.
"""

ACCOUNT_ID_PARAM = {
    "account_id": {
        "type": "string",
        "description": "The ACCOUNT_ID from a prior find_account or get_account_summary call.",
    },
}

TOOLS = [
    {
        "name": "search_playbook",
        "description": (
            "Search Personio's sales enablement docs: sales playbook, ICP, "
            "competitive battlecards (Workday, HiBob), objection handling "
            "guide, pricing cheat sheet, and customer case studies. Returns "
            "the most relevant sections for the query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, e.g. 'Workday competitive positioning' or 'price objection handling'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_account",
        "description": "Fuzzy-search accounts by company name. Use this first whenever you don't already have an ACCOUNT_ID - the AE will type approximate names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name_query": {"type": "string", "description": "Full or partial company name."},
            },
            "required": ["name_query"],
        },
    },
    {
        "name": "get_account_summary",
        "description": "Core account record: ARR, employee count, industry, region, segment, status, owner, customer-since date.",
        "input_schema": {"type": "object", "properties": ACCOUNT_ID_PARAM, "required": ["account_id"]},
    },
    {
        "name": "get_contacts",
        "description": "Known stakeholders at the account: name, role, persona type (e.g. economic buyer, champion, IT), and last interaction date. Useful for spotting missing stakeholder coverage.",
        "input_schema": {"type": "object", "properties": ACCOUNT_ID_PARAM, "required": ["account_id"]},
    },
    {
        "name": "get_opportunities",
        "description": "Opportunities for the account: stage, amount, days in stage, close date, and win/loss reason if closed.",
        "input_schema": {"type": "object", "properties": ACCOUNT_ID_PARAM, "required": ["account_id"]},
    },
    {
        "name": "get_recent_activities",
        "description": "Recent logged activities (calls, emails, meetings) for the account, most recent first. Defaults to the last 15 - pass a higher limit if the AE asks for the fuller history you offered.",
        "input_schema": {
            "type": "object",
            "properties": {
                **ACCOUNT_ID_PARAM,
                "limit": {"type": "integer", "description": "How many activities to return. Omit for the default of 15."},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "get_product_usage",
        "description": "Monthly product usage: MAU, logins, payroll runs, and which modules (performance, recruiting) are active. Use to spot usage trends and adoption gaps. Defaults to the last 6 months - pass a higher value for a longer trend.",
        "input_schema": {
            "type": "object",
            "properties": {
                **ACCOUNT_ID_PARAM,
                "months": {"type": "integer", "description": "How many months of usage history to return. Omit for the default of 6."},
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "get_support_tickets",
        "description": "Support tickets for the account with priority, status, and dates. Use to spot unresolved issues that a call should address.",
        "input_schema": {"type": "object", "properties": ACCOUNT_ID_PARAM, "required": ["account_id"]},
    },
]

_SNOWFLAKE_TOOLS = {
    "find_account": lambda i: snowflake_tools.find_account(i["name_query"]),
    "get_account_summary": lambda i: snowflake_tools.get_account_summary(i["account_id"]),
    "get_contacts": lambda i: snowflake_tools.get_contacts(i["account_id"]),
    "get_opportunities": lambda i: snowflake_tools.get_opportunities(i["account_id"]),
    "get_recent_activities": lambda i: snowflake_tools.get_recent_activities(**i),
    "get_product_usage": lambda i: snowflake_tools.get_product_usage(**i),
    "get_support_tickets": lambda i: snowflake_tools.get_support_tickets(i["account_id"]),
}


def _dispatch_tool(name: str, tool_input: dict) -> str:
    if name == "search_playbook":
        results = playbook_search.search(tool_input["query"])
        if not results:
            return "No matching enablement content found for that query."
        return "\n\n".join(
            f"### {r['section']} (from {r['source']})\n{r['text']}" for r in results
        )
    if name in _SNOWFLAKE_TOOLS:
        try:
            rows = _SNOWFLAKE_TOOLS[name](tool_input)
        except Exception as exc:
            return f"Query failed: {exc.__class__.__name__}: {exc}"
        if not rows:
            return "No matching rows found."
        return str(rows)
    return f"Unknown tool: {name}"


def _run_tool(name: str, tool_input: dict) -> str:
    start = time.monotonic()
    result = _dispatch_tool(name, tool_input)
    elapsed_ms = (time.monotonic() - start) * 1000
    failed = result.startswith("Query failed:") or result.startswith("Unknown tool:")
    logger.info(
        "tool=%s input=%s elapsed_ms=%.0f failed=%s result_chars=%d",
        name, tool_input, elapsed_ms, failed, len(result),
    )
    return result


def run_turn(client: anthropic.Anthropic, messages: list[dict]) -> list[dict]:
    """Runs one full agent turn (including any tool-use round-trips) and
    returns the updated message list with the assistant's final reply appended."""
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return messages

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_text = _run_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )
        messages.append({"role": "user", "content": tool_results})


def latest_reply_text(messages: list[dict]) -> str:
    """Extracts the plain-text portion of the most recent assistant message."""
    last = messages[-1]
    if last["role"] != "assistant":
        return ""
    return "".join(b.text for b in last["content"] if getattr(b, "type", None) == "text")


def log_feedback(question: str, reply: str, rating: str) -> None:
    """Logs an AE's thumbs-up/down on a reply. The cheapest real signal for
    "was this actually useful," and per Marcus Byrne's interview, the input
    that should drive the next iteration - not assumptions about what AEs want.

    This is a capture mechanism, not a closed loop: it writes to the log
    (stdout today - a real deployment would want a durable sink, a file or a
    table), and nothing currently reads it back to change agent behavior
    automatically. Turning "AE hit thumbs-down on X" into a prompt or tool
    change is still a human step. Logging the full reply, not just its
    length, is what makes that human step possible at all - a rating with no
    record of what was actually said isn't reviewable later."""
    logger.info("feedback=%s question=%r reply=%r", rating, question, reply)


def group_into_turns(messages: list[dict]) -> list[dict]:
    """Groups the raw message list into one entry per user turn, each with the
    tool calls that backed it and the final reply text. Used by the UI to
    show sources, and by eval scripts to assert on tool usage - e.g.
    confirming a follow-up question doesn't re-fetch data already in context.

    Only the LAST assistant message's text counts as the reply - a turn can
    include several assistant messages (one per tool-use round trip), and
    Claude sometimes attaches explanatory text to an earlier, non-final one
    alongside its tool_use block. That text is scaffolding for the tool call,
    not a second answer - concatenating it with the real final answer (an
    earlier version of this function did) reads as two competing, overlapping
    replies glued together with no separator. Matches latest_reply_text(),
    which already only looks at the final message."""
    turns = []
    current = None
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg["content"], str):
            current = {"user": msg["content"], "tool_calls": [], "reply": ""}
            turns.append(current)
        elif msg["role"] == "assistant" and current is not None:
            current["reply"] = ""  # reset each assistant message - only the last one's text survives
            for block in msg["content"]:
                block_type = getattr(block, "type", None)
                if block_type == "tool_use":
                    current["tool_calls"].append({"name": block.name, "input": block.input})
                elif block_type == "text":
                    current["reply"] += block.text
    return turns


if __name__ == "__main__":
    # Quick CLI smoke test, no Streamlit required.
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    convo = []
    print("Call-prep agent CLI (Ctrl+C to quit)")
    while True:
        user_input = input("\nAE> ").strip()
        if not user_input:
            continue
        convo.append({"role": "user", "content": user_input})
        convo = run_turn(client, convo)
        print(f"\nAgent: {latest_reply_text(convo)}")
