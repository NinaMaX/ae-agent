import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

import agent

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def is_displayable_user_turn(content) -> bool:
    """A user turn is either what the AE typed (a string) or a tool_result
    round-trip (a list of dicts) - only the former should render in the UI."""
    return isinstance(content, str)


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

for msg in st.session_state.messages:
    if msg["role"] == "user":
        if is_displayable_user_turn(msg["content"]):
            with st.chat_message("user"):
                st.markdown(msg["content"])
    else:
        text = "".join(b.text for b in msg["content"] if getattr(b, "type", None) == "text")
        if text:
            with st.chat_message("assistant"):
                st.markdown(text)

user_input = st.chat_input("Ask about an account, e.g. 'prep me for my call with...'")
if "pending_prompt" in st.session_state:
    user_input = st.session_state.pop("pending_prompt")

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("Pulling account context..."):
            try:
                client = get_client()
                st.session_state.messages = agent.run_turn(client, st.session_state.messages)
                reply = agent.latest_reply_text(st.session_state.messages)
            except Exception:
                # A raw stack trace here would be worse than an honest "something
                # broke" - the interview research is explicit that a single bad
                # moment costs an AE's trust for months, and a naked traceback
                # reads as exactly that kind of bad moment.
                st.session_state.messages.pop()  # drop the unanswered turn, don't leave it stuck in history
                reply = "Something went wrong pulling that together - mind trying again or rephrasing?"
        st.markdown(reply)
