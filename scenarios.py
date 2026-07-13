"""
Runs realistic multi-turn AE conversations end-to-end and prints full
transcripts for manual quality review. Needs live Snowflake + Anthropic
access, so it's a manual script, not part of the CI-safe test suite
(tests/test_agent.py).

Mirrors the case persona: a renewal/expansion call with a churn-risk
customer, back-to-back with a discovery call with a hot prospect. Account
names aren't hardcoded (we don't know the real 75 accounts yet - Snowflake
access is still MFA-blocked as of writing) - this script discovers a
plausible account for each scenario live, falling back to "any account" if
the targeted filter comes back empty rather than failing outright.

Run once Snowflake access is restored:
    python scenarios.py
"""

import os

import anthropic
from dotenv import load_dotenv

import agent
from connection import run_query

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)


def _pick_account(where_ilike: str) -> str:
    """Finds a company name matching a loose filter; falls back to any
    account if the filter matches nothing (enum values are unconfirmed)."""
    rows = run_query(
        f"SELECT COMPANY_NAME FROM CRM.ACCOUNTS WHERE {where_ilike} LIMIT 1"
    )
    if not rows:
        rows = run_query("SELECT COMPANY_NAME FROM CRM.ACCOUNTS LIMIT 1")
    return rows[0]["COMPANY_NAME"]


SCENARIOS = [
    {
        "label": "Renewal / expansion call with a churn-risk customer",
        "account_filter": "STATUS ILIKE '%risk%' OR STATUS ILIKE '%churn%'",
        "turns": [
            "Prep me for my renewal call with {account}",
            "What's our usage trend looking like there?",
            "Anything in support tickets I should know about before the call?",
            "What does the playbook say about handling a renewal that's at risk?",
        ],
    },
    {
        "label": "Discovery call with a hot prospect",
        "account_filter": "STATUS ILIKE '%prospect%' OR STATUS ILIKE '%active%'",
        "turns": [
            "I've got a discovery call with {account} coming up, what do I need to know?",
            "Who are the stakeholders we've engaged so far?",
            "Are they evaluating any competitors?",
        ],
    },
    {
        "label": "Drill-down / follow-up behavior (single account, multiple angles)",
        "account_filter": "1=1",  # any account
        "turns": [
            "Tell me about {account}",
            "What's their ARR and how long have they been a customer?",
            "Ok, and if pricing comes up, what should I lead with?",
        ],
    },
    {
        "label": "Unknown account (tests honest failure, not hallucination)",
        "account_filter": None,
        "turns": [
            "Prep me for my call with Definitely Not A Real Company Inc",
        ],
    },
]


def run_scenario(client, scenario):
    print(f"\n{'=' * 70}\n{scenario['label']}\n{'=' * 70}")
    account = None
    if scenario["account_filter"]:
        account = _pick_account(scenario["account_filter"])
        print(f"(using account: {account})\n")

    convo = []
    for turn in scenario["turns"]:
        prompt = turn.format(account=account) if account else turn
        print(f"AE> {prompt}")
        convo.append({"role": "user", "content": prompt})
        convo = agent.run_turn(client, convo)
        print(f"\nAgent: {agent.latest_reply_text(convo)}\n")


if __name__ == "__main__":
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    for scenario in SCENARIOS:
        run_scenario(client, scenario)
