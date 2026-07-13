import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

import agent

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def group_into_turns(messages: list[dict]) -> list[dict]:
    """Groups the raw Anthropic message list into one entry per AE question,
    each carrying its final reply plus every tool call that backed it - so the
    UI can show "what did this answer actually pull from" rather than asking
    the AE to trust a black box. Sofia Alvarez's interview is explicit that a
    single wrong fact costs months of trust; showing sources is the cheapest
    way to make grounding checkable rather than just claimed in the prompt."""
    turns = []
    current = None
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg["content"], str):
            current = {"user": msg["content"], "tool_calls": [], "reply": ""}
            turns.append(current)
        elif msg["role"] == "assistant" and current is not None:
            for block in msg["content"]:
                block_type = getattr(block, "type", None)
                if block_type == "tool_use":
                    current["tool_calls"].append({"name": block.name, "input": block.input})
                elif block_type == "text":
                    current["reply"] += block.text
    return turns


EXAMPLE_PROMPTS = [
    "Prep me for my renewal call with Tide Logistics AG",
    "I've got a discovery call with Fjord Logistics AS, what do I need to know?",
    "What does the playbook say about handling a stalled renewal?",
    "Tell me about Brightline Retail GmbH",
]

st.set_page_config(page_title="Personio Call Prep Co-Pilot", page_icon="📞")

with st.sidebar:
    st.subheader("Try asking")
    st.caption("A new AE won't know what this can do on day one - a few real starting points:")
    for prompt in EXAMPLE_PROMPTS:
        if st.button(prompt, use_container_width=True):
            st.session_state.pending_prompt = prompt
    st.divider()
    st.caption("Pulls live from Snowflake (CRM/product/support) and Personio's sales enablement docs. Multi-turn - ask a follow-up.")

st.title("📞 Personio Call Prep Co-Pilot")
st.caption("Internal AI Team · AE call-prep assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

for turn in group_into_turns(st.session_state.messages):
    with st.chat_message("user"):
        st.markdown(turn["user"])
    if turn["reply"] or turn["tool_calls"]:
        with st.chat_message("assistant"):
            if turn["reply"]:
                st.markdown(turn["reply"])
            if turn["tool_calls"]:
                label = f"Sources ({len(turn['tool_calls'])} tool call{'s' if len(turn['tool_calls']) != 1 else ''})"
                with st.expander(label):
                    for call in turn["tool_calls"]:
                        st.caption(f"`{call['name']}`  {call['input']}")

if error_message := st.session_state.pop("error_message", None):
    st.error(error_message)

user_input = st.chat_input("Ask about an account, e.g. 'prep me for my call with...'")
if "pending_prompt" in st.session_state:
    user_input = st.session_state.pop("pending_prompt")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Pulling account context..."):
        try:
            client = get_client()
            st.session_state.messages = agent.run_turn(client, st.session_state.messages)
        except Exception:
            # A raw stack trace here would be worse than an honest "something
            # broke" - the interview research is explicit that a single bad
            # moment costs an AE's trust for months, and a naked traceback
            # reads as exactly that kind of bad moment.
            st.session_state.messages.pop()  # drop the unanswered turn rather than leave it stuck, unanswered, in history
            st.session_state.error_message = "Something went wrong pulling that together - mind trying again or rephrasing?"
    st.rerun()
