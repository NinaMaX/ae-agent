"""
Runs realistic multi-turn AE conversations end-to-end and prints full
transcripts for manual quality review. Needs live Snowflake + Anthropic
access, so it's a manual script, not part of the CI-safe test suite
(tests/test_agent.py).

Mirrors the case persona: a renewal/expansion call with an at-risk
customer, back-to-back with a discovery call with a hot prospect. Account
names aren't hardcoded - real STATUS/STAGE enum values were confirmed live
(STATUS has no "at risk" value - it's customer/prospect/churned; "at risk" is
a judgment call the agent has to make from signals, not a flag to filter on,
which is exactly the kind of synthesis the interview research asked for).
Each scenario picks a live account matching real signals (e.g. a customer
with a renewal opportunity stalled in stage), not an already-churned account.

Run:
    python scenarios.py
"""

import os

import anthropic

import agent
from connection import run_query  # loads .env as a side effect


def _pick_account(query: str) -> str:
    """Runs a query returning a COMPANY_NAME column; falls back to any
    account if it comes back empty."""
    rows = run_query(query)
    if not rows:
        rows = run_query("SELECT COMPANY_NAME FROM CRM.ACCOUNTS LIMIT 1")
    return rows[0]["COMPANY_NAME"]


AT_RISK_RENEWAL_QUERY = """
    SELECT a.COMPANY_NAME
    FROM CRM.ACCOUNTS a
    JOIN CRM.OPPORTUNITIES o ON o.ACCOUNT_ID = a.ACCOUNT_ID
    WHERE a.STATUS = 'customer' AND o.TYPE = 'Renewal'
      AND o.STAGE NOT IN ('Closed Won', 'Closed Lost')
    ORDER BY o.DAYS_IN_STAGE DESC
    LIMIT 1
"""

HOT_PROSPECT_QUERY = """
    SELECT a.COMPANY_NAME
    FROM CRM.ACCOUNTS a
    JOIN CRM.OPPORTUNITIES o ON o.ACCOUNT_ID = a.ACCOUNT_ID
    WHERE a.STATUS = 'prospect' AND o.STAGE IN ('Demo', 'Proposal')
    ORDER BY o.DAYS_IN_STAGE ASC
    LIMIT 1
"""

SCENARIOS = [
    {
        "label": "Renewal / expansion call with an at-risk customer",
        "account_query": AT_RISK_RENEWAL_QUERY,
        "turns": [
            "Prep me for my renewal call with {account}",
            "What's our usage trend looking like there?",
            "Anything in support tickets I should know about before the call?",
            "What does the playbook say about handling a renewal that's at risk?",
        ],
    },
    {
        "label": "Discovery call with a hot prospect",
        "account_query": HOT_PROSPECT_QUERY,
        "turns": [
            "I've got a discovery call with {account} coming up, what do I need to know?",
            "Who are the stakeholders we've engaged so far?",
            "Are they evaluating any competitors?",
        ],
    },
    {
        "label": "Drill-down / follow-up behavior (single account, multiple angles)",
        "account_query": "SELECT COMPANY_NAME FROM CRM.ACCOUNTS LIMIT 1",
        "turns": [
            "Tell me about {account}",
            "What's their ARR and how long have they been a customer?",
            "Ok, and if pricing comes up, what should I lead with?",
        ],
    },
    {
        "label": "Unknown account (tests honest failure, not hallucination)",
        "account_query": None,
        "turns": [
            "Prep me for my call with Definitely Not A Real Company Inc",
        ],
    },
]


def run_scenario(client, scenario):
    print(f"\n{'=' * 70}\n{scenario['label']}\n{'=' * 70}")
    account = None
    if scenario["account_query"]:
        account = _pick_account(scenario["account_query"])
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
