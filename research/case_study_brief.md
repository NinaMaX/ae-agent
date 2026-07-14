# Case study: Internal AI PM

*Personio · Internal AI Team · Product Manager – Internal AI*

Original case brief as provided, transcribed for reference alongside `13_ae_interview_notes.md`. See `ONE_PAGER.md` and `README.md` for how the actual build responds to this.

---

## Context

The Internal AI PM role is a builder role. You'll own a business domain end-to-end: setting the roadmap, building the solutions, and driving adoption.

The case mirrors that — build a working prototype of an agent for the business problem below. It's not a real problem or real data, but it's close to the kinds of problems our Internal AI team is actually solving today. Scope is open — what you choose to build, and what you choose not to, is part of what we're evaluating.

---

## The problem

Personio's Account Executives spend a meaningful slice of every week preparing for account calls — pulling context from Salesforce, scanning recent activity, finding the right battlecard, checking product usage, remembering what the playbook says about the deal stage they're in. Some of that prep is high-value pattern recognition. A lot of it is friction.

Build an **AI assistant for an AE preparing for an account call**. They should be able to chat with it about an account, ask follow-ups, drill into specifics. You decide what it covers and where the quality bar is.

**Persona.** A mid-market AE at Personio, ~18 months tenure, EMEA. Owns 30–40 accounts. Tomorrow she has a renewal expansion call with a churn-risk customer back-to-back with a discovery call with a hot prospect. She's preparing both under time pressure.

**Shape.** A conversational assistant. Multi-turn. The AE asks, the agent answers, the AE drills in.

---

## What you have access to

**Snowflake** — live read-only service account with Salesforce-shaped data: accounts, contacts, opportunities, activities, product usage, support tickets. ~75 accounts with realistic activity. Connection details below.

**Google Drive folder** — synthetic Personio sales enablement content: sales playbook, ICP, competitive battlecards, objection handling guide, pricing cheat sheet, customer case studies, and AE interview notes from prior PM discovery.

Both are synthetic. No real customer data.

```
Snowflake account:    <to be provisioned>
Warehouse:            CASE_STUDY_WH
Database:             CASE_STUDY
Schema:               GTM
User:                 CASE_STUDY_RO
Password / key:       <shared via secure channel on confirmation>
Drive folder:         <link to be provisioned>
```

*(Note: the actually-provisioned Snowflake account differed from this — real database was `PERSONIO` with schemas `CRM`/`PRODUCT`/`SUPPORT`, not `CASE_STUDY.GTM`. See `snowflake_tools.py`'s module docstring and `README.md`'s Status section.)*

---

## What we want from you

A working prototype, not a production-ready system. Two things, submitted at least 24 hours before the live session:

1. **A working agent.** Running code we can read, in a repo with a README. Python required, everything else your call — including how you connect to the data, the LLM, the framework, the agent pattern etc.
   - *In the session: you'll demo the agent running during your solution pitch, and we'll walk through the code together in the technical deep-dive.*
2. **A short one-pager explaining your approach.** Cover the bits we'd need to understand what you built and why — typically: scope (what you built and what you cut), architecture and key technical choices, how you'd think about quality, and what a path to production looks like. Lean into what matters most for your build; you don't need to cover everything equally.
   - *In the session: this is what we'll have read in advance, and what you'll use as the spine of your solution pitch. Bring slides built from it if you prefer, or present from the doc directly.*

We expect roughly 3–5 hours of focused work. There's plenty here to dig into — be intentional about scope, and build what you can explain.

---

## What we evaluate

We grade scoping judgment as much as build quality. Specifically:

- **What you chose to build, and why** — and what you cut.
- **Whether it works** — the agent runs, handles a realistic conversation, does sensible things with both the structured and unstructured data.
- **How you'd know it's good enough** — we expect you to define what "good" looks like and how you'd measure it.
- **How an AE would actually use it** — not just "does it work," but "would she reach for it tomorrow."

We don't grade on framework choice, slide polish, or feature count.

---

## Logistics

**Clarifying questions.** Make simplifying assumptions where necessary. If you get stuck or require further clarity reach out to eva.wong@personio.de

**Submission.** Code link + your one-pager, sent to at least 24 hours before the session.

**Live session.** 60 minutes:

- 25 min — **Solution presentation + demo.** Walk us through what you built and why, using your one-pager as the spine and showing the agent running.
- 25 min — **Technical deep-dive.** We go into your code, architecture, and design choices. You drive; we ask. Expect us to dig into the *why* behind your choices.
- 10 min — **Your questions.**

The live session is where we verify what you did, hear how you think, and find out whether we'd enjoy working with you on real problems.

Good luck.
