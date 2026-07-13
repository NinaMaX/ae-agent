"""
Automated regression check, not just a manual transcript read (that's what
scenarios.py is for). Each case asserts something mechanically checkable:
the right tool got called, a follow-up doesn't needlessly re-fetch data
already in context, and an unknown account gets an honest "not found"
rather than a fabricated answer.

This is deliberately not a grader of prose quality or factual correctness -
that needs a human (or a hand-verified golden set far larger than this) per
ONE_PAGER.md's Quality section. What this catches: did the agent reach for
the right tool at all, and did it hold context instead of re-querying.
That's the cheapest, highest-signal regression check available before a
heavier eval harness is worth building.

Run:
    python eval_suite.py
"""

import os
import sys

import anthropic
from dotenv import load_dotenv

import agent
from scenarios import AT_RISK_RENEWAL_QUERY, HOT_PROSPECT_QUERY, _pick_account

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

NOT_FOUND_PHRASES = ["couldn't find", "could not find", "don't have", "no account", "not in the system", "no matching"]


def check_tool_called(turn: dict, expected_any_of: list[str]) -> tuple[bool, str]:
    called = {c["name"] for c in turn["tool_calls"]}
    if called & set(expected_any_of):
        return True, f"called {called & set(expected_any_of)}"
    return False, f"expected one of {expected_any_of}, got {called or 'no tool calls'}"


def check_no_tool_called(turn: dict, forbidden: list[str]) -> tuple[bool, str]:
    called = {c["name"] for c in turn["tool_calls"]}
    overlap = called & set(forbidden)
    if overlap:
        return False, f"re-called {overlap} instead of using context"
    return True, "held context, no redundant lookup"


def check_reply_contains_any(turn: dict, phrases: list[str]) -> tuple[bool, str]:
    reply_lower = turn["reply"].lower()
    if any(p in reply_lower for p in phrases):
        return True, "honest-failure language present"
    return False, f"expected one of {phrases} in reply, got: {turn['reply'][:150]!r}"


def check_surfaces_competitor(turn: dict, competitor_names: list[str]) -> tuple[bool, str]:
    """Accepts either a fresh search_playbook call OR the reply naming a
    competitor it already had grounded from CRM data - both are legitimate.
    Found via this exact eval: the model sometimes names a competitor from
    activity data already in context and *offers* the battlecard rather than
    calling search_playbook immediately, correctly balancing the system
    prompt's "proactively surface competitive context" instruction against
    its "keep the first answer short" instruction. That's good judgment, not
    a miss - so the check needs to accept either path, not just the tool call."""
    called = {c["name"] for c in turn["tool_calls"]}
    if "search_playbook" in called:
        return True, "called search_playbook"
    reply_lower = turn["reply"].lower()
    if any(name.lower() in reply_lower for name in competitor_names):
        return True, "named competitor from already-grounded context, offered next step"
    return False, f"expected search_playbook or a named competitor ({competitor_names}) in reply"


def build_cases():
    at_risk_account = _pick_account(AT_RISK_RENEWAL_QUERY)
    hot_prospect_account = _pick_account(HOT_PROSPECT_QUERY)

    return [
        {
            "label": "Renewal prep resolves the account and pulls real data",
            "turns": [
                {
                    "prompt": f"Prep me for my renewal call with {at_risk_account}",
                    "checks": [lambda t: check_tool_called(t, ["find_account"])],
                },
                {
                    "prompt": "What's their ARR?",
                    "checks": [lambda t: check_no_tool_called(t, ["find_account", "get_account_summary"])],
                },
            ],
        },
        {
            "label": "Discovery prep surfaces competitive context",
            "turns": [
                {
                    "prompt": f"I've got a discovery call with {hot_prospect_account}, what do I need to know?",
                    "checks": [lambda t: check_tool_called(t, ["find_account"])],
                },
                {
                    "prompt": "Are they evaluating any competitors?",
                    "checks": [lambda t: check_surfaces_competitor(t, ["HiBob", "Workday"])],
                },
            ],
        },
        {
            "label": "Case-study lookalike matching (Sofia's specific ask: 'who else looks like this customer')",
            "turns": [
                {
                    "prompt": f"Tell me about {at_risk_account}",
                    "checks": [lambda t: check_tool_called(t, ["find_account"])],
                },
                {
                    "prompt": "Do we have a case study from a similar customer I could reference on the call?",
                    "checks": [lambda t: check_tool_called(t, ["search_playbook"])],
                },
            ],
        },
        {
            "label": "Unknown account fails honestly instead of hallucinating",
            "turns": [
                {
                    "prompt": "Prep me for my call with Definitely Not A Real Company Inc",
                    "checks": [
                        lambda t: check_tool_called(t, ["find_account"]),
                        lambda t: check_reply_contains_any(t, NOT_FOUND_PHRASES),
                    ],
                },
            ],
        },
    ]


def run_suite():
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    results = []

    for case in build_cases():
        print(f"\n{'=' * 70}\n{case['label']}\n{'=' * 70}")
        convo = []
        for turn_spec in case["turns"]:
            print(f"AE> {turn_spec['prompt']}")
            convo.append({"role": "user", "content": turn_spec["prompt"]})
            convo = agent.run_turn(client, convo)
            reply = agent.latest_reply_text(convo)
            print(f"Agent: {reply[:200]}{'...' if len(reply) > 200 else ''}")

            this_turn = agent.group_into_turns(convo)[-1]
            for check in turn_spec["checks"]:
                passed, detail = check(this_turn)
                status = "PASS" if passed else "FAIL"
                print(f"  [{status}] {detail}")
                results.append((case["label"], passed, detail))

    print(f"\n{'=' * 70}\nSummary\n{'=' * 70}")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{total} checks passed")
    for label, ok, detail in results:
        if not ok:
            print(f"  FAILED: {label} - {detail}")

    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_suite() else 1)
